#!/usr/bin/env python3
"""Build and lint a reproducible AGPL corresponding-source archive."""
import argparse, gzip, hashlib, io, json, subprocess, tarfile
from pathlib import Path


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    archive = Path(args.output)
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    files, modes = [], {}
    for entry in git(root, "ls-tree", "-rz", "--full-tree", "HEAD").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, _object = metadata.split()
        decoded = name.decode("utf-8", "surrogateescape")
        if kind == b"blob":
            files.append(decoded)
            modes[decoded] = 0o755 if mode == b"100755" else 0o644
    required = ("LICENSE-AGPL-3.0", "apps/desktop/package.json", "apps/desktop/src/updater.ts")
    if not all(item in files for item in required):
        raise SystemExit("source archive missing required AGPL files")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as raw_archive:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_archive, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for name in sorted(files):
                    raw = git(root, "show", f"HEAD:{name}")
                    info = tarfile.TarInfo(name)
                    info.size = len(raw)
                    info.mode = modes[name]
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    tar.addfile(info, io.BytesIO(raw))
                notice = (json.dumps({"commit": commit, "license": "AGPL-3.0-only", "source_offer": "Corresponding source for distributed desktop binaries."}, sort_keys=True) + "\n").encode()
                info = tarfile.TarInfo("SOURCE-OFFER.json")
                info.size = len(notice)
                info.mode = 0o644
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                tar.addfile(info, io.BytesIO(notice))
    if args.check:
        with tarfile.open(archive, "r:gz") as tar:
            missing = set(required) - set(tar.getnames())
            if missing:
                raise SystemExit(f"archive check failed: {sorted(missing)}")
            tar.getmember("SOURCE-OFFER.json")
    print(hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
