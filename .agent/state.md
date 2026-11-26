# State (25 Nov 2026 UTC)
Card 1911275418195854934. Forgejo PR #55 `ci/desktop-release-cdn`.
Done: rebased onto origin/main and dropped merge commit; strict SemVer prerelease handling; retained collision-safe `desktop-v*` tags; main-only workflow branch targets; regression tests added.
Verification: Forgejo run 3718 pr-check failed because pnpm skipped Electron install script; Vitest workers raced to download one shared runtime. electron is now allowed in pnpm allowBuilds; desktop Vitest PASS (18 files, 212 passed, 2 skipped; no lazy download). upstream_verify PASS; pr-preflight PASS.
Next: push PR #55 head and await rerun.
Planka helper unavailable on devserver.

Review fix (26 Nov 2026 UTC): addressed OCR blocking findings by fail-closing reusable build base selection, validating tag reachability, passing event values via env, and adding unconditional HEAD upstream-tree verification with regression coverage. Tests: 82 upstream policy passed; desktop 18 files, 212 passed, 2 skipped; workflow lint pass; upstream_verify PR-scope pass; pr-preflight pass.

Follow-up (26 Nov 2026 UTC): explicitly fetch non-local PR/merge-group base SHAs before upstream verification; added a regression contract test for fail-closed base selection, HEAD verification, and SHA fetch. Verification: 47 upstream/workflow policy tests pass; workflow lint pass; upstream_verify PR-scope pass.

Follow-up verification fix (26 Nov 2026 UTC): separated PR-diff allowlist validation from unconditional HEAD tree verification so unrelated workflow/script changes do not masquerade as an import; regression now includes an unrelated README change. Verification: 47 policy tests, workflow lint, PR-scope and --verify-head upstream checks pass.
