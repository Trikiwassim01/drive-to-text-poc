FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tesseract + the three supported OCR languages (English, French, Arabic).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
