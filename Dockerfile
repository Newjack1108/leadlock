# Backend API - used when building from repo root (backend service).
# Build context: repo root. Copy api/ into /app and run uvicorn.

FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./

# Copy logo into static/ so PDF generation can find it (api/ has no access to web/ at runtime)
RUN mkdir -p static
COPY web/public/logo1.jpg web/public/logo1.png static/

ENV PORT=8000
EXPOSE 8000

# Railway sets PORT at runtime
CMD ["/bin/sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
