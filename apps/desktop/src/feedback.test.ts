/*
Copyright 2026 Seventwos

SPDX-License-Identifier: AGPL-3.0-only
Please see LICENSE files in the repository root for full details.
*/

import { describe, expect, it, vi } from "vitest";

import { FeedbackBroker, validateFeedback, renderIssue, MAX_BODY_LENGTH } from "./feedback.js";

const ctx = { appVersion: "1.2.3", platform: "win32" };
const good = { category: "bug", title: "Crash on start", body: "It crashes." };

function okFetch(): typeof fetch {
    return vi.fn(async () =>
        Response.json({ html_url: "https://github.com/seventwos-hq/usr-workspace-desktop/issues/9", number: 9 }),
    ) as unknown as typeof fetch;
}

describe("validateFeedback", () => {
    it("rejects bad shapes, categories and oversize input", () => {
        expect(validateFeedback(null)).toBeNull();
        expect(validateFeedback({ ...good, category: "constructor" })).toBeNull();
        expect(validateFeedback({ ...good, title: "  " })).toBeNull();
        expect(validateFeedback({ ...good, body: "x".repeat(MAX_BODY_LENGTH + 1) })).toBeNull();
        expect(validateFeedback({ ...good, title: 5 })).toBeNull();
    });

    it("redacts secrets and emails and defuses mentions", () => {
        const out = validateFeedback({
            ...good,
            body: "mail me a@b.com token ghp_abcdefghijklmnopqrstuvwx cc @octocat",
        });
        expect(out?.body).not.toContain("a@b.com");
        expect(out?.body).not.toContain("ghp_");
        expect(out?.body).toContain("@\u200Boctocat");
    });
});

describe("FeedbackBroker", () => {
    it("posts to the fixed repo with the token and mapped label", async () => {
        const fetchFn = okFetch();
        const broker = new FeedbackBroker(
            () => "tok",
            fetchFn,
            () => 1_000_000,
        );
        const res = await broker.submit({ ...good, category: "idea", repo: "evil/repo" }, ctx);
        expect(res).toEqual({ ok: true, url: expect.stringContaining("/issues/9"), number: 9 });
        const [url, init] = vi.mocked(fetchFn).mock.calls[0];
        expect(url).toBe("https://api.github.com/repos/seventwos-hq/usr-workspace-desktop/issues");
        expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer tok");
        expect(JSON.parse(init!.body as string).labels).toEqual(["enhancement"]);
    });

    it("is unavailable without a token and never calls GitHub", async () => {
        const fetchFn = okFetch();
        const res = await new FeedbackBroker(() => undefined, fetchFn).submit(good, ctx);
        expect(res).toMatchObject({ ok: false, error: "unavailable" });
        expect(fetchFn).not.toHaveBeenCalled();
    });

    it("rate limits rapid submissions", async () => {
        let t = 1_000_000;
        const broker = new FeedbackBroker(
            () => "tok",
            okFetch(),
            () => t,
        );
        expect((await broker.submit(good, ctx)).ok).toBe(true);
        expect(await broker.submit(good, ctx)).toMatchObject({ error: "rate_limited" });
        t += 31_000;
        expect((await broker.submit(good, ctx)).ok).toBe(true);
    });

    it("does not leak the token on GitHub errors", async () => {
        const fetchFn = vi.fn(async () => new Response("bad tok", { status: 403 })) as unknown as typeof fetch;
        const res = await new FeedbackBroker(() => "tok", fetchFn).submit(good, ctx);
        expect(res).toMatchObject({ ok: false, error: "failed" });
        expect(JSON.stringify(res)).not.toContain("tok");
    });
});

describe("renderIssue", () => {
    it("appends app context", () => {
        const r = renderIssue({ category: "bug", title: "t", body: "b" }, ctx);
        expect(r.body).toContain("win32, v1.2.3");
    });
});
