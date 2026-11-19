# Self-hosted deployment (the primary target is GitHub Pages; see docs/DEPLOYMENT.md).
# Base images are digest-pinned: a moving tag must not change what ships. Dependabot proposes bumps.

# Stage 1: build the static site from the timetables and pin its CSP hashes into nginx.conf.
FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd AS build
WORKDIR /src
COPY build.py profiles.py ./
COPY src/ src/
COPY timetables/ timetables/
COPY deploy/nginx.conf deploy/nginx.conf
# Terms are picked for the build date: rebuild the image when a new term starts.
RUN python3 build.py --out /site --nginx deploy/nginx.conf

# Stage 2: unprivileged, read-only nginx that serves only the built files.
FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03

USER root
RUN apk upgrade --no-cache \
 && rm -f /etc/nginx/conf.d/*.conf /docker-entrypoint.d/* \
 && rm -rf /usr/share/nginx/html/*
COPY --from=build --chown=root:root --chmod=0444 /src/deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=root:root /site/ /usr/share/nginx/html/
RUN find /usr/share/nginx/html -type d -exec chmod 0555 {} + \
 && find /usr/share/nginx/html -type f -exec chmod 0444 {} +

USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
