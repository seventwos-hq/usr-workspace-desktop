#!/usr/bin/env python3
"""Verify that apps/web and packages are an unmodified copy of the pinned upstream release.

The pin (tag, download URL, SHA-256) is read from the BASE branch, so a pull
request cannot change what it is checked against. The upstream tarball is
downloaded by tag and must match the pinned SHA-256.

Rules for a pull request (base..head):
  * No change to apps/web, packages, patches (or under them), package.json,
    or oxlint.config.ts and no pinnedTag change: not an import, pass.
  * Otherwise every changed path must be in the import allowlist, every file
    under apps/web/, packages/, and patches/, plus package.json and oxlint.config.ts,
    must match (content, executable bit, symlink target) the pinned tarball,
    except for the exact local license header in oxlint.config.ts, and
    .seventwos/upstream-state.json must carry "pinnedTag" equal to the pin.
  * Then, if the change is an import or touches .seventwos/patches/ and the head
    has .seventwos/patches/series, every listed patch must apply in order,
    exactly (no fuzz), to the head's apps/web and packages; an unlisted, missing,
    nested, or symlinked patch file or a patch that touches other paths fails.
Exit 0 = pass, 1 = verification failed, 2 = setup error (fail closed).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import PurePosixPath

PIN_PATH = ".seventwos/upstream-pin.json"
STATE_PATH = ".seventwos/upstream-state.json"
LEDGER_PATH = ".seventwos/upstream-ledger.jsonl"
# Paths that may change only by a byte-identical import of the pinned upstream release.
IMPORT_PREFIXES = ("apps/web/", "packages/")
# The workspace lockfile and catalog must change with the imported app.
# The root manifest and the dependency patches also follow the imported release.
IMPORT_FILES = ("package.json", "oxlint.config.ts")
# The root lint config follows the imported release but keeps our license header.
LOCAL_LINT_HEADER = (
    b"/*\nCopyright 2026 Element Creations Ltd.\n\n"
    b"SPDX-License-Identifier: AGPL-3.0-only\n"
    b"Please see LICENSE in the repository root for full details.\n*/\n\n"
)
ALLOWED_FILES = {STATE_PATH, LEDGER_PATH, "pnpm-lock.yaml", "pnpm-workspace.yaml", *IMPORT_FILES}
ALLOWED_PREFIXES = ("patches/",)
MAX_TARBALL_BYTES = 200 * 1024 * 1024
# Our own changes to the upstream copy, applied at build time (scripts/upstream/apply_patches.py).
PATCH_DIR = ".seventwos/patches"
PATCH_SERIES = f"{PATCH_DIR}/series"
RENAME_COPY_PREFIXES = ("rename from ", "rename to ", "copy from ", "copy to ")
SYMLINK_MODE_LINES = (
    "new file mode 120000",
    "old mode 120000",
    "new mode 120000",
    "deleted file mode 120000",
)


class VerifyError(Exception):
    pass


def git(*args: str, binary: bool = False):
    out = subprocess.run(["git", *args], check=True, capture_output=True).stdout
    return out if binary else out.decode()


def read_pin(base: str) -> dict:
    try:
        raw = git("show", f"{base}:{PIN_PATH}")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"setup error: {PIN_PATH} not found on {base}") from exc
    pin = json.loads(raw)
    for key in ("repository", "tag", "url", "sha256"):
        if not isinstance(pin.get(key), str) or not pin[key]:
            raise SystemExit(f"setup error: pin field {key!r} missing")
    expected_url = f"https://github.com/{pin['repository']}/archive/refs/tags/{pin['tag']}.tar.gz"
    if pin["url"] != expected_url:
        raise SystemExit("setup error: pin url must be the GitHub tag archive of the pinned tag")
    if len(pin["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in pin["sha256"]):
        raise SystemExit("setup error: pin sha256 must be 64 lowercase hex characters")
    return pin


def changed_paths(base: str, head: str) -> list[str]:
    out = git("diff", "--no-renames", "--name-only", "-z", f"{base}...{head}")
    return [p for p in out.split("\0") if p]


def is_import(paths: list[str], base: str, head: str) -> bool:
    if any(p in IMPORT_FILES or under_import_prefix(p) for p in paths):
        return True
    if STATE_PATH in paths:
        return pinned_tag_at(base) != pinned_tag_at(head)
    return False


def under_import_prefix(path: str) -> bool:
    return any(path == pre.rstrip("/") or path.startswith(pre) for pre in IMPORT_PREFIXES + ALLOWED_PREFIXES)


def pinned_tag_at(ref: str):
    try:
        return json.loads(git("show", f"{ref}:{STATE_PATH}")).get("pinnedTag")
    except (subprocess.CalledProcessError, json.JSONDecodeError, AttributeError):
        return None


def check_allowlist(paths: list[str]) -> list[str]:
    # A version bump may refresh our patches in the same change; they are checked after the import.
    return [p for p in paths if not (p.startswith(IMPORT_PREFIXES + ALLOWED_PREFIXES + (PATCH_DIR + "/",))
                                     or p in ALLOWED_FILES)]


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "upstream-verify"})
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 (fixed https URL)
        data = resp.read(MAX_TARBALL_BYTES + 1)
    if len(data) > MAX_TARBALL_BYTES:
        raise VerifyError("upstream tarball exceeds size limit")
    return data


def tarball_tree(data: bytes, sha256: str) -> dict[str, tuple[str, bytes]]:
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise VerifyError(f"tarball sha256 {digest} does not match pinned {sha256}")
    tree: dict[str, tuple[str, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                continue
            rel = "/".join(parts[1:])
            if not (rel.startswith(IMPORT_PREFIXES + ALLOWED_PREFIXES) or rel in IMPORT_FILES):
                continue
            if member.isdir():
                continue
            if member.issym():
                tree[rel] = ("120000", member.linkname.encode())
            elif member.isfile():
                fh = tar.extractfile(member)
                assert fh is not None
                mode = "100755" if member.mode & 0o111 else "100644"
                tree[rel] = (mode, fh.read())
            else:
                raise VerifyError(f"unsupported entry type in tarball: {rel}")
    if not tree:
        raise VerifyError("tarball has no files under " + ", ".join(IMPORT_PREFIXES))
    for pre in IMPORT_PREFIXES:
        if not any(k.startswith(pre) for k in tree):
            raise VerifyError(f"tarball has no {pre} files")
    return tree


def git_tree(head: str) -> dict[str, tuple[str, bytes]]:
    out = git("ls-tree", "-r", "-z", "--full-tree", head, "--",
              *[p.rstrip("/") for p in IMPORT_PREFIXES + ALLOWED_PREFIXES], *IMPORT_FILES)
    tree: dict[str, tuple[str, bytes]] = {}
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, kind, obj = meta.split()
        if kind != "blob":
            raise VerifyError(f"unsupported entry in imported path: {path} ({kind})")
        tree[path] = (mode, git("cat-file", "blob", obj, binary=True))
    return tree


def compare(expected: dict, actual: dict) -> list[str]:
    problems = []
    for path in sorted(expected.keys() - actual.keys()):
        problems.append(f"missing: {path}")
    for path in sorted(actual.keys() - expected.keys()):
        problems.append(f"extra: {path}")
    for path in sorted(expected.keys() & actual.keys()):
        if expected[path][0] != actual[path][0]:
            problems.append(f"mode differs: {path} ({actual[path][0]} != {expected[path][0]})")
        elif expected[path][1] != actual[path][1]:
            if (path == "oxlint.config.ts" and expected[path][0] in ("100644", "100755")
                    and expected[path][1].startswith(b"/*\n")
                    and actual[path][1].startswith(LOCAL_LINT_HEADER)):
                _, separator, body = expected[path][1].partition(b"*/\n\n")
                if separator and actual[path][1][len(LOCAL_LINT_HEADER):] == body:
                    continue
            problems.append(f"content differs: {path}")
    return problems


def _norm_patch_path(name: str, raw: str, *, require_ab: bool) -> str | None:
    token = raw.split("\t", 1)[0].strip()
    if token == "/dev/null":
        return None
    if token.startswith('"') or token.endswith('"') or "\\" in token:
        raise VerifyError(f"{name} uses a quoted or escaped path: {token!r}")
    if require_ab:
        if not token.startswith(("a/", "b/")):
            raise VerifyError(f"{name} header path must start with a/ or b/: {token!r}")
        return token[2:]
    return token


def validate_patch_paths(name: str, data: bytes) -> None:
    paths: list[str] = []
    try:
        decoded = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VerifyError(f"{name}: patch is not valid UTF-8: {exc}") from exc
    for line in decoded.splitlines():
        if line in SYMLINK_MODE_LINES or (line.startswith("index ") and line.endswith(" 120000")):
            raise VerifyError(f"{name} uses symlink file mode (120000)")
        if line.startswith(("--- ", "+++ ")):
            norm = _norm_patch_path(name, line[4:], require_ab=True)
            if norm is not None:
                paths.append(norm)
        elif line.startswith("diff --git "):
            rest = line[len("diff --git "):].strip()
            if not rest.startswith("a/") or " b/" not in rest:
                raise VerifyError(f"{name} has malformed diff --git header: {line!r}")
            a_part, b_part = rest.split(" b/", 1)
            for candidate in (
                _norm_patch_path(name, a_part, require_ab=True),
                _norm_patch_path(name, "b/" + b_part, require_ab=True),
            ):
                if candidate is not None:
                    paths.append(candidate)
        elif line.startswith(RENAME_COPY_PREFIXES):
            for prefix in RENAME_COPY_PREFIXES:
                if line.startswith(prefix):
                    norm = _norm_patch_path(name, line[len(prefix):], require_ab=False)
                    if norm is not None:
                        paths.append(norm)
                    break
    if not paths:
        raise VerifyError(f"{name} has no file changes")
    for rel in paths:
        if not rel.startswith(IMPORT_PREFIXES) or ".." in rel.split("/") or rel.startswith("/"):
            raise VerifyError(f"{name} touches a path outside apps/web and packages: {rel}")


def check_patches(head: str) -> str:
    """Apply the head's patch series to a scratch copy of the head's upstream paths."""
    try:
        series = git("show", f"{head}:{PATCH_SERIES}")
    except subprocess.CalledProcessError:
        return "no patch series"
    entries: list[str] = []
    for lineno, line in enumerate(series.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition(" ")
        if (
            not name.endswith(".patch")
            or "/" in name
            or "\\" in name
            or ".." in name
            or not reason.strip()
            or name in entries
        ):
            raise VerifyError(f"{PATCH_SERIES} line {lineno}: need a unique '<name>.patch <reason>'")
        entries.append(name)
    listed = git("ls-tree", "-r", "-z", "--full-tree", head, f"{PATCH_DIR}/")
    on_disk: set[str] = set()
    for rec in filter(None, listed.split("\0")):
        meta, fullpath = rec.split("\t", 1)
        mode, kind, _ = meta.split()
        if fullpath == PATCH_SERIES:
            if mode != "100644" or kind != "blob":
                raise VerifyError(f"{PATCH_SERIES} must be a regular 100644 file")
            continue
        rel_in_dir = fullpath[len(PATCH_DIR) + 1:]
        if "/" in rel_in_dir:
            raise VerifyError(f"nested patch path not allowed: {fullpath}")
        if mode != "100644" or kind != "blob":
            raise VerifyError(f"patch entry must be a regular 100644 file: {fullpath} ({mode} {kind})")
        if not rel_in_dir.endswith(".patch"):
            raise VerifyError(f"unexpected file in {PATCH_DIR}: {fullpath}")
        on_disk.add(rel_in_dir)
    if on_disk != set(entries):
        raise VerifyError("patch files and series differ: missing " + ", ".join(sorted(set(entries) - on_disk))
                          + "; unlisted " + ", ".join(sorted(on_disk - set(entries))))
    if not entries:
        return "no patches listed"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
        top = git("rev-parse", "--show-toplevel").strip()
        archive = subprocess.run(["git", "archive", "--format=tar", head, "--", *[p.rstrip("/") for p in IMPORT_PREFIXES]],
                                 cwd=top, check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        for name in entries:
            data = git("show", f"{head}:{PATCH_DIR}/{name}", binary=True)
            validate_patch_paths(name, data)
            res = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=tmp, input=data, capture_output=True)
            if res.returncode:
                raise VerifyError(f"{name} no longer applies:\n  {res.stderr.decode().strip()}")
    return f"{len(entries)} patches apply cleanly"


def verify(base: str, head: str, fetch=download) -> str:
    paths = changed_paths(base, head)
    result = verify_import(base, head, fetch, paths=paths)
    if not is_import(paths, base, head) and not any(p.startswith(PATCH_DIR + "/") for p in paths):
        return result
    return f"{result}; {check_patches(head)}"


def verify_import(base: str, head: str, fetch=download, *, paths: list[str] | None = None) -> str:
    pin = read_pin(base)
    if paths is None:
        paths = changed_paths(base, head)
    if not is_import(paths, base, head):
        return "pass: no upstream import in this change"
    outside = check_allowlist(paths)
    if outside:
        raise VerifyError("upstream import changes paths outside the allowlist: " + ", ".join(outside[:20]))
    if pinned_tag_at(head) != pin["tag"]:
        raise VerifyError(f'{STATE_PATH} must set "pinnedTag": "{pin["tag"]}"')
    problems = compare(tarball_tree(fetch(pin["url"]), pin["sha256"]), git_tree(head))
    if problems:
        shown = "\n  ".join(problems[:50])
        raise VerifyError(f"imported paths differ from {pin['repository']} {pin['tag']} ({len(problems)} problems):\n  {shown}")
    return f"pass: apps/web, packages, patches, package.json, and oxlint.config.ts are byte-identical to {pin['repository']} {pin['tag']} (except the local lint license header)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args(argv)
    try:
        print(verify(args.base, args.head))
    except VerifyError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
