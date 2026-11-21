# Seventwos Workspace for Desktop

Seventwos Workspace for Desktop is the desktop client for the Seventwos workspace. It is built on top of a fork of [Element Web](https://github.com/element-hq/element-web) and is being evolved for people and agents to communicate and collaborate over [Matrix](https://matrix.org/).

The project retains Element's desktop approach: a TypeScript and React application packaged for the desktop with [Electron](https://www.electronjs.org/), communicating with Matrix through the [Matrix JS SDK](https://github.com/matrix-org/matrix-js-sdk). End-to-end encryption is handled by the Matrix Rust crypto stack compiled to WebAssembly, so the desktop client shares its cryptographic core with the iOS and Android clients while the application layer remains web technology.

## Relationship to the iOS and Android workspaces

[Seventwos Workspace for iOS](https://github.com/seventwos-hq/usr-workspace-ios) and [Seventwos Workspace for Android](https://github.com/seventwos-hq/usr-workspace-android) are forks of Element X, which are native clients built directly on the [Matrix Rust SDK](https://github.com/matrix-org/matrix-rust-sdk).

Element does not publish an Element X desktop client. The Element desktop application is maintained inside the Element Web monorepo and is built on the Matrix JS SDK, so this repository forks Element Web rather than Element X. The three workspaces therefore share product intent and a common Matrix protocol foundation, but not a single application codebase.

## Repository layout and where we work

This repository is a monorepo inherited from Element Web and governed by `.seventwos/upstream-path-map.json` (enforced by `scripts/upstream/validate_policy.py` and `scripts/upstream/upstream_verify.py`). Paths are separated into three explicit tiers so Seventwos work layers cleanly on top of upstream without polluting imported code:

### 1. Seventwos-owned layer (`protected-divergence` — where we work)

- `apps/desktop/seventwos.com/` — Seventwos brand identity, endpoints (`workspace.seventwos.com`), themes, feature flags, and build/runtime configuration (`preview/config.json`, `preview/build.json`, `release/config.json`, `release/build.json`).
- `modules/` — Seventwos-authored UI and product modules (`banner`, `restricted-guests`, `widget-lifecycle`, `widget-toggles`) built on the Element Web Module API (`@element-hq/element-web-module-api`). **Default rule**: implement new Seventwos UI and product features in `modules/` or `apps/desktop/seventwos.com/` first.
- `.seventwos/` — selective upstream synchronisation policy (`upstream-policy.json`), path map (`upstream-path-map.json`), invariants (`upstream-invariants.json`), pinned upstream release (`upstream-pin.json`), selection state (`upstream-state.json`), immutable evidence (`.seventwos/evidence/`), and append-only decision ledger (`upstream-ledger.jsonl`), plus any explicit web-layer patch series under `.seventwos/patches/` for changes that the Module API or `config.json` cannot express.
- `.github/workflows/` and `scripts/upstream/` — repository-owned CI, policy validation, and release automation.

### 2. Selective-review desktop shell (`selective-review`)

- `apps/desktop/` (outside `apps/desktop/seventwos.com/`) — the Electron desktop application shell (formerly `element-desktop`). Keep Seventwos shell changes minimal and surgical so upstream Electron/desktop fixes can be reviewed and adopted individually.

### 3. Read-only upstream imports (`upstream-import-only` — do not edit in place)

- `packages/` (and `apps/web/` when present as a pinned source import) — must match a byte-identical import of the pinned upstream Element Web release tag recorded in `.seventwos/upstream-pin.json` (verified by `scripts/upstream/upstream_verify.py`). Never hand-edit files under `packages/` or `apps/web/`; layer Seventwos changes via `modules/`, `apps/desktop/seventwos.com/`, or `.seventwos/patches/`.

## Selective upstream synchronization

This repository is a desktop shell plus a separately pinned Element Web release, not a source fork that follows
upstream branch history. Repository-owned policy under [`.seventwos/`](https://github.com/seventwos-hq/usr-workspace-desktop/tree/main/.seventwos) defines the upstream path map,
invariants, current selection state, immutable evidence, and append-only decision ledger.

The upstream assessment workflow is read-only and report-only: it observes the `element-hq/element-web` `develop`
tip and reports candidate state without applying changes, merging commits, or changing bundle selection. It runs
for every pull request targeting `main` and merge-queue check request, as well as weekly and manual assessments.
Pull requests and merge groups validate the append-only ledger against their event's base SHA. A bundle
cannot be packaged until its exact release tag, HTTPS URL, SHA-256 digest, detached signature, provenance, rollback
record, and required runtime evidence have passed human review. Required runtime evidence covers denied
capabilities, network destinations, visual identity, and migration of existing Element and Riot profiles.

The seeded `v1.12.27` record is baseline evidence, not an approved selection. Its product intent and runtime evidence
remain pending human review, so packaging is intentionally blocked until the policy state names an approved bundle.
`apps/web` may change only by a verified byte-identical import of the pinned release, moving branch bundles are forbidden, and Seventwos product divergence must not be
overwritten during upstream assessment.

## Status

This repository is in transition from its Element Web foundation to a separately authored Seventwos application layer.

The current code includes inherited Element Web and Element Desktop code, branding, and configuration. This fork redistributes that code under the GNU Affero General Public License v3 and must not be represented as an independently authored Seventwos implementation. The transition will replace the inherited application layer with Seventwos code while retaining the desktop client architecture.

## Architecture

The intended desktop implementation includes:

- TypeScript and React.
- Electron packaging for macOS, Windows, and Linux.
- Matrix JS SDK integration.
- Client-side Matrix end-to-end encryption through the Rust crypto stack compiled to WebAssembly.
- Local encrypted search indexing through Seshat.
- Desktop notifications for encrypted messages.

Element Web is the upstream foundation and architectural reference for this workspace, not the target product identity.

## Repository scope

This is the product repository for Seventwos Workspace for Desktop. It is the source of truth for the desktop application code, Electron packaging and platform integrations, build and test configuration, and release preparation.

Changes in this repository should directly support the desktop client. Shared services and cross-platform product material are maintained separately; the origins and licensing of upstream-derived code are documented below.

## Provenance and licence

This repository began as a fork of Element Web and is now maintained as Seventwos Workspace for Desktop.

Copyright (c) 2014 - 2017 OpenMarket Ltd.

Copyright (c) 2017 Vector Creations Ltd.

Copyright (c) 2017 - 2025 New Vector Ltd.

These upstream copyright notices are retained in recognition of the work on which this fork is based.

We license the repository-owned code under the GNU Affero General Public License v3 only. See [LICENSE-AGPL-3.0](https://github.com/seventwos-hq/usr-workspace-desktop/blob/main/LICENSE-AGPL-3.0) for the applicable terms. Third-party dependencies remain under their respective licences.

Our modifications and newly authored repository code use AGPL-3.0-only. When we distribute a modified version or make one available for users to interact with over a network, we provide the corresponding source as required by the AGPL.

