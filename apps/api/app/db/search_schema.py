"""Postgres-only retrieval objects for a newly created ORM schema."""
from sqlalchemy import text


def install_search_objects(connection) -> None:
    connection.execute(text("""
        ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    """))
    connection.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_chunks_text_search
        ON chunks USING gin(text_search)
    """))
    connection.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw
        ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """))


def verify_search_objects(connection) -> None:
    columns = connection.execute(text("""
        SELECT column_name, data_type, is_generated
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'chunks'
          AND column_name = 'text_search'
    """)).mappings().all()
    if not columns or columns[0]['data_type'] != 'tsvector' or columns[0]['is_generated'] != 'ALWAYS':
        raise RuntimeError("The library's generated full-text search column is missing or invalid.")
    indexes = connection.execute(text("""
        SELECT idx.relname AS name, i.indisvalid, pg_get_indexdef(i.indexrelid) AS definition
        FROM pg_index i JOIN pg_class idx ON idx.oid = i.indexrelid
        WHERE i.indrelid = 'chunks'::regclass
    """)).mappings().all()
    by_name = {row['name']: row for row in indexes}
    for name, fragments in {
        'idx_chunks_text_search': ('USING gin', 'text_search'),
        'ix_chunks_embedding_hnsw': ('USING hnsw', 'halfvec(3072)', 'halfvec_cosine_ops'),
    }.items():
        row = by_name.get(name)
        if not row or not row['indisvalid'] or any(part not in row['definition'] for part in fragments):
            raise RuntimeError(f"The library's retrieval index {name} is missing or invalid.")
