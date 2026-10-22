# The volunteer crawler (docs/WOLONTARIUSZE.md). Build context: the repository root.
#   docker build -f tools/volunteer/Dockerfile -t planwat-crawler .
# Released images are published as ghcr.io/kilerdevs/planwat-crawler with a build provenance attestation
# (crawler-image.yml); check one with `gh attestation verify oci://<image> --repo kilerdevs/PlanWAT`.
FROM python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/work

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir curl_cffi==0.13.0 pymupdf==1.28.2 \
 && useradd -r -u 10003 -d /work -s /usr/sbin/nologin crawler

WORKDIR /app
# Only what the crawl needs: the crawler, the volunteer tools, the site's validator and the version.
COPY package.json build.py profiles.py ./
COPY tools/refresh/ tools/refresh/
COPY tools/volunteer/ tools/volunteer/
RUN chmod 0555 tools/volunteer/entrypoint.sh && find /app -type d -exec chmod 0555 {} + \
 && find /app -type f ! -name entrypoint.sh -exec chmod 0444 {} +

USER 10003:10003
VOLUME /work
ENTRYPOINT ["/app/tools/volunteer/entrypoint.sh"]
