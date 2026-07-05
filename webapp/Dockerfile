FROM python:3.11-slim

# Keep Python output unbuffered for logs; store DB on the mounted volume.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SUBITO_DB=/data/subito.db

WORKDIR /app

# Install dependencies first for better layer caching.
COPY webapp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the app.
COPY webapp/app.py /app/app.py
COPY webapp/scraper.py /app/scraper.py
COPY webapp/storage.py /app/storage.py
COPY webapp/static /app/static

# DB lives here (mounted as a volume in docker-compose).
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
