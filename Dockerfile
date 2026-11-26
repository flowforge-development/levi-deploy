FROM python:3.13-slim

WORKDIR /app
COPY levi_engine ./levi_engine

# numpy: cosine scoring for semantic search (std-only otherwise kept)
RUN pip install --no-cache-dir numpy

ENV PYTHONUNBUFFERED=1 \
    LEVI_DB_PATH=/data/levi.db

EXPOSE 8777

HEALTHCHECK --interval=60s --timeout=10s \
  CMD python3 -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8777/health', timeout=5)" || exit 1

CMD ["python3", "-m", "levi_engine.api", "--host", "0.0.0.0", "--port", "8777"]