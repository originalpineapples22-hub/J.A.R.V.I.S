# 0.5.4.M.4 — container image (Fly.io, Koyeb, Railway, or any Docker host)
FROM python:3.12-slim

# Build tools are needed for pywebpush; ffmpeg lets it read social video.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential python3-dev libffi-dev ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-optional.txt ./

# Core must succeed. Optional extras are best-effort — a package that will not
# build simply leaves its feature switched off instead of failing the image.
RUN pip install --no-cache-dir --upgrade pip wheel setuptools \
 && pip install --no-cache-dir -r requirements.txt \
 && while read -r line; do \
      pkg="${line%%#*}"; pkg="$(echo $pkg | xargs)"; \
      [ -z "$pkg" ] && continue; \
      pip install --no-cache-dir "$pkg" || echo "optional skipped: $pkg"; \
    done < requirements-optional.txt

COPY . .

# Memory, settings and files live on a mounted volume so they survive deploys.
ENV JARVIS_DATA=/data PORT=8080 PYTHONUNBUFFERED=1
RUN mkdir -p /data
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["sh", "-c", "uvicorn jarvis.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
