/*
Copyright 2024 New Vector Ltd.
Copyright 2023 The Matrix.org Foundation C.I.C.

SPDX-License-Identifier: AGPL-3.0-only OR GPL-3.0-only OR LicenseRef-Element-Commercial
Please see LICENSE files in the repository root for full details.
*/

// @vitest-environment happy-dom

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "test-utils-rtl";

import SdkConfig from "../../../SdkConfig";
import FeedbackDialog from "./FeedbackDialog";

describe("FeedbackDialog", () => {
    it("should respect feedback config", () => {
        SdkConfig.put({
            feedback: {
                existing_issues_url: "http://existing?foo=bar",
                new_issue_url: "https://new.issue.url?foo=bar",
            },
        });

        const { asFragment } = render(<FeedbackDialog onFinished={vi.fn()} />);
        expect(asFragment()).toMatchSnapshot();
    });

    it("sends feedback through the desktop issue broker with a public notice", async () => {
        const submit = vi.fn().mockResolvedValue({ ok: true });
        window.electron = { submitFeedback: submit } as unknown as typeof window.electron;
        const onFinished = vi.fn();
        const { getByText, container } = render(<FeedbackDialog onFinished={onFinished} />);
        expect(getByText(/public GitHub issue/)).toBeTruthy();
        fireEvent.change(container.querySelector("#feedbackComment")!, { target: { value: "Great app\nmore detail" } });
        fireEvent.click(getByText("Send feedback"));
        expect(submit).toHaveBeenCalledWith({ category: "idea", title: "Great app", body: "Great app\nmore detail" });
        expect(onFinished).toHaveBeenCalled();
        window.electron = undefined;
    });
});
