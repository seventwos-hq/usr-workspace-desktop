#!/usr/bin/env bash
set -euo pipefail
channel=${1:?stable or beta}; version=${2:?version}; public_key=${3:-public.pem}
[[ "$channel" == stable || "$channel" == beta ]]
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ ]]
: "${AZURE_STORAGE_ACCOUNT:?}" "${AZURE_STORAGE_CONTAINER:?}"
az storage blob download --account-name "$AZURE_STORAGE_ACCOUNT" --auth-mode login --container-name "$AZURE_STORAGE_CONTAINER" --name "v$version/manifest-$channel.json" --file rollback.json --overwrite true --only-show-errors
python3 scripts/release/manifest.py verify --manifest rollback.json --key "$public_key" --version "$version" --channel "$channel"
mapfile -t blobs < <(python3 - rollback.json <<'PY'
import json, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
print(*(entry["url"].rsplit("/", 1)[-1] for entry in manifest["release"].values()), sep="\n")
PY
)
for filename in "${blobs[@]}"; do
    blob="v$version/$filename"
    [[ "$(az storage blob exists --account-name "$AZURE_STORAGE_ACCOUNT" --auth-mode login --container-name "$AZURE_STORAGE_CONTAINER" --name "$blob" --query exists -o tsv --only-show-errors)" == true ]] || {
        printf 'rollback blob missing: %s\n' "$blob" >&2
        exit 1
    }
done
az storage blob upload --account-name "$AZURE_STORAGE_ACCOUNT" --auth-mode login --container-name "$AZURE_STORAGE_CONTAINER" --name "manifest-$channel.json" --file rollback.json --overwrite true --content-cache-control "no-cache, max-age=0" --only-show-errors
