FROM node:22-bookworm-slim AS chatgpt-runtime
RUN npm install --prefix /opt/codex --ignore-scripts --no-audit --no-fund @openai/codex@0.154.0
# Copy only the native runtime; Node/npm are not needed in the API image.
RUN node --input-type=module -e 'import { globSync, copyFileSync } from "node:fs"; const [binary] = [...globSync("/opt/codex/node_modules/@openai/codex-*/vendor/*/bin/codex")]; if (!binary) throw new Error("Codex runtime missing"); copyFileSync(binary, "/opt/codex-native");'

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CHATGPT_STATE_DIR=/app/chatgpt
ENV LOCAL_EMBEDDINGS_CACHE_DIR=/app/models

RUN groupadd --system --gid 1001 api && \
    useradd --system --uid 1001 --gid api --create-home --home-dir /home/api api

COPY requirements*.txt ./
ARG INSTALL_LOCAL_MODELS=true
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_LOCAL_MODELS" = "true" ]; then \
      pip install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r requirements-local.txt; fi

COPY --chown=api:api app ./app
COPY --chown=api:api alembic ./alembic
COPY --chown=api:api alembic.ini run_worker.py ./
COPY --from=chatgpt-runtime --chmod=755 /opt/codex-native /usr/local/bin/codex
COPY third_party/codex/ /usr/share/licenses/codex/

RUN mkdir -p /app/storage /app/chatgpt /app/models && chown api:api /app/storage /app/chatgpt /app/models && chmod 700 /app/chatgpt
USER api

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
