# State
Last updated: 2026-11-08 by Tobo

## Current card: documentation integration correction

## Done
- Added AGENTS.md and .agent/state.md
- Clarified independent review and Forgejo versus production release authority; supplied required fetch target/config arguments.

## Next
- Independent review of the correction before Forgejo merge and GitHub PR35 integration.
- Verify install/build/test commands once dependencies are installed.

## Blocked
- Correction not yet independently reviewed; latest-head native Copilot review and required CI remain integration gates.
- Additional CodeQL JavaScript/TypeScript analysis at e53ca2e9f247c22e4597e8b93715ed6641380831 failed during CLI download with HTTP 504; no successful analysis claimed.

## Notes
- CI is GitHub Actions only; no Forgejo workflows.
- Local commands in AGENTS.md remain unverified; no local build was run for this correction.
- Web bundle is fetched from an exact upstream tag/URL; apps/web intentionally absent.
- GitHub PR35 required checks passed at e53ca2e9f247c22e4597e8b93715ed6641380831; this does not validate the correction commit.
