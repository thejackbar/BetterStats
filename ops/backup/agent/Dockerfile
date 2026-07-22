# betterstats-backup-agent — small sidecar with Docker-socket + host
# filesystem access so backup.sh can be triggered from the Super Admin UI
# without giving the main backend container that privilege. See app.py's
# module docstring and docs/backup-system.md for the full reasoning.
FROM python:3.11-slim

# docker CLI + compose plugin, so this container can run the exact same
# `docker compose exec ...` / `docker run ...` commands backup.sh already
# uses on the host (it just executes backup.sh directly — see app.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg age zstd coreutils bash \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
