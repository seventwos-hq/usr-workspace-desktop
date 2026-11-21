import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("apply_patches.py")
SPEC = importlib.util.spec_from_file_location("apply_patches", MODULE_PATH)
assert SPEC and SPEC.loader
AP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AP)

ORIGINAL = "line one\nline two\nline three\n"
PATCH_1 = """--- a/apps/web/src/a.txt
+++ b/apps/web/src/a.txt
@@ -1,3 +1,3 @@
 line one
-line two
+line TWO
 line three
"""
# Builds on PATCH_1, so order matters.
PATCH_2 = """--- a/apps/web/src/a.txt
+++ b/apps/web/src/a.txt
@@ -1,3 +1,3 @@
 line one
-line TWO
+line 2
 line three
"""
STALE = """--- a/apps/web/src/a.txt
+++ b/apps/web/src/a.txt
@@ -1,3 +1,3 @@
 line one
-line zwei
+line 2
 line three
"""
OUTSIDE = """--- a/apps/desktop/x.txt
+++ b/apps/desktop/x.txt
@@ -1 +1 @@
-x
+y
"""


class ApplyPatchesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("apps/web/src/a.txt", ORIGINAL)
        self.write("apps/desktop/x.txt", "x\n")
        self.pdir = self.root / AP.PATCH_DIR
        self.pdir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def series(self, patches: dict, lines=None):
        for name, body in patches.items():
            (self.pdir / name).write_text(body)
        if lines is None:
            lines = [f"{name}  reason for {name}" for name in patches]
        (self.pdir / AP.SERIES).write_text("# order and reason\n" + "\n".join(lines) + "\n")

    def run_main(self):
        return AP.main(["--root", str(self.root)])

    def text(self):
        return (self.root / "apps/web/src/a.txt").read_text()

    def test_applies_in_series_order(self):
        self.series({"0002-b.patch": PATCH_2, "0001-a.patch": PATCH_1},
                    ["0001-a.patch first", "0002-b.patch second"])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.text(), "line one\nline 2\nline three\n")

    def test_wrong_order_fails(self):
        self.series({"0001-a.patch": PATCH_1, "0002-b.patch": PATCH_2},
                    ["0002-b.patch second", "0001-a.patch first"])
        with self.assertRaisesRegex(AP.PatchError, "0002-b.patch does not apply"):
            AP.apply_all(self.root, self.pdir)

    def test_stale_patch_fails_closed_without_changes(self):
        self.series({"0001-stale.patch": STALE})
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.text(), ORIGINAL)

    def test_second_run_fails(self):
        self.series({"0001-a.patch": PATCH_1})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.run_main(), 1)

    def test_unlisted_patch_fails(self):
        self.series({"0001-a.patch": PATCH_1}, [])
        with self.assertRaisesRegex(AP.PatchError, "not in series: 0001-a.patch"):
            AP.apply_all(self.root, self.pdir)

    def test_missing_patch_fails(self):
        self.series({}, ["0001-a.patch reason"])
        with self.assertRaisesRegex(AP.PatchError, "listed but missing"):
            AP.apply_all(self.root, self.pdir)

    def test_missing_reason_fails(self):
        self.series({"0001-a.patch": PATCH_1}, ["0001-a.patch"])
        with self.assertRaisesRegex(AP.PatchError, "no reason"):
            AP.apply_all(self.root, self.pdir)

    def test_patch_outside_upstream_copy_fails(self):
        self.series({"0001-out.patch": OUTSIDE})
        with self.assertRaisesRegex(AP.PatchError, "outside the upstream copy"):
            AP.apply_all(self.root, self.pdir)
        self.assertEqual((self.root / "apps/desktop/x.txt").read_text(), "x\n")

    def test_missing_series_is_setup_failure(self):
        with self.assertRaisesRegex(AP.PatchError, "not found"):
            AP.apply_all(self.root, self.pdir)



    def test_rename_outside_upstream_copy_fails(self):
        rename_patch = (
            "diff --git a/apps/web/src/a.txt b/README.md\n"
            "similarity index 100%\n"
            "rename from apps/web/src/a.txt\n"
            "rename to README.md\n"
        )
        self.series({"0001-ren.patch": rename_patch})
        with self.assertRaisesRegex(AP.PatchError, "outside the upstream copy"):
            AP.apply_all(self.root, self.pdir)

    def test_symlinked_patch_file_fails(self):
        target = self.root / "outside.patch"
        target.write_text(PATCH_1)
        (self.pdir / "0001-sym.patch").symlink_to(target)
        (self.pdir / AP.SERIES).write_text("0001-sym.patch  reason\n")
        with self.assertRaisesRegex(AP.PatchError, "symlinked patch entry not allowed"):
            AP.apply_all(self.root, self.pdir)

    def test_symlink_mode_in_patch_fails(self):
        sym_patch = (
            "diff --git a/apps/web/src/link b/apps/web/src/link\n"
            "new file mode 120000\n"
            "--- /dev/null\n"
            "+++ b/apps/web/src/link\n"
            "@@ -0,0 +1 @@\n"
            "+/etc/passwd\n"
        )
        self.series({"0001-mode.patch": sym_patch})
        with self.assertRaisesRegex(AP.PatchError, "symlink file modes"):
            AP.apply_all(self.root, self.pdir)


if __name__ == "__main__":
    unittest.main()
