# State
Last updated: 2026-11-09 by Tobo

Snapshot: GitHub PR35 at 6c2874943c3857b93b2f28350c3b33c84fee8a68. Recheck later heads and results live.

## Current card: documentation integration correction

## Done
- Added AGENTS.md and .agent/state.md
- Clarified independent review and Forgejo versus production release authority; supplied required fetch target/config arguments.
- Forgejo PR2 and PR3 corrections were independently approved, normally merged, and forwarded to GitHub PR35; PR3 documents the separate Git hook installation step.

## Next
- Complete GitHub PR35 through exact-head required CI, native Copilot review and independently verified finding closure; then verify Pages and Forgejo content reconciliation.
- Verify install/build/test commands once dependencies are installed.

## Blocked
- GitHub PR35 integration and subsequent Pages verification remain incomplete at this snapshot; the earlier CodeQL download failure is no longer an active blocker.

## Notes
- CI is GitHub Actions only; no Forgejo workflows.
- Local commands in AGENTS.md remain unverified; no local build was run for this correction.
- Web bundle is fetched from an exact upstream tag/URL; apps/web intentionally absent.
- Historical CodeQL JavaScript/TypeScript download at e53ca2e9f247c22e4597e8b93715ed6641380831 failed with HTTP 504. CodeQL run 42503614607 succeeded for JavaScript/TypeScript, Python and Actions at the snapshot head above.
- Required checks passed at the snapshot head: runs 42503614363, 42503614526 and 42503614583. These results do not validate any later correction commit.
