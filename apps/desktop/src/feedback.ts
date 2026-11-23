/*
Copyright 2026 Seventwos

SPDX-License-Identifier: AGPL-3.0-only
Please see LICENSE files in the repository root for full details.
*/

/**
 * Feedback broker: turns "Share feedback" submissions from the renderer into public GitHub Issues
 * in the fixed target repository. The renderer never chooses the repository, labels or token.
 */

export const FEEDBACK_REPO = "seventwos-hq/usr-workspace-desktop";
export const FEEDBACK_TOKEN_ENV = "SEVENTWOS_FEEDBACK_GITHUB_TOKEN";

export const MAX_TITLE_LENGTH = 120;
export const MAX_BODY_LENGTH = 5000;
const MIN_INTERVAL_MS = 30_000;
const MAX_PER_HOUR = 5;
const REQUEST_TIMEOUT_MS = 15_000;

// Only labels that already exist in the repository; unknown labels would be auto-created.
const CATEGORY_LABELS = {
    bug: "bug",
    idea: "enhancement",
    question: "question",
} as const;

export type FeedbackCategory = keyof typeof CATEGORY_LABELS;

export interface FeedbackInput {
    category: FeedbackCategory;
    title: string;
    body: string;
}

export interface FeedbackContext {
    appVersion: string;
    platform: string;
}

export type FeedbackResult =
    | { ok: true; url: string; number: number }
    | { ok: false; error: "invalid" | "rate_limited" | "unavailable" | "failed"; message: string };

// Issues are public, so strip credentials and contact details a user may paste by accident.
const REDACTIONS: [RegExp, string][] = [
    [/\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}/g, "[redacted token]"],
    [/\bsy[a-z]_[A-Za-z0-9_-]{16,}/g, "[redacted token]"],
    [/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}/gi, "$1 [redacted]"],
    [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*/g, "[redacted token]"],
    [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[redacted email]"],
];

function clean(text: string): string {
    let out = text
        // eslint-disable-next-line no-control-regex
        .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
        .replace(/\r\n?/g, "\n")
        .trim();
    for (const [pattern, replacement] of REDACTIONS) out = out.replace(pattern, replacement);
    // Prevent @mentions from notifying arbitrary users.
    return out.replace(/@(?=[A-Za-z0-9])/g, "@\u200B");
}

export function validateFeedback(input: unknown): FeedbackInput | null {
    if (typeof input !== "object" || input === null) return null;
    const { category, title, body } = input as Record<string, unknown>;
    if (typeof category !== "string" || !Object.hasOwn(CATEGORY_LABELS, category)) return null;
    if (typeof title !== "string" || typeof body !== "string") return null;
    if (title.length > MAX_TITLE_LENGTH * 2 || body.length > MAX_BODY_LENGTH * 2) return null;
    const cleanTitle = clean(title).replace(/\s+/g, " ");
    const cleanBody = clean(body);
    if (!cleanTitle || !cleanBody) return null;
    if (cleanTitle.length > MAX_TITLE_LENGTH || cleanBody.length > MAX_BODY_LENGTH) return null;
    return { category: category as FeedbackCategory, title: cleanTitle, body: cleanBody };
}

export function renderIssue(
    input: FeedbackInput,
    context: FeedbackContext,
): { title: string; body: string; labels: string[] } {
    return {
        title: input.title,
        body: [
            input.body,
            "",
            "---",
            `Submitted via Desktop Share feedback (${context.platform}, v${clean(context.appVersion)}).`,
        ].join("\n"),
        labels: [CATEGORY_LABELS[input.category]],
    };
}

export class FeedbackBroker {
    private sent: number[] = [];

    public constructor(
        private readonly getToken: () => string | undefined = () => process.env[FEEDBACK_TOKEN_ENV],
        private readonly fetchFn: typeof fetch = fetch,
        private readonly now: () => number = Date.now,
    ) {}

    public async submit(raw: unknown, context: FeedbackContext): Promise<FeedbackResult> {
        const input = validateFeedback(raw);
        if (!input) {
            return { ok: false, error: "invalid", message: "Feedback is missing or too long." };
        }
        const token = this.getToken();
        if (!token) {
            return { ok: false, error: "unavailable", message: "Feedback is not configured on this build." };
        }

        const now = this.now();
        this.sent = this.sent.filter((t) => now - t < 3_600_000);
        const last = this.sent[this.sent.length - 1];
        if (this.sent.length >= MAX_PER_HOUR || (last !== undefined && now - last < MIN_INTERVAL_MS)) {
            return { ok: false, error: "rate_limited", message: "Please wait before sending more feedback." };
        }

        try {
            const res = await this.fetchFn(`https://api.github.com/repos/${FEEDBACK_REPO}/issues`, {
                method: "POST",
                headers: {
                    "Accept": "application/vnd.github+json",
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "seventwos-workspace-desktop",
                },
                body: JSON.stringify(renderIssue(input, context)),
                signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
            });
            if (!res.ok) {
                return { ok: false, error: "failed", message: `GitHub rejected the request (${res.status}).` };
            }
            const data = (await res.json()) as { html_url?: unknown; number?: unknown };
            if (typeof data.html_url !== "string" || typeof data.number !== "number") {
                return { ok: false, error: "failed", message: "Unexpected response from GitHub." };
            }
            this.sent.push(now);
            return { ok: true, url: data.html_url, number: data.number };
        } catch {
            return { ok: false, error: "failed", message: "Could not reach GitHub." };
        }
    }
}
