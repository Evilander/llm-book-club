"""Full ingestion pipeline for processing books."""
from __future__ import annotations
import os
import uuid
import logging
from pathlib import Path
from datetime import datetime

from sqlalchemy.orm import Session

from ..db.models import Book, Section, Chunk, IngestStatus, ReadingUnit, ReadingUnitType, ReadingUnitStatus, BookMemory
from ..db.engine import SessionLocal
from ..providers.embeddings.factory import get_embeddings_client
from ..providers.llm.factory import get_llm_client
from .extractor import extract_text
from .chunker import chunk_sections, chunk_text, estimate_tokens, estimate_reading_time
from .intelligent_chunker import IntelligentChunker, StructureAnalyzer

logger = logging.getLogger(__name__)


# Storage directory for uploaded files
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./storage"))
STORAGE_DIR.mkdir(exist_ok=True)


def save_uploaded_file(file_data: bytes, filename: str) -> tuple[str, Path]:
    """
    Save uploaded file to storage.

    Returns:
        Tuple of (file_id, file_path)
    """
    file_id = str(uuid.uuid4())
    ext = Path(filename).suffix.lower()
    file_path = STORAGE_DIR / f"{file_id}{ext}"
    file_path.write_bytes(file_data)
    return file_id, file_path


async def run_ingestion_pipeline(
    book_id: str,
    file_data: bytes,
    filename: str,
) -> str:
    """
    Run the full ingestion pipeline for a book.

    Args:
        book_id: Database ID for the book record
        file_data: Raw file bytes
        filename: Original filename

    Returns:
        book_id on success
    """
    db = SessionLocal()

    try:
        # Update status to processing
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise ValueError(f"Book {book_id} not found")

        book.ingest_status = IngestStatus.PROCESSING
        db.commit()

        # Step 1: Extract text and sections
        extracted = extract_text(file_data, filename)

        # Update book metadata
        book.title = extracted.title
        book.author = extracted.author
        book.total_chars = len(extracted.full_text)
        book.total_tokens_estimate = estimate_tokens(extracted.full_text)
        book.metadata_json = extracted.metadata
        db.commit()

        # Step 2: Chunk sections
        chunked = chunk_sections(extracted.sections)

        # Step 3: Create section and chunk records
        all_chunks_for_embedding = []
        chunk_records = []

        for cs in chunked:
            sec = cs.section

            section_record = Section(
                book_id=book_id,
                title=sec.title,
                section_type=sec.section_type,
                order_index=sec.order_index,
                char_start=sec.char_start,
                char_end=sec.char_end,
                page_start=sec.page_start,
                page_end=sec.page_end,
                token_estimate=estimate_tokens(sec.text),
                reading_time_min=estimate_reading_time(sec.text),
            )
            db.add(section_record)
            db.flush()  # Get the section ID

            for chunk in cs.chunks:
                chunk_record = Chunk(
                    book_id=book_id,
                    section_id=section_record.id,
                    order_index=chunk.order_index,
                    text=chunk.text,
                    char_start=chunk.absolute_char_start,
                    char_end=chunk.absolute_char_end,
                    source_ref=chunk.source_ref,
                    token_count=estimate_tokens(chunk.text),
                )
                db.add(chunk_record)
                chunk_records.append(chunk_record)

                # Contextual chunk header for improved retrieval
                context_header = f"[Book: {book.title}"
                if sec.title:
                    context_header += f" | {sec.section_type.title()}: {sec.title}"
                context_header += f" | Section {sec.order_index + 1}] "
                augmented_text = context_header + chunk.text
                all_chunks_for_embedding.append(augmented_text)

        db.commit()

        # Step 4: Generate embeddings
        embeddings_client = get_embeddings_client()
        embeddings = await embeddings_client.embed(all_chunks_for_embedding)

        # Step 5: Update chunks with embeddings
        for chunk_record, embedding in zip(chunk_records, embeddings):
            chunk_record.embedding = embedding

        db.commit()

        # Mark as completed
        book.ingest_status = IngestStatus.COMPLETED
        db.commit()

        return book_id

    except Exception as e:
        # Mark as failed
        db.rollback()
        book = db.query(Book).filter(Book.id == book_id).first()
        if book:
            book.ingest_status = IngestStatus.FAILED
            book.ingest_error = str(e)
            db.commit()
        raise

    finally:
        db.close()


def run_ingestion_sync(book_id: str, file_data: bytes, filename: str) -> str:
    """
    Synchronous wrapper for ingestion pipeline (for RQ worker).
    """
    import asyncio
    return asyncio.run(run_ingestion_pipeline(book_id, file_data, filename))


