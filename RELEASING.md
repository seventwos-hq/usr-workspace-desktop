# Releasing the desktop app

This document describes how desktop releases are versioned, verified, signed,
delivered and, when needed, rolled back. Items marked **(planned)** are not
built yet.

## 1. Versioning

- The app follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.
  - MAJOR: breaking changes (data, configuration or behaviour).
  - MINOR: backwards-compatible features.
  - PATCH: fixes, including security fixes.
- The bundled upstream web client version is tracked in
  `.seventwos/upstream-state.json`. Every release note states the app version
  and the upstream web client version it bundles.

## 2. Channels

| Channel | Audience | Purpose |
| --- | --- | --- |
| `beta` | Allowlisted testers | Early validation of every release |
| `stable` | All customers | Verified releases |

- Every release goes to `beta` first and stays there for at least 3 days with
  no new crash or sign-in errors before it is promoted to `stable`.
- A security fix may shorten the beta period only with release-owner approval.

## 3. Gates before a release tag

A release tag is created only when all of these are met:

1. CI is green.
2. Code review is complete with no open findings.
3. The design-language check is done, with screenshots attached.
4. The smoke-test checklist passes (see section 12):
   - fresh install
   - upgrade from the previous version
   - sign-in
   - send and receive an encrypted message
   - place and receive a call
   - profile load
5. A customer-facing changelog is written.

## 4. Approval

- The team may prepare release candidates and beta builds.
- Every `stable` release tag requires approval from the release owner.

## 5. Signing

- Windows builds are signed with Azure Trusted Signing **(planned)**.
- macOS builds are signed with an Apple Developer ID and notarized **(planned)**.
- Signing keys and credentials live only in a key vault or in CI secrets.
- CI signs release builds. Nobody signs builds on a personal machine, and
  keys are never committed to the repository.

## 6. Auto-update (planned)

- The app's `update_base_url` points at our own update server, backed by cloud
  object storage behind a CDN. The domain is yet to be decided.
- Windows and macOS use Squirrel feeds; Linux uses an apt repository.
- `beta` and `stable` have separate feeds.
- Updates download in the background and are installed silently when the app
  restarts.

## 7. Staged rollout

- A `stable` release first goes to about 10% of users.
- If crash, sign-in and update metrics hold, it goes to 100% after 48 hours.
- If metrics regress, pause the rollout and follow section 8.

## 8. Rollback

- Keep the last 3 signed builds available.
- To pull a bad release, repoint the feed to the previous good build. Never
  delete a published build.
- Write a short incident note for every rollback: what happened, impact, and
  the fix.

## 9. Customer communication

- Each release has an entry on the public release notes page and in the app's
  "What's new" view.
- Breaking changes are announced to organisation admins at least 2 weeks
  before release.

## 10. Upstream updates

- Upstream security releases are merged monthly.
- Critical upstream advisories are merged and released within 72 hours.
- After each merge, update `.seventwos/upstream-state.json` and the release
  notes with the new upstream version.

## 11. Platform order

- Windows and Linux ship first.
- macOS builds remain `beta` / tester-only until notarization is available
  **(planned)**.

## 12. Smoke tests

- Desktop smoke tests use Playwright against the packaged Electron app.
- The run posts screenshots of each step so reviewers can check the result
  against the design language.
- The checklist covers install, upgrade, sign-in, encrypted messaging, calls
  and profile load.

## Release checklist

- [ ] Version bumped; upstream web client version recorded
- [ ] CI green and review complete
- [ ] Design-language check and screenshots attached
- [ ] Smoke tests pass
- [ ] Changelog written
- [ ] Released to `beta`; 3 days with no new crash or sign-in errors
- [ ] Release-owner approval for the `stable` tag
- [ ] Staged rollout: 10%, then 100% after 48 hours
- [ ] Release notes and "What's new" published
