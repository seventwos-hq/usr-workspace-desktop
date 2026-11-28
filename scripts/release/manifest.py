#!/usr/bin/env python3
"""Generate and verify deterministic, signed desktop release manifests."""
from __future__ import annotations
import argparse, base64, hashlib, ipaddress, json, os, re, subprocess, sys, tempfile
from urllib.parse import urlsplit
from pathlib import Path

PLATFORMS = {"windows": "win-x64.msi", "win-x64": "win-x64.msi", "windows-x64": "win-x64.msi", "win-arm64": "win-arm64.msi", "windows-arm64": "win-arm64.msi", "macos": "macos.dmg", "linux": "linux-amd64.deb", "linux-amd64": "linux-amd64.deb", "linux-arm64": "linux-arm64.deb", "source": "source.tar.gz"}
CHANNELS = {"stable", "beta"}

def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def sign(payload: dict, key_path: Path) -> dict:
    content = canonical(payload)
    with tempfile.NamedTemporaryFile() as signature, tempfile.NamedTemporaryFile() as payload_file:
        payload_file.write(content); payload_file.flush()
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key_path), "-rawin", "-out", signature.name , "-in", payload_file.name,], check=True, timeout=30)
        payload["signature"] = {"algorithm": "ed25519", "value": base64.b64encode(Path(signature.name).read_bytes()).decode()}
    return payload

def verify(document: dict, public_key: Path) -> None:
    signature = document.get("signature")
    if not isinstance(signature, dict) or signature.get("algorithm") != "ed25519": fail("unsupported signature")
    encoded = signature.get("value")
    if not isinstance(encoded, str): fail("missing signature")
    try: raw = base64.b64decode(encoded, validate=True)
    except Exception: fail("invalid signature encoding")
    payload = {k: v for k, v in document.items() if k != "signature"}
    with tempfile.NamedTemporaryFile() as sig, tempfile.NamedTemporaryFile() as data:
        sig.write(raw); sig.flush(); data.write(canonical(payload)); data.flush()
        result = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public_key), "-rawin", "-in", data.name, "-sigfile", sig.name], capture_output=True, timeout=30)
    if result.returncode: fail("signature verification failed")

def valid_hostname(hostname: str) -> bool:
    if not hostname or any(ord(char) < 32 or ord(char) == 127 for char in hostname): return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if re.fullmatch(r"[0-9.]+", hostname): return False
    if len(hostname) > 253: return False
    labels = hostname.split(".")
    return all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)

def build(args: argparse.Namespace) -> dict:
    if args.channel not in CHANNELS: fail("channel must be stable or beta")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in args.base_url):
        fail("base URL must not contain whitespace or ASCII control characters")
    try:
        base = urlsplit(args.base_url)
        hostname = base.hostname
        port = base.port
    except ValueError:
        fail("base URL must be a valid HTTPS URL")
    raw_netloc = base.netloc.rsplit("@", 1)[-1]
    if "?" in args.base_url or "#" in args.base_url or raw_netloc.endswith(":"):
        fail("base URL must have a valid port and no query or fragment")
    if (base.scheme.lower() != "https" or not base.netloc or not valid_hostname(hostname)
            or base.username is not None or base.password is not None or port is not None and not 1 <= port <= 65535):
        fail("base URL must use https with a valid host and no credentials, query, or fragment")
    release = Path(args.release_dir).resolve()
    entries = {}
    for platform, name in sorted(PLATFORMS.items()):
        artifact = release / name
        if not artifact.is_file(): fail(f"missing {artifact}")
        entries[platform] = {"url": f"{args.base_url.rstrip(chr(47))}/v{args.version}/{name}", "version": args.version, "sha256": sha256(artifact)}
    return {"schema": 1, "channel": args.channel, "version": args.version, "release": entries}

def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate"); gen.add_argument("--release-dir", required=True); gen.add_argument("--base-url", required=True); gen.add_argument("--version", required=True); gen.add_argument("--channel", required=True); gen.add_argument("--key", required=True)
    ver = sub.add_parser("verify"); ver.add_argument("--manifest", required=True); ver.add_argument("--key", required=True); ver.add_argument("--version", required=False); ver.add_argument("--channel", required=True)
    args = parser.parse_args()
    if args.command == "generate":
        output = sign(build(args), Path(args.key)); print(canonical(output).decode()); return
    path = Path(args.manifest); document = json.loads(path.read_text())
    verify(document, Path(args.key))
    if document.get("channel") != args.channel: fail("channel mismatch")
    if args.version and document.get("version") != args.version: fail("version mismatch")
    if document.get("schema") != 1 or set(document.get("release", {})) != set(PLATFORMS): fail("invalid manifest shape")
    print(f"verified {args.channel} manifest {document.get('version')}")
if __name__ == "__main__": main()
