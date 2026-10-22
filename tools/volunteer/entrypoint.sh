#!/bin/sh
# The volunteer crawler loop: every two hours (with jitter) take this window's share, crawl it, push the bundle.
#
#   PLANWAT_LOGIN        your GitHub login, as listed in volunteers.json (required)
#   PLANWAT_FORK         <login>/<repository> to push the crawl branch to (default: <login>/PlanWAT)
#   PLANWAT_FORK_TOKEN   fine-grained token: Contents read/write on that fork only (required unless --dry-run)
#   PLANWAT_UPSTREAM     the project to read data and the registry from (default: kilerdevs/PlanWAT)
#   PLANWAT_ONCE=1       one pass, then exit (for cron or a first test)
#   PLANWAT_DRY_RUN=1    crawl and build the bundle, push nothing
#   PLANWAT_MAX_MINUTES  time budget of one pass (default 90)
set -eu

: "${PLANWAT_LOGIN:?set PLANWAT_LOGIN to your GitHub login}"
FORK="${PLANWAT_FORK:-$PLANWAT_LOGIN/PlanWAT}"
UPSTREAM="${PLANWAT_UPSTREAM:-kilerdevs/PlanWAT}"
WORK="${PLANWAT_WORK:-/work}"
MAX_MINUTES="${PLANWAT_MAX_MINUTES:-90}"
if [ "${PLANWAT_DRY_RUN:-0}" != 1 ] && [ -z "${PLANWAT_FORK_TOKEN:-}" ]; then
  echo 'set PLANWAT_FORK_TOKEN (or PLANWAT_DRY_RUN=1 for a test run)' >&2
  exit 2
fi

pass() {
  started=$(date -u +%Y-%m-%dT%H:%M:%S)
  echo "== pass at $started UTC as $PLANWAT_LOGIN"
  # Fresh public data every pass: what the site published is what this crawl compares against.
  rm -rf "$WORK/data"
  git clone -q --depth=1 --branch data "https://github.com/$UPSTREAM.git" "$WORK/data"
  curl_registry
  set +e
  extra=''
  if [ "${PLANWAT_DRY_RUN:-0}" = 1 ]; then extra='--dry-run'; fi
  python /app/tools/refresh/refresh.py --out "$WORK/data" --assign "$WORK/volunteers.json" --as "$PLANWAT_LOGIN" \
    --outcomes "$WORK/outcomes.json" --max-minutes "$MAX_MINUTES" --adaptive-hours 4 $extra
  code=$?
  set -e
  if [ "$code" -ne 0 ] && [ "$code" -ne 3 ] && [ "$code" -ne 4 ]; then
    echo "crawl failed (exit $code); nothing pushed"
    return 0
  fi
  python /app/tools/volunteer/bundle.py --data "$WORK/data" --outcomes "$WORK/outcomes.json" --fork "$FORK" $extra
}

curl_registry() {
  # The registry always comes from the project's volunteers branch, never from the fork: it decides who checks what.
  python - "$UPSTREAM" "$WORK/volunteers.json" <<'PY'
import sys, urllib.request
upstream, out = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(f'https://raw.githubusercontent.com/{upstream}/volunteers/volunteers.json', timeout=30) as r:
    data = r.read(1024 * 1024)
open(out, 'wb').write(data)
PY
}

while :; do
  pass || echo 'pass failed; trying again next window'
  if [ "${PLANWAT_ONCE:-0}" = 1 ]; then exit 0; fi
  # Two hours plus up to 20 minutes of jitter, so volunteers never hit a faculty site in lockstep.
  sleep $((7200 + $(od -An -N2 -tu2 /dev/urandom | tr -d ' ') % 1200))
done
