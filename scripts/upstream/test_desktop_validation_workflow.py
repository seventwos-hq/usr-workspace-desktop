import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/desktop-validation.yaml"
PREPARE_WORKFLOW = ROOT / ".github/workflows/build_desktop_prepare.yaml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/seventwos-desktop-release.yml"


class DesktopValidationWorkflowTests(unittest.TestCase):
    def test_resolved_electron_is_installed_before_parallel_unit_tests(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        install = workflow.index(
            "run: pnpm install --frozen-lockfile --filter seventwos-workspace-desktop"
        )
        prepare = workflow.index(
            "run: pnpm --filter seventwos-workspace-desktop exec install-electron"
        )
        tests = workflow.index(
            "run: pnpm --filter seventwos-workspace-desktop test:unit --run"
        )
        self.assertLess(install, prepare)
        self.assertLess(prepare, tests)
        step = workflow[:prepare].rsplit("            - name:", 1)[1]
        self.assertNotIn("if:", step)
        self.assertNotIn("continue-on-error:", step)
        self.assertNotIn("--maxWorkers", workflow)
        self.assertNotIn("--no-file-parallelism", workflow)


    def test_validation_runs_on_main_pull_requests(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        pull_request = workflow.split("    pull_request:", 1)[1].split("    merge_group:", 1)[0]
        self.assertIn("- main", pull_request)
        self.assertNotIn("- develop", pull_request)

    def test_prepare_fails_closed_and_verifies_the_head_tree(self) -> None:
        workflow = PREPARE_WORKFLOW.read_text(encoding="utf-8")
        validate = workflow.index("            - name: Validate inputs")
        install = workflow.index("            - name: Install build dependencies")
        step = workflow[validate:install]
        self.assertIn("PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}", step)
        self.assertIn("MERGE_GROUP_BASE_SHA: ${{ github.event.merge_group.base_sha }}", step)
        run = step.split("run: |", 1)[1]
        self.assertNotIn("${{ github.base_ref }}", run)
        self.assertNotIn("${{ github.ref_type }}", run)
        self.assertIn("BASE=\"$PR_BASE_SHA\"", step)
        self.assertIn("BASE=\"$MERGE_GROUP_BASE_SHA\"", step)
        self.assertIn("git fetch --no-tags origin \"$BASE\"", step)
        self.assertIn("git rev-parse --verify \"${BASE}^{commit}\"", step)
        self.assertIn("upstream_verify.py --base \"$BASE\" --head HEAD --verify-head", step)
        self.assertIn("cannot determine trusted upstream base", step)

    def test_prepare_builds_repository_owned_web_patches(self) -> None:
        workflow = PREPARE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python3 scripts/upstream/apply_patches.py --root .", workflow)
        self.assertIn("pnpm --dir apps/web build", workflow)
        self.assertNotIn("web-bundle-url", workflow)
        self.assertNotIn("web-bundle.tar.gz", workflow)
        apply = workflow.index("python3 scripts/upstream/apply_patches.py")
        build = workflow.index("pnpm --dir apps/web build")
        pack = workflow.index("asar pack")
        self.assertLess(apply, build)
        self.assertLess(build, pack)

    def test_release_upload_is_tag_gated_and_oidc_only(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('tags: ["desktop-v*"]', workflow)
        self.assertNotIn('tags: ["v*"]', workflow)
        self.assertIn(
            '[[ "$TAG" =~ ^desktop-v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\\.[0-9A-Za-z-]+)*)?$ ]]',
            workflow,
        )
        publish = workflow.index("    publish:")
        self.assertGreater(workflow.index("id-token: write", publish), publish)
        self.assertIn("environment: desktop-release", workflow[publish:])
        self.assertNotIn("pull_request_target", workflow)
        self.assertIn('printf \'prerelease=%s\\n\' "$PRERELEASE" >> "$GITHUB_OUTPUT"', workflow)
        self.assertIn('VERSION="${TAG#desktop-v}"', workflow)
        self.assertIn('git merge-base --is-ancestor "$TAG_SHA" origin/main', workflow)
        self.assertIn("Publish versioned download manifest", workflow)
        self.assertIn('--name "v$VERSION/manifest.json"', workflow)
        self.assertGreaterEqual(workflow.count("--overwrite false"), 2)
        self.assertNotIn("VERSIONED_OVERWRITE", workflow)
        self.assertIn("if: steps.stage.outputs.prerelease != 'true'", workflow)
        self.assertIn("Publish latest stable download manifest", workflow)
        self.assertIn("--name manifest.json", workflow)
        self.assertIn("--overwrite true", workflow)
        self.assertIn("SEVENTWOS_WORKSPACE_SIGNTOOL_SUBJECT_NAME", workflow)
        self.assertIn("SEVENTWOS_WORKSPACE_SIGNTOOL_THUMBPRINT", workflow)
        self.assertIn("SEVENTWOS_WORKSPACE_APPLE_TEAM_ID", workflow)


if __name__ == "__main__":
    unittest.main()
