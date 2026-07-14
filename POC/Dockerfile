# VPS runner image — curl_cffi only, NO browser (Playwright stays on the home machine).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Jakarta

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-runner.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-runner.txt -r requirements-web.txt

COPY src/ ./src/
COPY config/ ./config/
COPY tests/ ./tests/
COPY webapp/ ./webapp/

# data/ (SQLite + exports + reports) is a mounted volume, not baked into the image.
ENTRYPOINT ["python", "src/runner.py"]
CMD ["--reset-today"]
