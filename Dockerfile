# ---- Falcon Fitness — deployment image -------------------------------------
# Stage 1 compiles the C++ training engine.
FROM debian:bookworm-slim AS engine-build

RUN apt-get update \
 && apt-get install -y --no-install-recommends g++ \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY engine/main.cpp .
RUN g++ -O3 -std=c++17 -static-libstdc++ -static-libgcc -o falcon-engine main.cpp

# ---- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim

# non-root user: Cloud Run refuses to boot as root
RUN useradd --create-home --shell /bin/bash falcon
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# prebuilt engine from stage 1 (no compiler in the final image)
COPY --from=engine-build /build/falcon-engine ./bin/falcon-engine
RUN chmod +x ./bin/falcon-engine

# Every Python module app.py imports at start-up must be here, or the container
# dies with ModuleNotFoundError the moment it boots. app.py imports
# receipt_check, membership and sms_otp at module level (lines 36-38).
COPY app.py fallback_engine.py membership.py receipt_check.py sms_otp.py ./
COPY engine/ ./engine/
COPY .env.example ./
COPY templates/ ./templates/
COPY static/ ./static/

# No binary import here — but on some hosts (e.g. Cloud Run) argv[0] is not
# "python", so the launcher block in app.py never runs. gunicorn fixes that.
RUN pip install --no-cache-dir gunicorn

# /data is the Fly volume mount; make sure the non-root user can write to it
RUN mkdir -p data /data && chown -R falcon:falcon /app /data
USER falcon

# The database MUST live on the mounted volume or every redeploy wipes it.
# fly.toml mounts the volume at /data, so that is where the database goes.
ENV PORT=8080 \
    FALCON_DB_PATH=/data/falcon.db \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz').status==200 else 1)"

# gunicorn: 2 workers is plenty for a brochure site + small API.
# --preload keeps a single SQLite writer per worker and warms the engine once.
# shell form (no exec) so ${PORT} is expanded — the base image's ENTRYPOINT
# already wraps this in /bin/sh -c.
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 \
    --timeout 60 --access-logfile - --error-logfile - app:app
