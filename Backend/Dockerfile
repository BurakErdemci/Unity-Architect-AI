# Development container for the backend only. It exists so a contributor can
# work on the Python side without installing Python 3.13 and building a venv;
# the Electron app still runs on the host and connects to this container.
#
# What does NOT work in here, by construction: the subscription CLI providers
# (Claude Code, Codex, Cursor, Copilot, Kimi, agy). They are installed on the
# host and signed in as the host user, and neither travels into an image. Cloud
# API providers are plain HTTP and work normally. See docs/building.md.

# 3.13 because that is what the project targets (CONTRIBUTING.md). This said
# 3.11 until 31 Aug 2026, one of several reasons the container had never run.
FROM python:3.13-slim

WORKDIR /app

# Build deps for the wheels that still compile from source (bcrypt is imported
# by database.py, so it is not dead weight). Removed in the same layer so they
# do not ship in the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

# The SQLite file lives on a volume so a rebuild does not discard the history.
VOLUME /data
ENV DB_PATH=/data/unity_master_v3.db

# 0.0.0.0, not the app's 127.0.0.1 default: bound to loopback the port is
# published but nothing on the host can reach it. Measured 31 Aug 2026 — the
# container would have started and then refused every connection.
ENV HOST=0.0.0.0
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "main.py"]
