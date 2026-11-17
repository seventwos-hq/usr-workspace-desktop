#!/usr/bin/env python3
"""Verify that apps/web is an unmodified copy of the pinned upstream release.

The pin (tag, download URL, SHA-256) is read from the BASE branch, so a pull
request cannot change what it is checked against. The upstream tarball is
downloaded by tag and must match the pinned SHA-256.

Rules for a pull request (base..head):
  * No change to apps/web or under apps/web/ and no pinnedTag change: not an import, pass.
  * Otherwise every changed path must be in the import allowlist, every file
    under apps/web/ must be byte-identical (content, executable bit, symlink
    target) to apps/web/ in the pinned tarball, and
    .seventwos/upstream-state.json must carry "pinnedTag" equal to the pin.
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
import urllib.request
from pathlib import PurePosixPath

PIN_PATH = ".seventwos/upstream-pin.json"
STATE_PATH = ".seventwos/upstream-state.json"
LEDGER_PATH = ".seventwos/upstream-ledger.jsonl"
WEB_PREFIX = "apps/web/"
# The workspace lockfile and catalog must change with the imported app.
ALLOWED_FILES = {STATE_PATH, LEDGER_PATH, "pnpm-lock.yaml", "pnpm-workspace.yaml"}
MAX_TARBALL_BYTES = 200 * 1024 * 1024


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
    if any(p == WEB_PREFIX.rstrip("/") or p.startswith(WEB_PREFIX) for p in paths):
        return True
    if STATE_PATH in paths:
        return pinned_tag_at(base) != pinned_tag_at(head)
    return False


def pinned_tag_at(ref: str):
    try:
        return json.loads(git("show", f"{ref}:{STATE_PATH}")).get("pinnedTag")
    except (subprocess.CalledProcessError, json.JSONDecodeError, AttributeError):
        return None


def check_allowlist(paths: list[str]) -> list[str]:
    return [p for p in paths if not (p.startswith(WEB_PREFIX) or p in ALLOWED_FILES)]


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
            if not rel.startswith(WEB_PREFIX):
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
        raise VerifyError("tarball has no apps/web/ files")
    return tree


def git_tree(head: str) -> dict[str, tuple[str, bytes]]:
    out = git("ls-tree", "-r", "-z", "--full-tree", head, "--", WEB_PREFIX.rstrip("/"))
    tree: dict[str, tuple[str, bytes]] = {}
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, kind, obj = meta.split()
        if kind != "blob":
            raise VerifyError(f"unsupported entry in apps/web: {path} ({kind})")
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
            problems.append(f"content differs: {path}")
    return problems


def verify(base: str, head: str, fetch=download) -> str:
    pin = read_pin(base)
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
        raise VerifyError(f"apps/web differs from {pin['repository']} {pin['tag']} ({len(problems)} problems):\n  {shown}")
    return f"pass: apps/web is byte-identical to {pin['repository']} {pin['tag']}"


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
