#!/bin/sh
# The volunteer crawler image's entrypoint (docs/WOLONTARIUSZE.md). Everything lives in runner.py:
#
#   run (default)  one pass per two-hour assignment window, forever
#   once           one pass now, then exit (PLANWAT_ONCE=1 does the same)
#   status         what the crawler is doing and what the coordinator said about its last bundle
#   health         the HEALTHCHECK
#   setup          the first-run wizard: login, fork, token, faculties, .env
#   doctor         every check, each with what to do about it
set -eu
if [ "$#" -eq 0 ]; then
  set -- run
fi
exec python /app/tools/volunteer/runner.py "$@"
