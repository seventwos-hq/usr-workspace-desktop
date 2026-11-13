# Signing and dependency inventory

Static review of `develop` (no builds run). Scope: desktop code signing, the web bundle source, and other
upstream-controlled sources. Nothing here changes behaviour.

## 1. Code signing

| Platform | Mechanism in repo | Env vars / secrets read | Status |
|---|---|---|---|
| Windows | `apps/desktop/electron-builder.ts` sets `win.signtoolOptions` (sha256) | `SEVENTWOS_WORKSPACE_SIGNTOOL_SUBJECT_NAME` + `SEVENTWOS_WORKSPACE_SIGNTOOL_THUMBPRINT`; legacy fallbacks `ED_SIGNTOOL_SUBJECT_NAME`, `ED_SIGNTOOL_THUMBPRINT`. Signing is applied only if both are set. | Uses local signtool/cert-store (SHA-1 thumbprint). No Azure Trusted Signing or other remote signer configured. |
| macOS | `mac.hardenedRuntime`, entitlements plist, `strictVerify`, `gatekeeperAssess` | `APPLE_TEAM_ID` is read only to decide `resetAdHocDarwinSignature`. No notarize script/afterSign hook exists. | Not signable or notarizable as configured. Identity and notarization credentials are not wired up. |
| Linux | `deb`/`tar.gz` targets, no signing | `SEVENTWOS_WORKSPACE_DEBIAN_CHANGELOG` (legacy `ED_DEBIAN_CHANGELOG`) | No package or repo signing. gpg appears only for verifying the upstream bundle (section 2). |
| CI | `.github/workflows/build_desktop_*.yaml` | None. `CSC_IDENTITY_AUTO_DISCOVERY: false`; jobs are labelled "unsigned". No `secrets.*` used. | Artifacts are unsigned by design (see `apps/desktop/README.md`). |

Hardcoded Element signing identities: **none found** (no team ID, cert subject, thumbprint or publisher name in
the builder config, build config, entitlements or workflows). `build.json` appId is `org.seventwos.workspace.desktop`.

Residual notes:
- `electron_windows_cert_sn` (the subject name) is embedded in package metadata and used by `src/tray.ts` to derive a
  tray GUID. Changing the cert subject later changes that GUID on Windows (tray icon identity/pinning resets).
- Legacy `ED_*` aliases still exist; they are inherited names, not Element credentials.
- Source file headers still say "Element Creations Ltd" (licence headers; not an identity used for signing).

## 2. Web bundle (element-web)

Two paths exist:

- **CI path (`build_desktop_prepare.yaml`)**: requires an HTTPS URL and a SHA-256 digest as workflow inputs. It checks
  both against `scripts/upstream/validate_policy.py`, runs `curl` over HTTPS and `sha256sum --check`, then extracts the
  bundle, copies the Seventwos `config.json` and packs `webapp.asar`. The URL prefix allowed by policy is
  `https://github.com/element-hq/element-web/releases/download/`. **There is no gpg check in CI**; integrity relies
  on the digest being pinned by a human.
- **Local path (`apps/desktop/scripts/fetch-package.ts`, `pnpm run fetch <tag>`)**: downloads
  `https://github.com/element-hq/element-web/releases/download/<tag>/element-<tag>.tar.gz` and the `.asc` file,
  and runs `gpg --verify`. With `--importkey` it imports the key from the Element-hosted key URL in
  `PUB_KEY_URL`. A custom HTTPS URL disables verification (`verify = false`, "manually verified"). Note that
  `--importkey` trusts whatever the key URL serves at that moment (no fingerprint pin in the script).
- `validate_policy.py` pins the same key URL, the key file SHA-256 and the primary/signing fingerprints. These are
  used by policy validation and are not enforced by the build.

## 3. Inventory and recommendations

