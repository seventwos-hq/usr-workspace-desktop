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
           "patches/dependency.patch": b"trusted patch\n"}


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

    def test_non_import_change_passes(self):
        self.write("README.md", b"y\n")
        self.commit("docs")
        self.assertIn("no upstream import", self.verify())

    def test_exact_import_passes(self):
        self.import_web()
        self.assertIn("byte-identical", self.verify())

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
        self.write("oxlint.config.ts", b"export default {};\n")
        self.import_web()
        self.verify()

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
