# State (20 Nov 06:05 UTC)
Card 1910588255833687729. Patch-layer rework of old PR34 delta on v1.12.35.
Done: 6 conflicts resolved in scratch merge (~/work/tmp/w/m, v1.12.28+delta->v1.12.35). Resolution: take upstream for SecurityManager.ts, CreateSecretStorageDialog.tsx (cryptoSetup extension code dropped: upstream removed ModuleRunner extension), package.json (upstream sentry/deps; module-api + crypto-wasm pins dropped), ProxiedModuleApi.ts deleted upstream (accepted); keep our values in config.sample.json; keep our href in SetupEncryptionToast.tsx on upstream Link.
Result: .seventwos/patches/web-delta.patch (23 files, +56/-80), verified: git apply --check clean on pristine v1.12.35 tarball (sha256 5f153456...e945) in ~/work/tmp/v35.
NOT done: lint/type-check/unit tests (apps/web not in this branch; needs pristine import, PR#40 blocked by ocr-gate size cap; pnpm install+build exceeds 2 GB local cap -> CI). No push, no PR.
Next: 1) pristine v1.12.35 import commit; 2) build-time patch apply script + path-map/policy entry; 3) CI build + brand audit + attribution check; then push + PR "WIP: feat: rebuild desktop web layer on upstream 1.12.35".
