FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 api \
    && useradd --system --uid 1001 --gid api --home /app --shell /usr/sbin/nologin api

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=api:api app ./app
COPY --chown=api:api run_worker.py .

RUN mkdir -p /app/storage && chown -R api:api /app/storage

USER api

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
