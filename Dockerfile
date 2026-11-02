FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRANSCRIPTION_PROVIDER=fake \
    DATABASE_URL=sqlite:////data/calls.db \
    RECORDINGS_DIR=/data/recordings \
    MONITOR_DIR=/var/spool/asterisk/monitor \
    CDR_PATH=/var/log/asterisk/cdr-csv/Master.csv \
    WATCH_ENABLED=true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/recordings /var/spool/asterisk/monitor /var/log/asterisk/cdr-csv \
    && chown -R appuser:appuser /data /var/spool/asterisk/monitor /var/log/asterisk/cdr-csv

COPY app ./app
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
