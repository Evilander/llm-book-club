FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd --system --gid 1001 api && \
    useradd --system --uid 1001 --gid api --create-home --home-dir /home/api api

COPY requirements*.txt ./
ARG INSTALL_LOCAL_MODELS=false
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_LOCAL_MODELS" = "true" ]; then pip install --no-cache-dir -r requirements-local.txt; fi

COPY --chown=api:api app ./app
COPY --chown=api:api alembic ./alembic
COPY --chown=api:api alembic.ini run_worker.py ./

RUN mkdir -p /app/storage && chown api:api /app/storage
USER api

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
