# Development and verification

Use the published `main` branch for the current reading experience. Older branches contain different app implementations.

## Local installation

Requirements: Docker with Compose, or Python 3.12, Node 22, PostgreSQL 16 with pgvector 0.8 or newer, and Redis 7.

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.local.example apps/web/.env.local
docker compose up --build --wait
```

The default CPU encoder prepares books without a hosted embedding account. Configure discussion access in Settings or the API environment file. Native vector dimensions are checked against the configured model, normalized, and zero-padded to the existing storage dimension. Retrieval also requires matching model provenance. See [local search and memory](local-search.md) for model changes and refreshing existing books.

The migration service must finish before the API and worker start. The API verifies the migration head, generated full-text column, and search indexes. A failure stops startup. `/health` returns HTTP 503 when Postgres or Redis is unavailable and omits connection exception details.

Services bind to loopback by default. The API runs as an unprivileged container user and includes its migrations. Before the API and worker start, `storage-init` gives that user ownership of the managed upload volume, including uploads written by older containers running as root. This one-time startup service has no network and does not mount the external books folder.

Docker includes CPU model dependencies by default. For a non-Docker installation, install `apps/api/requirements-local.txt` as well as the base requirements. Installations that use only HTTP embedding/reranking providers can build with `INSTALL_LOCAL_MODELS=false` to omit those dependencies. The deterministic integration image intentionally uses that smaller build; its tests do not measure local model quality.

## Automated checks

The SQLite unit suite and real Postgres suite run in separate processes. The unit suite intentionally replaces the pgvector type; it cannot prove that database indexes or migrations work.

```bash
pip install -r apps/api/requirements.txt
python -m pytest apps/api/tests -q

docker compose -p readagain-verification -f compose.integration.yml --profile app up --build -d --wait
export TEST_DATABASE_URL=postgresql+psycopg://readagain_test:integration-only@127.0.0.1:55432/postgres
export TEST_REDIS_URL=redis://127.0.0.1:56379/0
export TEST_APP_URL=http://127.0.0.1:58000
export TEST_PROVIDER_URL=http://127.0.0.1:59000
cd apps/api
python -m pytest integration -q
cd ../..
docker compose -p readagain-verification -f compose.integration.yml --profile app down -v
```

The verification stack uses temporary database storage and generated test documents. Its local HTTP provider produces deterministic embeddings and replies; no API keys or real books are used. Each database test creates and removes only its own randomly named `readagain_test_*` database. Set `TEST_DATABASE_URL` only to an isolated server with database-creation permission.

Check the ChatGPT runtime packaged in the API image against the same offline provider:

```bash
docker compose -p readagain-verification -f compose.integration.yml exec -T api python - < apps/api/integration/check_chatgpt_package.py
```

This runs two independent synthetic reading turns through the native App Server. It verifies streaming, usage, context isolation, native rollout storage, and the exposed tool set without signing in or accessing a paid model. See [ChatGPT connection](chatgpt-connection.md) for the supported runtime version and live setup.

The workflow tests upload EPUB, PDF, and TXT through the API, wait for the real RQ worker, open the reader, validate margin quotes, stream a discussion, open citations, and check that an earlier thought reaches a later session. They also return from a later discussion to an earlier page and inspect the provider's HTTP requests for unread text or later thoughts. The fixture provider's loopback port 59000 exposes test-only capture/reset endpoints; it is not part of the production app. Database tests cover fresh and concurrent startup, rollback after failures, upgrades from the old stamped schema, explicit legacy adoption, and both retrieval branches. See [grounding and reading boundaries](grounding-and-reading-boundaries.md) for the citation, Unicode, and stream contracts.

For UI checks:

```bash
cd apps/web
npm ci
npm run test:stream
npm run build
npx playwright install chromium
npm run start
# In another shell, from apps/web:
READING_TEST_URL=http://127.0.0.1:3000 npm run test:reader
```

The browser suite covers paper, Bionic text, pagination, highlights, desktop/mobile drawers, streaming, and saved preferences. It uses request fixtures. GitHub Actions runs these checks, the real integration stack, and a pinned Gitleaks credential scan. Review personal information separately; a secret scanner cannot identify every private detail.

## Database upgrades and recovery

Back up the library before upgrading an existing installation:

```bash
docker compose exec -T db pg_dump -U bookclub -Fc bookclub > library-backup.dump
docker compose run --rm migrate
```

Store backups outside the repository. Keep the upload storage volume together with the database backup.

Revision 007 repairs search objects skipped by the old fresh-install path. It uses a half-precision HNSW expression while keeping the original full-precision vectors. Candidate search uses that expression and then ranks candidates with full-precision distances. The migration may block ingestion while indexes are built; run it during a maintenance window for a large library.

An existing library with no Alembic revision is not silently stamped. After a backup, the explicit recovery command validates the known table/column types, nullability, enums, and primary keys before adopting the library:

```bash
docker compose run --rm migrate python -m app.db.init_db --adopt-unversioned
```

Unknown or partial legacy schemas are rejected without applying changes. Inspect the reported schema differences and restore/repair a copy before proceeding; do not manually stamp an unverified schema. A missing migration file, an unknown revision, an old pgvector extension, or an invalid index also prevents startup.

The schema lock, migrations, search objects, and version stamp share one database transaction. See [Alembic's shared-connection pattern](https://alembic.sqlalchemy.org/en/latest/cookbook.html#sharing-a-connection-with-a-series-of-migration-commands-and-environments). The half-precision index and iterative scan follow [pgvector's indexing guidance](https://github.com/pgvector/pgvector#half-precision-indexing). Node 22 is a supported LTS runtime; the former Node 20 image is end-of-life according to the [Node release schedule](https://nodejs.org/en/about/previous-releases).
