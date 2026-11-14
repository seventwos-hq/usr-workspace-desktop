#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = ROOT / ".seventwos"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
MANDATORY_MAPPINGS = (
    ("apps/web/**", "apps/web/**", "protected-divergence"),
    ("apps/desktop/**", "apps/desktop/**", "selective-review"),
    ("packages/**", "packages/**", "selective-review"),
    ("modules/**", "modules/**", "protected-divergence"),
    (".github/workflows/**", ".github/workflows/**", "protected-divergence"),
    ("none", "apps/desktop/seventwos.org/**", "protected-divergence"),
    ("none", ".seventwos/**", "protected-divergence"),
)
MANDATORY_INVARIANTS = {
    "web-app-in-repo": "apps/web is required and must be built from this repository's source; the desktop client must package that local build.",
    "no-downloaded-web-bundle": "Desktop packaging must not download a prebuilt web bundle or depend on an upstream release key.",
    "protect-seventwos-divergence": "Seventwos UI, product, auth, storage, profile migration, configuration, and release paths require repository ownership review.",
    "assessment-only": "Upstream assessment automation may report candidates but may not apply changes, merge, or publish.",
    "append-only-ledger": "Existing upstream ledger entries may not be edited, reordered, or removed.",
}
UPSTREAM_REPOSITORY = "element-hq/element-web"
UPSTREAM_URL = "https://github.com/element-hq/element-web"
REQUIRED_FILES = {
    "policy": POLICY_DIR / "upstream-policy.json",
    "state": POLICY_DIR / "upstream-state.json",
    "path_map": POLICY_DIR / "upstream-path-map.json",
    "invariants": POLICY_DIR / "upstream-invariants.json",
    "ledger": POLICY_DIR / "upstream-ledger.jsonl",
}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"{path.relative_to(ROOT)}: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_policy_files() -> tuple[dict, dict]:
    for path in REQUIRED_FILES.values():
        require(path.is_file(), f"missing required policy file: {path.relative_to(ROOT)}")

    policy = load_json(REQUIRED_FILES["policy"])
    state = load_json(REQUIRED_FILES["state"])
    path_map = load_json(REQUIRED_FILES["path_map"])
    invariants = load_json(REQUIRED_FILES["invariants"])

    for name, value in (("policy", policy), ("state", state), ("path-map", path_map), ("invariants", invariants)):
        require(value.get("schemaVersion") == 1, f"unsupported upstream {name} schemaVersion")
    validate_policy_semantics(policy, state, path_map, invariants)
    validate_ledger()
    return policy, state


def validate_policy_semantics(policy: dict, state: dict, path_map: dict, invariants: dict) -> None:
    require(state.get("policyId") == policy.get("policyId"), "state policyId does not match policy")
    require(policy.get("integrationModel") == "desktop-shell-plus-in-repo-web-app", "unexpected integration model")
    require(policy.get("upstream", {}).get("repository") == UPSTREAM_REPOSITORY, "upstream repository is not the pinned Element Web repository")
    require(policy.get("upstream", {}).get("sourceUrl") == UPSTREAM_URL, "upstream source URL is not pinned")
    require("bundleReleaseUrlPrefix" not in policy.get("upstream", {}), "downloaded web bundles are not permitted")
    require(policy.get("webApp", {}).get("path") == "apps/web", "web app must live in apps/web")
    require(policy.get("webApp", {}).get("source") == "in-repo", "web app must be built from in-repo source")
    require(state.get("webApp", {}).get("source") == "in-repo", "state must record the in-repo web app")
    require(state.get("selectedBundle") is None, "no downloaded bundle may be selected")
    require(policy.get("protectedDivergence", {}).get("pathMap") == ".seventwos/upstream-path-map.json", "protected divergence must use the pinned path map")
    require(policy.get("protectedDivergence", {}).get("codeowners") == "CODEOWNERS", "protected divergence must require CODEOWNERS")
    require(policy.get("ledger", {}).get("path") == ".seventwos/upstream-ledger.jsonl", "ledger path must remain pinned")
    require(policy.get("ledger", {}).get("appendOnly") is True, "ledger must remain append-only")
    require((ROOT / "apps" / "web" / "package.json").is_file(), "apps/web must be present")

    mappings = path_map.get("mappings")
    require(isinstance(mappings, list), "path-map mappings must be an array")
    actual_mappings = {(item.get("upstream"), item.get("local"), item.get("mode")) for item in mappings}
    require(set(MANDATORY_MAPPINGS) <= actual_mappings, "mandatory path-map protection was removed or weakened")

    actual_invariants = {
        item.get("id"): item
        for item in invariants.get("invariants", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for invariant_id, statement in MANDATORY_INVARIANTS.items():
        invariant = actual_invariants.get(invariant_id, {})
        require(
            invariant.get("severity") == "error" and invariant.get("statement") == statement,
            f"mandatory invariant {invariant_id} was removed or weakened",
        )


def validate_ledger() -> None:
    entries = []
    for line_number, line in enumerate(REQUIRED_FILES["ledger"].read_text(encoding="utf-8").splitlines(), start=1):
        require(line.strip() != "", f"ledger line {line_number} must not be blank")
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValidationError(f"ledger line {line_number}: {error}") from error
        require(isinstance(entry, dict), f"ledger line {line_number} must be an object")
        require(entry.get("sequence") == line_number, f"ledger line {line_number} has a non-contiguous sequence")
        require(entry.get("schemaVersion") == 1 and entry.get("eventId"), f"ledger line {line_number} is missing required identity")
        entries.append(entry)
    require(entries, "upstream ledger must contain at least one entry")
    require(len({entry["eventId"] for entry in entries}) == len(entries), "ledger event IDs must be unique")


def validate_append_only(base_ref: str | None, allow_ledger_introduction: bool = False) -> None:
    require(bool(base_ref), "a base ref is required for append-only validation")
    base_commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(base_commit.returncode == 0, f"cannot resolve append-only base ref {base_ref}")
    result = subprocess.run(
        ["git", "show", f"{base_ref}:.seventwos/upstream-ledger.jsonl"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        require(allow_ledger_introduction, "cannot read ledger from base ref; refusing to bypass append-only validation")
        tree = subprocess.run(
            ["git", "ls-tree", "--name-only", base_ref, ".seventwos/upstream-ledger.jsonl"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        require(tree.returncode == 0 and not tree.stdout.strip(), "ledger introduction is allowed only when the base has no ledger")
        return
    current = REQUIRED_FILES["ledger"].read_text(encoding="utf-8")
    require(current.startswith(result.stdout), "upstream ledger is append-only; existing bytes changed or were removed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Seventwos selective upstream policy")
    parser.add_argument("--base-ref", help="Git ref used to enforce append-only ledger history")
    parser.add_argument("--allow-ledger-introduction", action="store_true", help="Allow the ledger only when a valid base ref has no ledger")
    args = parser.parse_args()

    try:
        validate_policy_files()
        if args.base_ref or args.allow_ledger_introduction:
            validate_append_only(args.base_ref, args.allow_ledger_introduction)
    except ValidationError as error:
        print(f"upstream policy validation failed: {error}", file=sys.stderr)
        return 1

    print("upstream policy validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
