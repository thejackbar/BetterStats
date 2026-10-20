FROM python:3.11-slim

WORKDIR /app

# chromium + fonts: the club teaser renderer (services/club_teaser_images.py)
# screenshots the site's card pages with it. Playwright drives this one; it does
# not download its own (PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD), so the image stays the
# size of one browser, not two.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc tesseract-ocr chromium fonts-liberation fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    TEASER_CHROMIUM_PATH=/usr/bin/chromium

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
