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

# Stage 2: unprivileged, read-only nginx that serves only the built files. Alpine's own nginx package, which takes nginx
# security releases sooner than the nginx.org images (2026-11-19: 1.30.7 here, nginxinc's images still on 1.30.6).
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

RUN apk upgrade --no-cache \
 && apk add --no-cache nginx \
 && rm -rf /etc/nginx/http.d /usr/share/nginx/html \
 && mkdir -p /usr/share/nginx/html
COPY --from=build --chown=root:root --chmod=0444 /src/deploy/nginx.conf /etc/nginx/nginx.conf
COPY --from=build --chown=root:root /site/ /usr/share/nginx/html/
RUN find /usr/share/nginx/html -type d -exec chmod 0555 {} + \
 && find /usr/share/nginx/html -type f -exec chmod 0444 {} +

USER nginx
EXPOSE 8080
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
# -e: the startup log goes to stderr too, not to the package's log directory on a read-only root
CMD ["nginx", "-e", "/dev/stderr", "-g", "daemon off;"]