| Item | Current source | Risk | Recommendation |
|---|---|---|---|
| Web bundle tarball | GitHub release assets of `element-hq/element-web` | Upstream-controlled content (including any telemetry/default endpoints in the bundle); release asset can be re-uploaded. | Keep pinning an immutable tag plus SHA-256. Mirror the verified tarball to Seventwos storage and build from the mirror. Review bundle config defaults on every bump. |
| Bundle signature key | Element-hosted `.asc` key URL (`fetch-package.ts`, `validate_policy.py`) | Key fetched over HTTPS from a third-party host; `fetch-package.ts` does not pin the fingerprint. | Verify fingerprints in `validate_policy.py` before import, or vendor the key (SHA-256 already recorded) in the repo. Add a gpg verification step to CI in addition to the digest. |
| Custom bundle URL mode | `fetch-package.ts` arbitrary HTTPS URL | Skips signature verification. | Restrict use to documented cases, or require a digest argument. |
| Windows signing | Local cert via env vars (SUBJECT_NAME, THUMBPRINT) | No cert exists yet. SHA-1 thumbprint selects a local store cert, which is hard to use on CI runners. | Decide on a signing service (EV cert, Azure Trusted Signing, or similar) and add it in a reviewed change with protected environments. |
| macOS signing/notarization | Not implemented | Apps cannot be distributed outside dev. Gatekeeper blocks unsigned apps. | Add Developer ID identity and notarization (`APPLE_*` secrets under a Seventwos prefix) once an Apple Developer account exists. |
| Auto-update | `update_base_url` is a Seventwos URL in the checked-in configs; `enable_auto_update` is false | No Element update server is referenced. Risk only when enabled. | Keep disabled until the update service exists. Update feeds must be signed on Windows/macOS. |
| `@element-hq/*`, `@vector-im/*`, `@matrix-org/*` npm packages | npm registry via `pnpm-workspace.yaml`; workspace packages under `packages/` carry `@element-hq` names | Upstream supply chain; names are Element-branded. | Keep `pnpm-lock.yaml` frozen (CI already uses `--frozen-lockfile`). Renaming workspace packages is optional and affects imports. |
| `eslint-plugin-element-call` | `github:element-hq/element-call#main` in root `package.json` | Floating branch reference to a GitHub repo (dev dependency only). | Pin to a commit SHA or drop it. |
| `matrix-js-sdk` | `git+https://github.com/matrix-org/matrix-js-sdk.git` allowed in `pnpm-workspace.yaml` | Git dependency permitted for builds. | Confirm the lockfile resolves it to a commit; vendor if the dependency is needed. |
| `matrix-seshat` 5.0.0 (native) | npm; built by `hak` | Native code from an upstream publisher; built on the CI runner. | Keep exact pin; review at each bump. |
| Node download in Docker | `nodejs.org` in `dockerbuild/setup.sh` | Not Element-controlled; no checksum check visible. | Add SHA-256 verification (optional). |
| Source comments/changelog links | `github.com/element-hq/...` in comments, `CHANGELOG.md` | Non-functional. | Leave as is. Covered by the brand-guard baseline. |

No `packages.element.io` references were found in build or runtime code. The only Element-hosted URL used by the
build is the key URL noted above.

## 4. What Alvin must provide

Nothing below exists in the repo, and no values are recorded here.

- **Windows**: a code-signing certificate or signing-service account and its subject name; for the legacy path the
  SHA-1 thumbprint of the cert on the build machine. Decide whether to use a remote signing service.
- **macOS**: an Apple Developer Program account, a Developer ID Application certificate, the team ID, and notarization
  credentials (App Store Connect API key or Apple ID with app-specific password).
- **Linux**: optionally, a GPG key if `.deb`/tarball or apt-repo signing is wanted.
- **Update service**: hosting for `https://workspace.seventwos.org/desktop/update/` and the signing keys for it.
- **Bundle pinning**: the chosen upstream release tag plus the SHA-256 of the tarball to build.
- **Secret storage**: a protected CI environment to hold the above, using `SEVENTWOS_WORKSPACE_*` names.
