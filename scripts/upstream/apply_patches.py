#!/usr/bin/env python3
"""Apply our reviewed changes (.seventwos/patches) to the upstream web app before a build.

apps/web and packages stay byte-identical to the pinned upstream release in git.
Our own changes live as patch files and are applied in the order given by
.seventwos/patches/series (one "<file>  <reason>" per line).

Fails closed: an unlisted or missing patch file, an empty reason, or any patch
that does not apply exactly (no fuzz, no partial apply) stops the build.
Run it once on a clean checkout; a second run fails because the tree has changed.
Exit 0 = applied, 1 = a patch does not apply, 2 = setup error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PATCH_DIR = ".seventwos/patches"
SERIES = "series"
# Patches may only touch the upstream copy.
ALLOWED_PREFIXES = ("apps/web/", "packages/")


class PatchError(Exception):
    pass


def read_series(patch_dir: Path) -> list[tuple[str, str]]:
    series_path = patch_dir / SERIES
    if not series_path.is_file():
        raise PatchError(f"{series_path} not found")
    entries: list[tuple[str, str]] = []
    for lineno, line in enumerate(series_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition(" ")
        if not name.endswith(".patch") or "/" in name:
            raise PatchError(f"series line {lineno}: bad patch name {name!r}")
        if not reason.strip():
            raise PatchError(f"series line {lineno}: {name} has no reason")
        if any(name == n for n, _ in entries):
            raise PatchError(f"series line {lineno}: {name} listed twice")
        entries.append((name, reason.strip()))
    on_disk = sorted(p.name for p in patch_dir.glob("*.patch"))
    listed = [n for n, _ in entries]
    missing = sorted(set(listed) - set(on_disk))
    unlisted = sorted(set(on_disk) - set(listed))
    if missing:
        raise PatchError("listed but missing: " + ", ".join(missing))
    if unlisted:
        raise PatchError("patch files not in series: " + ", ".join(unlisted))
    return entries


def touched_paths(patch: bytes) -> list[str]:
    paths = []
    for line in patch.decode(errors="replace").splitlines():
        if line.startswith(("--- ", "+++ ")):
            p = line[4:].split("\t")[0]
            if p != "/dev/null":
                paths.append(p.split("/", 1)[1] if p[:2] in ("a/", "b/") else p)
    return paths


def git_apply(root: Path, patch: bytes, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "apply", "--whitespace=nowarn", *flags, "-"],
                          cwd=root, input=patch, capture_output=True)


def apply_all(root: Path, patch_dir: Path) -> str:
    entries = read_series(patch_dir)
    patches = []
    for name, _ in entries:
        data = (patch_dir / name).read_bytes()
        paths = touched_paths(data)
        if not paths:
            raise PatchError(f"{name}: no file changes")
        bad = [p for p in paths if not p.startswith(ALLOWED_PREFIXES) or ".." in p.split("/")]
        if bad:
            raise PatchError(f"{name}: touches paths outside the upstream copy: {', '.join(bad[:5])}")
        patches.append((name, data))
    if not patches:
        return "no patches listed"
    # Later patches may build on earlier ones, so each is checked and then applied in order.
    for name, data in patches:
        res = git_apply(root, data, "--check")
        if res.returncode:
            raise PatchError(f"{name} does not apply:\n{res.stderr.decode().strip()}")
        res = git_apply(root, data)
        if res.returncode:
            raise PatchError(f"{name} failed to apply:\n{res.stderr.decode().strip()}")
    return f"applied {len(patches)} patches: " + ", ".join(n for n, _ in patches)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root holding apps/web (default: .)")
    ap.add_argument("--patch-dir", default=None, help=f"default: <root>/{PATCH_DIR}")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    patch_dir = Path(args.patch_dir).resolve() if args.patch_dir else root / PATCH_DIR
    try:
        print(apply_all(root, patch_dir))
    except PatchError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
