FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SANDBOX_SOCKET_PATH=/sandbox/tool.sock

RUN useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    sandbox

RUN mkdir -p /sandbox \
    && chown sandbox:sandbox /sandbox

COPY runner.py /app/runner.py

USER sandbox

CMD ["python", "/app/runner.py"]
