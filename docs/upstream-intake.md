# Upstream intake (Element -> Seventwos Workspace Desktop)

How to pull a new Element release into this fork safely. Template for the android/ios forks.

Desktop packages a pre-built Element Web bundle (`apps/desktop/scripts/fetch-package.ts`); `apps/web` is removed and must not be restored. Read `AGENTS.md` and `.seventwos/upstream-policy.json` first; `.seventwos/upstream-ledger.jsonl` is append-only.

## Procedure

1. Fetch upstream tag (unverified; add remote once):
   `git remote add upstream <element-upstream-url>` ; `git fetch upstream --tags` (unverified)
2. Branch off develop:
   `git fetch origin && git checkout -b intake/<upstream-tag> origin/develop` (unverified)
3. Merge the tag: `git merge <upstream-tag>` (unverified). Resolve conflicts keeping Seventwos names/ids/config; never restore `apps/web`.
4. Re-apply and verify branding:
   - `scripts/brand-guard.sh` must print `brand-guard: OK` (run on current develop: OK, exit 0).
   - New legitimate matches only: justify, then `scripts/brand-guard.sh --update` (regenerates baseline in `.brand-guard-allowlist`) and review the diff (unverified). Prefer rebranding over raising a baseline.
   - Check `apps/desktop/package.json` (`name` seventwos-workspace-desktop, `productName` "Seventwos Workspace"), appId in `apps/desktop/electron-builder.ts`, and default homeserver in `apps/desktop/seventwos.org/release/config.json`.
5. Quick checks (all unverified): `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm test:unit`, `python3 scripts/upstream/validate_policy.py --help` for policy validation options. Only `documentation/` is OKF-validated (`scripts/okf/validate_okf_markdown.py --changed`); files in `docs/` need no frontmatter.
6. Push `intake/<upstream-tag>` and open a PR into `develop`. Do not merge without review; do not tag or release.

## Invariants (must hold after every intake)

- App name/ids stay Seventwos (`seventwos-workspace-desktop`, "Seventwos Workspace", Seventwos appId).
- Default homeserver is `workspace.seventwos.org` (`apps/desktop/seventwos.org/release/config.json`, `apps/desktop/src/config.ts`).
- `scripts/brand-guard.sh` passes.
- No `element.io` / `riot.im` / `app.element.*` URLs outside `.brand-guard-allowlist`.
- `apps/web` stays absent.
- Bundle selection uses an immutable release tag, HTTPS URL and SHA-256 (`.seventwos/upstream-invariants.json`).
- Ledger entries are never edited, reordered or removed.
