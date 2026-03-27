# Backend API - use when Railway Root Directory is set to "api".
# Build context = api/ (this directory). Copy requirements then app code.

FROM python:3.11-slim

# Needed if this image runs backup.py (cron) or any pg_dump; small cost vs a broken backup service.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV PORT=8000
EXPOSE 8000

CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
