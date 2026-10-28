# The clinician surface, as a deployable container.
#
# Only the surface. `make` runs the gates, the walkthrough and the live encounters
# and then serves — that is the developer's entry point and it is wrong here: a
# platform restarting the container should not re-run a test suite before it will
# answer a health check, and a public URL must never make a model call because
# somebody loaded a page.
#
# Real model output still reaches the hosted page. It is replayed from the store,
# written by a live run before deployment — which is the resumption machinery
# doing exactly what it was built for. See docs/CODE.md, "The second run picks up
# where the first stopped".

FROM python:3.13-slim

# Faster starts and no .pyc litter in a read-only-ish layer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/docker-entrypoint.sh

# Not root. The process needs to read the packs and talk to Postgres, nothing else.
RUN useradd --create-home --uid 10001 clinician && chown -R clinician:clinician /app
USER clinician

# The platform overrides PORT; 8000 is the local default.
ENV HOST=0.0.0.0 \
    PORT=8000 \
    CLINICIAN_HOSTED=1
EXPOSE 8000

# The container can report whether it is working, not merely running. /health
# answers with which store backend it actually reached, whether the scripted
# page built, and what has gone wrong in the process so far, so a platform
# restarting on this signal is restarting on something that means something. A
# degraded build still answers 200 and keeps serving; only an unreachable
# store is a 503, because that is the case where restarting might help.
#
# urlopen raises on any non-2xx, which is the non-zero exit Docker wants.
# python rather than curl: this image has no curl and does not need one.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health',timeout=4)"]

# The entrypoint decides whether to pass --live, from what the deployment has
# rather than from what the image was built with.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
