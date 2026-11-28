#!/bin/bash
set -euo pipefail

export DISPLAY=:99
export XDG_RUNTIME_DIR=/tmp/runtime
mkdir -p "$XDG_RUNTIME_DIR" /tmp/runner
chmod 0700 "$XDG_RUNTIME_DIR"

Xvfb "$DISPLAY" -screen 0 1280x720x24 -nolisten tcp &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
xdpyinfo -display "$DISPLAY" >/dev/null

exec pnpm -C /work/apps/desktop exec playwright test --reporter=line "$@"
