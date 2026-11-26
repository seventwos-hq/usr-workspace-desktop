import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("upstream_verify.py")
SPEC = importlib.util.spec_from_file_location("upstream_verify", MODULE_PATH)
assert SPEC and SPEC.loader
UV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UV)

WEB = {"apps/web/package.json": b'{"version": "1.0.0"}\n', "apps/web/src/a.ts": b"export const a = 1;\n",
       "packages/shared-utils/src/b.ts": b"export const b = 1;\n"}
SUPPORT = {"package.json": b'{"scripts": {"postinstall": "node scripts/pnpm-link.ts"}}\n',
           "patches/dependency.patch": b"trusted patch\n",
           "oxlint.config.ts": (
               b"/*\nCopyright 2025 Element Creations Ltd.\n\n"
               b"SPDX-License-Identifier: AGPL-3.0-only\n"
               b"Please see LICENSE in the repository root for full details.\n*/\n\n"
               b'export default { rules: { "no-eval": "error" } };\n'
           )}

WEB_PATCH = """--- a/apps/web/src/a.ts
+++ b/apps/web/src/a.ts
@@ -1 +1 @@
-export const a = 1;
+export const a = 2;
"""


def make_tarball(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, data in files.items():
            info = tarfile.TarInfo(f"element-web-1.0.0/{rel}")
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class UpstreamVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.tarball = make_tarball({**WEB, **SUPPORT, "apps/desktop/x.txt": b"ignored\n"})
        self.fetch = lambda url: self.tarball
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        pin = {
            "repository": "element-hq/element-web",
            "tag": "v1.0.0",
            "url": "https://github.com/element-hq/element-web/archive/refs/tags/v1.0.0.tar.gz",
            "sha256": hashlib.sha256(self.tarball).hexdigest(),
        }
        self.write(".seventwos/upstream-pin.json", json.dumps(pin).encode())
        self.write(".seventwos/upstream-state.json", b"{}\n")
        self.write("README.md", b"x\n")
        self.commit("base")
        self.git("checkout", "-q", "-b", "pr")

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True)

    def write(self, rel, data):
        p = Path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def import_web(self, files=WEB, tag="v1.0.0"):
        for rel, data in {**SUPPORT, **files}.items():
            self.write(rel, data)
        self.write(".seventwos/upstream-state.json", json.dumps({"pinnedTag": tag}).encode())
        self.write(".seventwos/upstream-ledger.jsonl", b'{"tag": "%s"}\n' % tag.encode())
        self.commit("import")

    def verify(self):
        return UV.verify("main", "HEAD", fetch=self.fetch)

    def add_patches(self, patches: dict, lines=None):
        for name, body in patches.items():
            self.write(f".seventwos/patches/{name}", body.encode())
        if lines is None:
            lines = [f"{name} reason" for name in patches]
        self.write(".seventwos/patches/series", ("\n".join(lines) + "\n").encode())
        self.commit("patches")

    def test_patches_that_apply_pass_after_byte_identity(self):
        self.accept_import()
        self.add_patches({"0001-a.patch": WEB_PATCH})
        result = self.verify()
        self.assertIn("no upstream import", result)
        self.assertIn("1 patches apply cleanly", result)

    def test_import_with_patches_checks_both(self):
        self.import_web()
        self.add_patches({"0001-a.patch": WEB_PATCH})
        result = self.verify()
        self.assertIn("byte-identical", result)
        self.assertIn("1 patches apply cleanly", result)

    def test_patch_that_no_longer_applies_fails(self):
        self.accept_import()
        self.add_patches({"0001-a.patch": WEB_PATCH.replace("= 1;", "= 9;", 1)})
        with self.assertRaisesRegex(UV.VerifyError, "0001-a.patch no longer applies"):
            self.verify()

    def test_patch_series_must_list_every_patch(self):
        self.accept_import()
        self.add_patches({"0001-a.patch": WEB_PATCH}, ["# empty"])
        with self.assertRaisesRegex(UV.VerifyError, "unlisted 0001-a.patch"):
            self.verify()

    def test_patch_needs_reason(self):
        self.accept_import()
        self.add_patches({"0001-a.patch": WEB_PATCH}, ["0001-a.patch"])
        with self.assertRaisesRegex(UV.VerifyError, "series line 1"):
            self.verify()

    def test_patch_outside_upstream_paths_fails(self):
        self.accept_import()
        self.add_patches({"0001-a.patch": WEB_PATCH.replace("apps/web/src/a.ts", "README.md")})
        with self.assertRaisesRegex(UV.VerifyError, "outside apps/web and packages"):
            self.verify()

    def test_patch_cannot_hide_a_modified_import(self):
        self.import_web({**WEB, "apps/web/src/a.ts": b"export const a = 2;\n"})
        self.add_patches({"0001-a.patch": WEB_PATCH})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: apps/web/src/a.ts"):
            self.verify()


    def test_patch_rename_outside_upstream_paths_fails(self):
        self.accept_import()
        rename_patch = (
            "diff --git a/apps/web/src/a.ts b/README.md\n"
            "similarity index 100%\n"
            "rename from apps/web/src/a.ts\n"
            "rename to README.md\n"
        )
        self.add_patches({"0001-ren.patch": rename_patch})
        with self.assertRaisesRegex(UV.VerifyError, "outside apps/web and packages"):
            self.verify()

    def test_nested_patch_path_fails(self):
        self.accept_import()
        self.write(".seventwos/patches/sub/0001-a.patch", WEB_PATCH.encode())
        self.write(".seventwos/patches/series", b"0001-a.patch reason\n")
        self.commit("nested patch")
        with self.assertRaisesRegex(UV.VerifyError, "nested patch path not allowed"):
            self.verify()

    def test_verify_head_checks_imported_tree_without_import_diff(self):
        self.accept_import()
        self.write("apps/web/src/a.ts", b"export const a = 2;\n")
        self.commit("tamper imported tree")
        self.git("branch", "-f", "main", "HEAD")
        self.write("README.md", b"z\n")
        self.commit("unrelated change")
        self.assertIn("no upstream import", self.verify())
        with self.assertRaisesRegex(UV.VerifyError, "content differs: apps/web/src/a.ts"):
            UV.verify("main", "HEAD", fetch=self.fetch, verify_head=True)

    def test_non_import_change_passes(self):
        self.write("README.md", b"y\n")
        self.commit("docs")
        self.assertIn("no upstream import", self.verify())

    def test_exact_import_passes(self):
        self.import_web()
        self.assertIn("byte-identical", self.verify())

    def accept_import(self):
        self.import_web()
        self.assertIn("byte-identical", self.verify())
        self.git("branch", "-f", "main", "HEAD")

    def test_support_only_content_changes_after_import_fail(self):
        self.accept_import()
        for path in SUPPORT:
            with self.subTest(path=path):
                self.write(path, b"malicious\n")
                self.commit("modify support file")
                with self.assertRaisesRegex(UV.VerifyError, f"content differs: {path}"):
                    self.verify()
                self.git("reset", "--hard", "main")

    def test_support_only_deletions_after_import_fail(self):
        self.accept_import()
        for path in SUPPORT:
            with self.subTest(path=path):
                Path(path).unlink()
                self.commit("delete support file")
                with self.assertRaisesRegex(UV.VerifyError, f"missing: {path}"):
                    self.verify()
                self.git("reset", "--hard", "main")

    def test_support_only_mode_changes_after_import_fail(self):
        self.accept_import()
        for path in SUPPORT:
            with self.subTest(path=path):
                os.chmod(path, 0o755)
                self.commit("chmod support file")
                with self.assertRaisesRegex(UV.VerifyError, f"mode differs: {path}"):
                    self.verify()
                self.git("reset", "--hard", "main")

    def test_support_only_symlinks_after_import_fail(self):
        self.accept_import()
        for path in SUPPORT:
            with self.subTest(path=path):
                Path(path).unlink()
                os.symlink("README.md", path)
                self.commit("support symlink")
                with self.assertRaisesRegex(UV.VerifyError, f"mode differs: {path}"):
                    self.verify()
                self.git("reset", "--hard", "main")

    def test_extra_patch_after_import_fails(self):
        self.accept_import()
        self.write("patches/extra.patch", b"unverified patch\n")
        self.commit("extra patch")
        with self.assertRaisesRegex(UV.VerifyError, "extra: patches/extra.patch"):
            self.verify()

    def test_patch_root_file_after_import_fails(self):
        self.accept_import()
        Path("patches/dependency.patch").unlink()
        Path("patches").rmdir()
        self.write("patches", b"unverified\n")
        self.commit("replace patch directory")
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist: patches"):
            self.verify()

    def test_modified_root_postinstall_fails(self):
        self.import_web({**WEB, "package.json": b'{"scripts": {"postinstall": "malicious"}}\n'})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: package.json"):
            self.verify()

    def test_modified_patch_fails(self):
        self.import_web({**WEB, "patches/dependency.patch": b"malicious patch\n"})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: patches/dependency.patch"):
            self.verify()

    def test_missing_support_files_fail(self):
        for path in SUPPORT:
            with self.subTest(path=path):
                self.import_web()
                Path(path).unlink()
                self.commit("delete support file")
                with self.assertRaisesRegex(UV.VerifyError, f"missing: {path}"):
                    self.verify()

    def test_extra_patch_fails(self):
        self.import_web({**WEB, "patches/extra.patch": b"unverified patch\n"})
        with self.assertRaisesRegex(UV.VerifyError, "extra: patches/extra.patch"):
            self.verify()

    def test_support_mode_changes_fail(self):
        for path in SUPPORT:
            with self.subTest(path=path):
                self.import_web()
                os.chmod(path, 0o755)
                self.commit("chmod support file")
                with self.assertRaisesRegex(UV.VerifyError, f"mode differs: {path}"):
                    self.verify()
                os.chmod(path, 0o644)

    def test_support_symlinks_fail(self):
        for path in SUPPORT:
            with self.subTest(path=path):
                self.import_web()
                Path(path).unlink()
                os.symlink("README.md", path)
                self.commit("support symlink")
                with self.assertRaisesRegex(UV.VerifyError, f"mode differs: {path}"):
                    self.verify()
                Path(path).unlink()

    def test_web_root_regular_file_fails(self):
        self.write("apps/web", b"unverified\n")
        self.commit("web file")
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist: apps/web"):
            self.verify()

    def test_web_root_symlink_fails(self):
        Path("apps").mkdir()
        os.symlink("../README.md", "apps/web")
        self.commit("web symlink")
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist: apps/web"):
            self.verify()

    def test_web_root_submodule_fails(self):
        self.git("update-index", "--add", "--cacheinfo", "160000",
                 UV.git("rev-parse", "HEAD").strip(), "apps/web")
        self.git("commit", "-q", "-m", "web submodule")
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist: apps/web"):
            self.verify()

    def test_modified_file_fails(self):
        self.import_web({**WEB, "apps/web/src/a.ts": b"export const a = 2;\n"})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: apps/web/src/a.ts"):
            self.verify()

    def test_extra_and_missing_files_fail(self):
        files = dict(WEB)
        del files["apps/web/src/a.ts"]
        files["apps/web/extra.ts"] = b"x"
        self.import_web(files)
        with self.assertRaisesRegex(UV.VerifyError, "missing: apps/web/src/a.ts"):
            self.verify()

    def test_modified_package_file_fails(self):
        self.import_web({**WEB, "packages/shared-utils/src/b.ts": b"export const b = 2;\n"})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: packages/shared-utils/src/b.ts"):
            self.verify()

    def test_package_only_change_is_checked(self):
        self.import_web()
        self.write("packages/shared-utils/src/c.ts", b"x\n")
        self.commit("extra package file")
        with self.assertRaisesRegex(UV.VerifyError, "extra: packages/shared-utils/src/c.ts"):
            self.verify()

    def test_mode_change_fails(self):
        self.import_web()
        os.chmod("apps/web/src/a.ts", 0o755)
        self.commit("chmod")
        with self.assertRaisesRegex(UV.VerifyError, "mode differs"):
            self.verify()

    def test_path_outside_allowlist_fails(self):
        self.write("apps/desktop/main.ts", b"x")
        self.import_web()
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist: apps/desktop/main.ts"):
            self.verify()

    def test_lint_config_change_with_import_passes(self):
        _, _, body = SUPPORT["oxlint.config.ts"].partition(b"*/\n\n")
        self.import_web({**WEB, "oxlint.config.ts": UV.LOCAL_LINT_HEADER + body})
        self.assertIn("byte-identical", self.verify())

    def test_modified_lint_config_with_import_fails(self):
        self.import_web({**WEB, "oxlint.config.ts": b"export default {};\n"})
        with self.assertRaisesRegex(UV.VerifyError, "content differs: oxlint.config.ts"):
            self.verify()

    def test_local_lint_header_only_change_after_import_passes(self):
        self.accept_import()
        _, _, body = SUPPORT["oxlint.config.ts"].partition(b"*/\n\n")
        self.write("oxlint.config.ts", UV.LOCAL_LINT_HEADER + body)
        self.commit("local lint header")
        self.assertIn("byte-identical", self.verify())

    def test_lint_header_exception_rejects_injected_code_and_rule_changes(self):
        self.accept_import()
        _, _, body = SUPPORT["oxlint.config.ts"].partition(b"*/\n\n")
        contents = (
            UV.LOCAL_LINT_HEADER + b'import "malicious";\n' + body,
            UV.LOCAL_LINT_HEADER + b"export default {};\n",
            UV.LOCAL_LINT_HEADER.replace(b"Copyright", b"*/ import 'malicious'; /* Copyright") + body,
            UV.LOCAL_LINT_HEADER + UV.LOCAL_LINT_HEADER + body,
        )
        for content in contents:
            with self.subTest(content=content):
                self.write("oxlint.config.ts", content)
                self.commit("tamper lint config")
                with self.assertRaisesRegex(UV.VerifyError, "content differs: oxlint.config.ts"):
                    self.verify()
                self.git("reset", "--hard", "main")

    def test_pin_change_in_pr_is_outside_allowlist(self):
        self.write(".seventwos/upstream-pin.json", b"{}")
        self.import_web()
        with self.assertRaisesRegex(UV.VerifyError, "outside the allowlist"):
            self.verify()

    def test_wrong_pinned_tag_fails(self):
        self.import_web(tag="v0.9.0")
        with self.assertRaisesRegex(UV.VerifyError, "pinnedTag"):
            self.verify()

    def test_tarball_hash_mismatch_fails(self):
        self.import_web()
        self.fetch = lambda url: b"tampered"
        with self.assertRaisesRegex(UV.VerifyError, "does not match pinned"):
            self.verify()

    def test_missing_pin_on_base_fails_closed(self):
        self.git("checkout", "-q", "main")
        self.git("rm", "-q", ".seventwos/upstream-pin.json")
        self.commit("drop pin")
        self.git("checkout", "-q", "pr")
        with self.assertRaises(SystemExit):
            self.verify()

    def test_pin_url_must_match_tag(self):
        self.git("checkout", "-q", "main")
        pin = json.loads(Path(".seventwos/upstream-pin.json").read_text())
        pin["url"] = "https://example.invalid/x.tar.gz"
        self.write(".seventwos/upstream-pin.json", json.dumps(pin).encode())
        self.commit("bad pin")
        self.git("checkout", "-q", "pr")
        self.git("rebase", "-q", "main")
        self.write("apps/web/package.json", WEB["apps/web/package.json"])
        self.commit("web")
        with self.assertRaises(SystemExit):
            self.verify()


if __name__ == "__main__":
    unittest.main()