async def run_intelligent_ingestion_pipeline(
    book_id: str,
    file_data: bytes,
    filename: str,
    use_intelligent_chunking: bool = True,
) -> str:
    """
    Enhanced ingestion pipeline with intelligent structure analysis and reading units.

    This pipeline:
    1. Extracts text using standard extraction
    2. Analyzes book structure using LLM sampling
    3. Creates intelligent reading units respecting narrative boundaries
    4. Chunks each reading unit for embedding
    5. Generates embeddings
    6. Initializes BookMemory for tracking user progress

    Args:
        book_id: Database ID for the book record
        file_data: Raw file bytes
        filename: Original filename
        use_intelligent_chunking: Whether to use LLM-assisted structure analysis

    Returns:
        book_id on success
    """
    db = SessionLocal()

    try:
        # Update status to processing
        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            raise ValueError(f"Book {book_id} not found")

        book.ingest_status = IngestStatus.PROCESSING
        db.commit()

        logger.info(f"Starting intelligent ingestion for book {book_id}: {filename}")

        # Step 1: Extract text
        extracted = extract_text(file_data, filename)

        # Update book metadata
        book.title = extracted.title
        book.author = extracted.author
        book.total_chars = len(extracted.full_text)
        book.total_tokens_estimate = estimate_tokens(extracted.full_text)
        book.metadata_json = extracted.metadata
        db.commit()

        logger.info(f"Extracted {book.total_tokens_estimate} tokens from {filename}")

        # Step 2: Analyze structure and create reading units (if intelligent chunking enabled)
        all_chunks_for_embedding = []
        chunk_records = []

        if use_intelligent_chunking and book.total_tokens_estimate > 10000:
            # Use intelligent chunking for larger texts
            llm_client = get_llm_client()
            chunker = IntelligentChunker(llm_client)

            logger.info("Analyzing book structure...")
            structure = await chunker.analyzer.analyze_structure(extracted.full_text)
            logger.info(f"Detected structure: {structure.book_type}, complexity: {structure.estimated_complexity}")

            # Create reading units
            logger.info("Creating reading units...")
            unit_specs = await chunker.create_reading_units(extracted.full_text, structure)
            logger.info(f"Created {len(unit_specs)} reading units")

            # Store structure analysis in book metadata
            book.metadata_json = {
                **(book.metadata_json or {}),
                "structure_analysis": {
                    "book_type": structure.book_type,
                    "has_chapters": structure.has_chapters,
                    "has_endnotes": structure.has_endnotes,
                    "is_non_linear": structure.is_non_linear,
                    "complexity": structure.estimated_complexity,
                    "narrative_threads": [t.name for t in structure.narrative_threads],
                }
            }
            db.commit()

            # Create reading unit and chunk records
            for unit_idx, unit_spec in enumerate(unit_specs):
                unit_text = extracted.full_text[unit_spec.char_start:unit_spec.char_end]

                # Map unit type string to enum
                try:
                    unit_type = ReadingUnitType(unit_spec.unit_type)
                except ValueError:
                    unit_type = ReadingUnitType.SECTION

                reading_unit = ReadingUnit(
                    book_id=book_id,
                    title=unit_spec.title,
                    unit_type=unit_type,
                    order_index=unit_idx,
                    char_start=unit_spec.char_start,
                    char_end=unit_spec.char_end,
                    token_estimate=estimate_tokens(unit_text),
                    reading_time_min=estimate_reading_time(unit_text),
                    narrative_thread=unit_spec.narrative_thread,
                    chronological_position=unit_spec.chronological_position,
                    status=ReadingUnitStatus.UNREAD,
                    related_units=unit_spec.related_unit_indices if unit_spec.related_unit_indices else None,
                )
                db.add(reading_unit)
                db.flush()  # Get the reading unit ID

                # Chunk this reading unit
                chunks = chunk_text(
                    text=unit_text,
                    section_char_start=unit_spec.char_start,
                    chunk_size=1500,
                    overlap=200,
                    source_ref_base=unit_spec.source_refs[0] if unit_spec.source_refs else None,
                )

                for chunk in chunks:
                    chunk_record = Chunk(
                        book_id=book_id,
                        reading_unit_id=reading_unit.id,
                        order_index=chunk.order_index,
                        text=chunk.text,
                        char_start=chunk.absolute_char_start,
                        char_end=chunk.absolute_char_end,
                        source_ref=chunk.source_ref,
                        token_count=estimate_tokens(chunk.text),
                    )
                    db.add(chunk_record)
                    chunk_records.append(chunk_record)

                    # Contextual chunk header for improved retrieval
                    context_header = f"[Book: {book.title}"
                    if unit_spec.title:
                        context_header += f" | {unit_type.value.title()}: {unit_spec.title}"
                    context_header += f" | Unit {unit_idx + 1}] "
                    augmented_text = context_header + chunk.text
                    all_chunks_for_embedding.append(augmented_text)

            db.commit()

            # Also create legacy Section records for backwards compatibility
            await _create_legacy_sections(db, book_id, extracted.sections)

        else:
            # Use standard section-based chunking for smaller texts or when disabled
            logger.info("Using standard section-based chunking")
            chunked = chunk_sections(extracted.sections)

            for cs in chunked:
                sec = cs.section

                section_record = Section(
                    book_id=book_id,
                    title=sec.title,
                    section_type=sec.section_type,
                    order_index=sec.order_index,
                    char_start=sec.char_start,
                    char_end=sec.char_end,
                    page_start=sec.page_start,
                    page_end=sec.page_end,
                    token_estimate=estimate_tokens(sec.text),
                    reading_time_min=estimate_reading_time(sec.text),
                )
                db.add(section_record)
                db.flush()

                # Also create a reading unit for each section
                reading_unit = ReadingUnit(
                    book_id=book_id,
                    title=sec.title,
                    unit_type=ReadingUnitType.SECTION,
                    order_index=sec.order_index,
                    char_start=sec.char_start,
                    char_end=sec.char_end,
                    token_estimate=estimate_tokens(sec.text),
                    reading_time_min=estimate_reading_time(sec.text),
                    status=ReadingUnitStatus.UNREAD,
                )
                db.add(reading_unit)
                db.flush()

                for chunk in cs.chunks:
                    chunk_record = Chunk(
                        book_id=book_id,
                        section_id=section_record.id,
                        reading_unit_id=reading_unit.id,
                        order_index=chunk.order_index,
                        text=chunk.text,
                        char_start=chunk.absolute_char_start,
                        char_end=chunk.absolute_char_end,
                        source_ref=chunk.source_ref,
                        token_count=estimate_tokens(chunk.text),
                    )
                    db.add(chunk_record)
                    chunk_records.append(chunk_record)

                    # Contextual chunk header for improved retrieval
                    context_header = f"[Book: {book.title}"
                    if sec.title:
                        context_header += f" | {sec.section_type.title()}: {sec.title}"
                    context_header += f" | Section {sec.order_index + 1}] "
                    augmented_text = context_header + chunk.text
                    all_chunks_for_embedding.append(augmented_text)

            db.commit()

        logger.info(f"Created {len(chunk_records)} chunks for embedding")

        # Step 3: Generate embeddings
        embeddings_client = get_embeddings_client()
        embeddings = await embeddings_client.embed(all_chunks_for_embedding)

        # Step 4: Update chunks with embeddings
        for chunk_record, embedding in zip(chunk_records, embeddings):
            chunk_record.embedding = embedding

        db.commit()
        logger.info("Embeddings generated and stored")

        # Step 5: Initialize BookMemory for progress tracking
        book_memory = BookMemory(
            book_id=book_id,
            units_completed=[],
            total_reading_time_min=0,
            xp_earned=0,
            achievements_unlocked=[],
        )
        db.add(book_memory)
        db.commit()
        logger.info("BookMemory initialized")

        # Mark as completed
        book.ingest_status = IngestStatus.COMPLETED
        db.commit()

        logger.info(f"Intelligent ingestion complete for book {book_id}")
        return book_id

    except Exception as e:
        logger.error(f"Ingestion failed for {book_id}: {e}")
        db.rollback()
        book = db.query(Book).filter(Book.id == book_id).first()
        if book:
            book.ingest_status = IngestStatus.FAILED
            book.ingest_error = str(e)
            db.commit()
        raise

    finally:
        db.close()


async def _create_legacy_sections(db: Session, book_id: str, sections) -> None:
    """Create legacy Section records for backwards compatibility."""
    for sec in sections:
        section_record = Section(
            book_id=book_id,
            title=sec.title,
            section_type=sec.section_type,
            order_index=sec.order_index,
            char_start=sec.char_start,
            char_end=sec.char_end,
            page_start=sec.page_start,
            page_end=sec.page_end,
            token_estimate=estimate_tokens(sec.text),
            reading_time_min=estimate_reading_time(sec.text),
        )
        db.add(section_record)
    db.commit()


def run_intelligent_ingestion_sync(
    book_id: str,
    file_data: bytes,
    filename: str,
    use_intelligent_chunking: bool = True
) -> str:
    """
    Synchronous wrapper for intelligent ingestion pipeline (for RQ worker).
    """
    import asyncio
    return asyncio.run(run_intelligent_ingestion_pipeline(
        book_id, file_data, filename, use_intelligent_chunking
    ))
