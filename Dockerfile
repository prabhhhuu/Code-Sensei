# ── AI Code Tutor ────────────────────────────────────────────────────────────
# Base image includes pip + venv tooling; slim keeps the image small.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Toolchains required by run_challenge_tests():
#   node   -> JavaScript / TypeScript
#   default-jdk (javac/java) -> Java
#   gcc / g++  -> C / C++
# curl is used by health checks (optional but handy).
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs npm \
        default-jdk-headless \
        gcc g++ libc6-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the backend source (templates/static included).
COPY backend/ /app/backend/

WORKDIR /app/backend

# SQLite DB location can be overridden via DATABASE_DIR (e.g. mounted volume).
# Allow the runtime user to write it when DATABASE_DIR points elsewhere.
ENV DATABASE_DIR=/app/backend

# Non-root runtime user; owns the app dir so the SQLite file can be created.
RUN useradd -m -u 1000 tutor \
    && mkdir -p /app/backend \
    && chown -R tutor:tutor /app/backend
USER tutor

EXPOSE 8000

# gunicorn: 4 threads, 120s timeout (Groq calls can take up to 90s).
# Worker count is overridable: set WEB_CONCURRENCY=1 on 512MB hosts (Render free)
# to leave memory headroom for javac/g++ subprocesses.
CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-2} --threads 4 --timeout 120 -b 0.0.0.0:${PORT:-8000} app:app"]
