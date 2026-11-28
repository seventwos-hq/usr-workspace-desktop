"""Regression contracts for the isolated Linux desktop UI runner."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "apps/desktop/playwright/runner/compose.yaml"


class DesktopUiRunnerConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Compose accepts JSON because JSON is a strict subset of YAML. Keeping
        # the fixture in this form lets the lint job use only Python stdlib.
        cls.config = json.loads(COMPOSE.read_text())
        cls.runner = cls.config["services"]["ui-tests"]

    def test_external_network_is_impossible(self) -> None:
        self.assertEqual(self.runner["networks"], ["isolated"])
        self.assertIs(self.config["networks"]["isolated"]["internal"], True)
        self.assertEqual(self.runner["ports"], [])
        self.assertNotIn("network_mode", self.runner)

    def test_runner_is_hardened(self) -> None:
        self.assertTrue(self.runner["read_only"])
        self.assertEqual(self.runner["user"], "1000:1000")
        self.assertEqual(self.runner["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", self.runner["security_opt"])
        self.assertEqual(self.runner["ipc"], "private")

    def test_source_and_artifact_are_read_only(self) -> None:
        self.assertTrue(all(mount["read_only"] is True for mount in self.runner["volumes"]))
        self.assertEqual(
            [mount["source"] for mount in self.runner["volumes"]],
            ["../../../..", "../../dist"],
        )
        self.assertEqual(
            {mount["target"] for mount in self.runner["volumes"]},
            {"/work", "/work/apps/desktop/dist"},
        )

    def test_writable_state_is_ephemeral_and_bounded(self) -> None:
        self.assertTrue(any(item.startswith("/tmp:") for item in self.runner["tmpfs"]))
        self.assertLessEqual(self.runner["pids_limit"], 512)
        self.assertEqual(self.runner["mem_limit"], "4g")

    def test_runner_builds_shared_playwright_image(self) -> None:
        build = self.runner["build"]
        self.assertEqual(build["context"], "../../../..")
        self.assertEqual(build["dockerfile"], "apps/desktop/playwright/Dockerfile")
        self.assertTrue((COMPOSE.parent / build["context"] / build["dockerfile"]).is_file())
        self.assertNotIn("image", self.runner)
        self.assertNotIn("entrypoint", self.runner)

    def test_headless_ci_environment_and_writable_output_are_configured(self) -> None:
        self.assertEqual(self.runner["environment"]["GITHUB_ACTIONS"], "1")
        self.assertEqual(
            self.runner["command"],
            ["--output=/tmp/runner/test-results", "${PLAYWRIGHT_TARGET:-playwright/e2e/launch/launch.spec.ts}"],
        )

    def test_smoke_script_fails_closed_without_artifact(self) -> None:
        script = (COMPOSE.parent / "run-smoke.sh").read_text()
        self.assertIn('test -x "$artifact"', script)
        self.assertIn('docker compose -f "$compose_file" config --quiet', script)
        self.assertNotIn("--network host", script)
        self.assertIn("container_artifact=/work/", script)
        self.assertIn('ELEMENT_DESKTOP_EXECUTABLE:-\"$repo_root/apps/desktop/dist/', script)
        self.assertIn("-e ELEMENT_DESKTOP_EXECUTABLE=", script)


if __name__ == "__main__":
    unittest.main()
