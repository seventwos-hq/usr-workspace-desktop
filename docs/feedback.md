# Share feedback broker

Panel 1 ("Share feedback") of the Desktop UI files **public** GitHub Issues in
`seventwos-hq/usr-workspace-desktop`. The Beta Board is retired; this repository
has no Beta Board code, so Issues is the single feedback channel. There is no LLM
classifier: the user picks a category.

## Flow

Renderer -> `window.electron.submitFeedback({ category, title, body })` -> main-process
`ipcMain.handle("submitFeedback")` (`apps/desktop/src/feedback.ts`) -> GitHub REST
`POST /repos/seventwos-hq/usr-workspace-desktop/issues`.

The result is `{ ok: true, url, number }` or `{ ok: false, error, message }` where
`error` is `invalid`, `rate_limited`, `unavailable` or `failed`.

## Categories and labels

| category   | label         |
| ---------- | ------------- |
| `bug`      | `bug`         |
| `idea`     | `enhancement` |
| `question` | `question`    |

## Security properties

- Repository and labels are fixed in the main process; the renderer cannot choose them.
- Only the main window may call the handler.
- Title (120) and body (5000) are length-limited; control characters are stripped.
- Because issues are public, tokens, JWTs, `Bearer` values and email addresses are
  redacted, and `@mentions` are defused. The UI must still tell the user the post is public.
- Rate limit: one per 30 s and 5 per hour per app run.
- Errors never include the token or GitHub response bodies.

## Token

The broker reads `SEVENTWOS_FEEDBACK_GITHUB_TOKEN` from the environment; without it
submissions return `unavailable`. Use a fine-grained token scoped to this one
repository with only **Issues: write**. A token shipped to end-user machines can be
extracted, so for public distribution front this with a server-side relay that holds
the token and keep this module as the client contract (follow-up, not implemented here).

## UI

The panel UI lives in the externally pinned web bundle (`apps/web` was removed), so it
is not part of this change; it should call `submitFeedback` above.
