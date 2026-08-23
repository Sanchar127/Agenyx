FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    sandbox

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY runner.py /app/runner.py

USER sandbox

EXPOSE 9000

CMD ["uvicorn", "runner:app", "--host", "0.0.0.0", "--port", "9000"]
