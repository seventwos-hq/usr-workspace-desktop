#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
compose_file="$repo_root/apps/desktop/playwright/runner/compose.yaml"
artifact=${ELEMENT_DESKTOP_EXECUTABLE:-"$repo_root/apps/desktop/dist/linux-unpacked/seventwos-workspace-desktop"}

case "$artifact" in
  "$repo_root/apps/desktop/dist"/*) ;;
  *)
    echo "ERROR: Linux desktop executable must be under $repo_root/apps/desktop/dist: $artifact" >&2
    exit 2
    ;;
esac
container_artifact=/work/${artifact#"$repo_root"/}

test -x "$artifact" || {
  echo "ERROR: Linux desktop executable is missing or not executable: $artifact" >&2
  echo "Build or download the unpacked Linux artifact before running the UI smoke test." >&2
  exit 2
}

export PW_TAG=${PW_TAG:-linux-desktop-smoke}
export PLAYWRIGHT_TARGET=${PLAYWRIGHT_TARGET:-playwright/e2e/launch/launch.spec.ts}

docker compose -f "$compose_file" config --quiet
docker compose -f "$compose_file" run --rm -e ELEMENT_DESKTOP_EXECUTABLE="$container_artifact" ui-tests
