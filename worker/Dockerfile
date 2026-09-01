
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies first for better Docker layer caching.
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user with a numeric UID/GID.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --no-create-home app

# Copy application source.
COPY app ./app

# Kubernetes runAsNonRoot can reliably verify this numeric UID.
USER 10001:10001

CMD ["python", "-m", "app.main"]
