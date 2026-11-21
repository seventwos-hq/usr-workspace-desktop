#!/usr/bin/env python3
"""Apply our reviewed changes (.seventwos/patches) to the upstream web app before a build.

apps/web and packages stay byte-identical to the pinned upstream release in git.
Our own changes live as patch files and are applied in the order given by
.seventwos/patches/series (one "<file>  <reason>" per line).

Fails closed: an unlisted or missing patch file, an empty reason, a symlinked patch,
or any patch that touches paths outside apps/web or packages or does not apply
exactly (no fuzz, no partial apply) stops the build.
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
RENAME_COPY_PREFIXES = ("rename from ", "rename to ", "copy from ", "copy to ")
SYMLINK_MODE_LINES = (
    "new file mode 120000",
    "old mode 120000",
    "new mode 120000",
    "deleted file mode 120000",
)


class PatchError(Exception):
    pass


def read_series(patch_dir: Path) -> list[tuple[str, str]]:
    resolved_dir = patch_dir.resolve()
    series_path = resolved_dir / SERIES
    if series_path.is_symlink() or not series_path.is_file():
        raise PatchError(f"{series_path} not found")
    entries: list[tuple[str, str]] = []
    for lineno, line in enumerate(series_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, reason = line.partition(" ")
        if (
            not name.endswith(".patch")
            or "/" in name
            or "\\" in name
            or ".." in name
        ):
            raise PatchError(f"series line {lineno}: bad patch name {name!r}")
        if (resolved_dir / name).is_symlink():
            raise PatchError(f"symlinked patch entry not allowed: {name}")
        if (resolved_dir / name).resolve().parent != resolved_dir:
            raise PatchError(f"series line {lineno}: bad patch name {name!r}")
        if not reason.strip():
            raise PatchError(f"series line {lineno}: {name} has no reason")
        if any(name == n for n, _ in entries):
            raise PatchError(f"series line {lineno}: {name} listed twice")
        entries.append((name, reason.strip()))
    on_disk: list[str] = []
    for p in sorted(resolved_dir.iterdir(), key=lambda item: item.name):
        if p.name == SERIES:
            continue
        if p.is_symlink():
            raise PatchError(f"symlinked patch entry not allowed: {p.name}")
        if p.is_dir():
            raise PatchError(f"subdirectory in patch dir not allowed: {p.name}")
        if p.name.endswith(".patch") and p.is_file():
            on_disk.append(p.name)
    listed = [n for n, _ in entries]
    missing = sorted(set(listed) - set(on_disk))
    unlisted = sorted(set(on_disk) - set(listed))
    if missing:
        raise PatchError("listed but missing: " + ", ".join(missing))
    if unlisted:
        raise PatchError("patch files not in series: " + ", ".join(unlisted))
    return entries


def _norm_patch_path(raw: str, *, require_ab: bool) -> str | None:
    token = raw.split("\t", 1)[0].strip()
    if token == "/dev/null":
        return None
    if token.startswith('"') or token.endswith('"') or "\\" in token:
        raise PatchError(f"quoted or escaped patch path not allowed: {token!r}")
    if require_ab:
        if not token.startswith(("a/", "b/")):
            raise PatchError(f"patch header path must start with a/ or b/: {token!r}")
        return token[2:]
    return token


def touched_paths(patch: bytes) -> list[str]:
    paths: list[str] = []
    try:
        decoded = patch.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PatchError(f"patch is not valid UTF-8: {exc}") from exc
    for line in decoded.splitlines():
        if line in SYMLINK_MODE_LINES or (line.startswith("index ") and line.endswith(" 120000")):
            raise PatchError("symlink file modes (120000) are not allowed in patches")
        if line.startswith(("--- ", "+++ ")):
            norm = _norm_patch_path(line[4:], require_ab=True)
            if norm is not None:
                paths.append(norm)
        elif line.startswith("diff --git "):
            rest = line[len("diff --git "):].strip()
            if not rest.startswith("a/") or " b/" not in rest:
                raise PatchError(f"malformed diff --git header: {line!r}")
            a_part, b_part = rest.split(" b/", 1)
            a_norm = _norm_patch_path(a_part, require_ab=True)
            b_norm = _norm_patch_path("b/" + b_part, require_ab=True)
            if a_norm is not None:
                paths.append(a_norm)
            if b_norm is not None:
                paths.append(b_norm)
        elif line.startswith(RENAME_COPY_PREFIXES):
            for prefix in RENAME_COPY_PREFIXES:
                if line.startswith(prefix):
                    norm = _norm_patch_path(line[len(prefix):], require_ab=False)
                    if norm is not None:
                        paths.append(norm)
                    break
    return paths


def git_apply(root: Path, patch: bytes, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "apply", "--whitespace=nowarn", *flags, "-"],
                          cwd=root, input=patch, capture_output=True)


def apply_all(root: Path, patch_dir: Path) -> str:
    resolved_dir = patch_dir.resolve()
    entries = read_series(resolved_dir)
    patches = []
    for name, _ in entries:
        patch_path = (resolved_dir / name).resolve()
        if patch_path.parent != resolved_dir or patch_path.is_symlink():
            raise PatchError(f"{name}: invalid patch path")
        data = patch_path.read_bytes()
        try:
            paths = touched_paths(data)
        except PatchError as exc:
            raise PatchError(f"{name}: {exc}") from exc
        if not paths:
            raise PatchError(f"{name}: no file changes")
        bad = [
            p for p in paths
            if not p.startswith(ALLOWED_PREFIXES) or ".." in p.split("/") or p.startswith("/")
        ]
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
