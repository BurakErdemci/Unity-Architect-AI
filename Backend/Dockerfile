FROM python:3.11-slim

WORKDIR /app

# System deps for bcrypt/cryptography/grpcio
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

# SQLite DB volume
VOLUME /data
ENV DB_PATH=/data/unity_master_v3.db

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
