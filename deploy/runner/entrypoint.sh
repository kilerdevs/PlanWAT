#!/bin/sh
# Registers the runner once (RUNNER_TOKEN, a one-hour registration token from Settings -> Actions -> Runners),
# then runs it. The registration lives in the runner volume, so later starts need no token.
set -eu
cd /home/runner/actions-runner
if [ ! -f .runner ]; then
  if [ -z "${RUNNER_TOKEN:-}" ]; then
    echo 'not registered yet: set RUNNER_TOKEN in .env (Settings -> Actions -> Runners -> New self-hosted runner)' >&2
    exit 1
  fi
  ./config.sh --unattended --replace --url "${RUNNER_REPO_URL:-https://github.com/kilerdevs/PlanWAT}" \
    --token "$RUNNER_TOKEN" --name "${RUNNER_NAME:-$(hostname)}" --labels "${RUNNER_LABELS:-planwat}" --work _work
fi
exec ./run.sh
