#!/bin/sh
# Registers the runner once (RUNNER_TOKEN, a one-hour registration token from Settings -> Actions -> Runners),
# then runs it. The registration lives in the runner volume, so later starts need no token.
#
# A host without a volume (the Northflank container, deploy/runner/README.md) keeps it in RUNNER_STATE instead: the
# registration files as a base64 tar.gz, set as a secret variable once the runner is registered
# (`planwat-runner state` prints it). A start that finds no registration restores it from there and needs no token.
set -eu
cd /home/runner/actions-runner
FILES='.runner .credentials .credentials_rsaparams .env .path'

if [ "${1:-}" = state ]; then
  # The registration, for RUNNER_STATE: one line on stdout, nothing else.
  tar -cz $FILES | base64 -w0
  echo
  exit 0
fi

if [ ! -f .runner ] && [ -n "${RUNNER_STATE:-}" ]; then
  if printf '%s' "$RUNNER_STATE" | base64 -d | tar -xz $FILES 2>/dev/null && [ -f .runner ]; then
    echo 'registration restored from RUNNER_STATE'
  else
    rm -f $FILES
    echo 'RUNNER_STATE does not hold a registration; registering with RUNNER_TOKEN instead' >&2
  fi
fi
if [ ! -f .runner ]; then
  if [ -z "${RUNNER_TOKEN:-}" ]; then
    echo 'not registered yet: set RUNNER_TOKEN in .env (Settings -> Actions -> Runners -> New self-hosted runner)' >&2
    exit 1
  fi
  ./config.sh --unattended --replace --url "${RUNNER_REPO_URL:-https://github.com/kilerdevs/PlanWAT}" \
    --token "$RUNNER_TOKEN" --name "${RUNNER_NAME:-$(hostname)}" --labels "${RUNNER_LABELS:-planwat}" --work _work
fi
exec ./run.sh
