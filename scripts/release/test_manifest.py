import json, subprocess, sys, tempfile, unittest
from pathlib import Path
SCRIPT = Path(__file__).with_name("manifest.py")
class ReleaseManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name); self.release = self.root / "release"; self.release.mkdir()
        for name in ("win-x64.msi", "win-arm64.msi", "macos.dmg", "linux-amd64.deb", "linux-arm64.deb", "source.tar.gz"): (self.release / name).write_bytes((name * 3).encode())
        self.private = self.root / "private.pem"; self.public = self.root / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", self.private], check=True, capture_output=True,timeout=15)
        subprocess.run(["openssl", "pkey", "-in", self.private, "-pubout", "-out", self.public], check=True, capture_output=True,timeout=15)
    def tearDown(self): self.tmp.cleanup()
    def tool(self, *args, success=True):
        result = subprocess.run([sys.executable, SCRIPT, *map(str, args)], capture_output=True,text=True,timeout=15)
        if success and result.returncode: self.fail(result.stderr)
        if not success: self.assertNotEqual(result.returncode, 0)
        return result
    def generate(self, channel="beta"):
        return json.loads(self.tool("generate", "--release-dir", self.release, "--base-url", "https://downloads.invalid", "--version", "2.0.0", "--channel", channel, "--key", self.private).stdout)
    def test_round_trip_and_determinism(self):
        first = self.generate(); second = self.generate(); self.assertEqual(first, second)
        self.assertIn("win-arm64", first["release"])
        self.assertIn("windows-arm64", first["release"])
        self.assertEqual(first["release"]["win-arm64"], first["release"]["windows-arm64"])
        path = self.root / "manifest.json"; path.write_text(json.dumps(first))
        self.assertIn("verified beta manifest 2.0.0", self.tool("verify", "--manifest", path, "--key", self.public, "--channel", "beta").stdout)
    def test_tamper_fails(self):
        document = self.generate(); document["version"] = "9.9.9"; path = self.root / "bad.json"; path.write_text(json.dumps(document))
        self.tool("verify", "--manifest", path, "--key", self.public, "--channel", "beta", success=False)
    def test_channel_mismatch_fails(self):
        path = self.root / "channel.json"; path.write_text(json.dumps(self.generate()))
        self.tool("verify", "--manifest", path, "--key", self.public, "--channel", "stable", success=False)
    def test_manifest_contains_expected_platform_set(self):
        manifest = self.generate()
        self.assertEqual(
            {"windows", "win-x64", "windows-x64", "win-arm64", "windows-arm64", "macos", "linux", "linux-amd64", "linux-arm64", "source"},
            set(manifest["release"]),
        )
    def test_invalid_base_url_components_fail(self):
        invalid = (
            "https://user@example.invalid",
            "https://user:pass@example.invalid",
            "https://downloads.invalid/path?channel=beta",
            "https://downloads.invalid/path#fragment",
            "https://",
            "https:///missing-host",
        )
        for base_url in invalid:
            with self.subTest(base_url=base_url):
                result = self.tool("generate", "--release-dir", self.release, "--base-url", base_url, "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)
                self.assertIn("base URL must", result.stderr)

    def test_malformed_base_url_does_not_escape_parser_errors(self):
        invalid = ("https://[broken", "https://[::1", "https://example.invalid:abc")
        for base_url in invalid:
            with self.subTest(base_url=base_url):
                result = self.tool("generate", "--release-dir", self.release, "--base-url", base_url, "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)
                self.assertIn("base URL must", result.stderr)

    def test_invalid_hostname_syntax_fails(self):
        invalid = ("a_b.invalid", "bad host.invalid", "-bad.invalid", "bad-.invalid", "bad..invalid", ".leading.invalid", "trailing.invalid.", chr(127).join(("bad", "host.invalid")), "256.1.1.1")
        for hostname in invalid:
            with self.subTest(hostname=hostname):
                self.tool("generate", "--release-dir", self.release, "--base-url", f"https://{hostname}", "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)

    def test_valid_hostname_and_ip_literals_are_accepted(self):
        for hostname in ("example.invalid", "cdn-1.example.invalid", "127.0.0.1", "[2001:db8::1]", "xn--bcher-kva.example"):
            with self.subTest(hostname=hostname):
                self.tool("generate", "--release-dir", self.release, "--base-url", f"https://{hostname}", "--version", "2.0.0", "--channel", "stable", "--key", self.private)

    def test_invalid_port_syntax_and_ranges_fail(self):
        for base_url in ("https://example.invalid:", "https://[2001:db8::1]:", "https://example.invalid:0", "https://example.invalid:-1", "https://example.invalid:65536"):
            with self.subTest(base_url=base_url):
                self.tool("generate", "--release-dir", self.release, "--base-url", base_url, "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)

    def test_empty_query_and_fragment_markers_fail(self):
        for base_url in ("https://example.invalid?", "https://example.invalid#"):
            with self.subTest(base_url=base_url):
                self.tool("generate", "--release-dir", self.release, "--base-url", base_url, "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)

    def test_whitespace_and_ascii_controls_in_base_url_fail_cleanly(self):
        invalid = (
            " https://downloads.invalid",
            "https://downloads.invalid ",
            "https://downloads.invalid/\npath",
            "https://downloads.invalid/\rpath",
            "https://downloads.invalid/\tpath",
            "https://downloads.invalid/bad path",
            "https://downloads.invalid/\x7fpath",
        )
        for base_url in invalid:
            with self.subTest(base_url=base_url):
                result = self.tool("generate", "--release-dir", self.release, "--base-url", base_url, "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)
                self.assertIn("base URL must", result.stderr)

    def test_non_https_base_url_fails(self):
        result = self.tool("generate", "--release-dir", self.release, "--base-url", "http://downloads.invalid", "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)
        self.assertIn("base URL must use https", result.stderr)

    def test_missing_artifact_fails(self):
        (self.release / "macos.dmg").unlink()
        self.tool("generate", "--release-dir", self.release, "--base-url", "https://downloads.invalid", "--version", "2.0.0", "--channel", "stable", "--key", self.private, success=False)
    def rollback_result(self, missing=None):
        manifest = self.generate("stable")
        fake_bin = self.root / "bin"
        fake_bin.mkdir(exist_ok=True)
        az = fake_bin / "az"
        az.write_text("""#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$AZ_LOG"
if [[ "$1 $2 $3" == "storage blob download" ]]; then
  cp "$FIXTURE_MANIFEST" "${@: -4:1}"
  exit 0
fi
if [[ "$1 $2 $3" == "storage blob exists" ]]; then
  name=""
  while (($#)); do
    if [[ "$1" == --name ]]; then name=$2; break; fi
    shift
  done
  [[ "$name" != "$MISSING_BLOB" ]] && printf 'true\\n' || printf 'false\\n'
  exit 0
fi
if [[ "$1 $2 $3" == "storage blob upload" ]]; then exit 0; fi
exit 2
""")
        az.chmod(0o755)
        fixture = self.root / "rollback-fixture.json"
        fixture.write_text(json.dumps(manifest))
        log = self.root / "az.log"
        env = dict(__import__("os").environ)
        repo = Path(__file__).resolve().parents[2]
        scripts = self.root / "scripts"
        scripts.symlink_to(repo / "scripts", target_is_directory=True)
        env.update(AZURE_STORAGE_ACCOUNT="account", AZURE_STORAGE_CONTAINER="container", FIXTURE_MANIFEST=str(fixture), AZ_LOG=str(log), MISSING_BLOB=missing or "", PATH=f"{fake_bin}:{env['PATH']}")
        result = subprocess.run(
            [Path(__file__).with_name("rollback.sh"), "stable", "2.0.0", self.public],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=15,
        )
        return result, log.read_text() if log.exists() else ""
    def test_rollback_checks_every_manifest_blob_before_upload(self):
        result, log = self.rollback_result()
        self.assertEqual(0, result.returncode, result.stderr)
        for filename in ("win-x64.msi", "win-arm64.msi", "macos.dmg", "linux-amd64.deb", "linux-arm64.deb", "source.tar.gz"):
            self.assertIn(f"--name v2.0.0/{filename}", log)
        self.assertIn("blob upload", log)
    def test_rollback_does_not_upload_when_manifest_blob_is_missing(self):
        result, log = self.rollback_result("v2.0.0/linux-arm64.deb")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("rollback blob missing", result.stderr)
        self.assertNotIn("blob upload", log)
    def test_source_archive_is_reproducible_and_preserves_executable_bits(self):
        repo = self.root / "repo"
        (repo / "apps/desktop/src").mkdir(parents=True)
        for name in ("LICENSE-AGPL-3.0", "apps/desktop/package.json", "apps/desktop/src/updater.ts", "run.sh"):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        (repo / "run.sh").chmod(0o755)
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "add", "."], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        outputs = [self.root / "source-one.tar.gz", self.root / "source-two.tar.gz"]
        for output in outputs:
            subprocess.run(
                [sys.executable, Path(__file__).with_name("source_archive.py"), "--root", repo, "--output", output, "--check"],
                check=True, capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
        import tarfile
        with tarfile.open(outputs[0], "r:gz") as archive:
            self.assertEqual(0o755, archive.getmember("run.sh").mode)
            self.assertEqual(0o644, archive.getmember("LICENSE-AGPL-3.0").mode)
if __name__ == "__main__": unittest.main()
