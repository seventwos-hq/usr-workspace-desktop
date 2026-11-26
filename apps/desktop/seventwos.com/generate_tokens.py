#!/usr/bin/env python3
"""Generate and verify Seventwos Desktop + Web design tokens from tokens.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKENS_PATH = ROOT / "tokens.json"
CSS_PATH = ROOT / "tokens.css"
CONFIG_PATHS = (ROOT / "release/config.json", ROOT / "preview/config.json")


def render_css(tokens: dict) -> str:
    brand = tokens["brand"]
    typo = tokens["typography"]
    scale = typo["scale"]
    radii = tokens["radii"]
    light_cpd = tokens["themes"]["light"]["compound"]
    dark_cpd = tokens["themes"]["dark"]["compound"]

    lines = [
        "/* Generated from apps/desktop/seventwos.com/tokens.json — do not edit by hand. */",
        ":root {",
        f"  --brand-red: {brand['red']};",
        f"  --brand-red-dark: {brand['redDark']};",
        f"  --brand-blue: {brand['blue']};",
        f"  --brand-blue-dark: {brand['blueDark']};",
        f"  --brand-critical: {brand['critical']};",
        f"  --font-sans: {typo['fontSans']};",
        f"  --text-display: {scale['display']};",
        f"  --text-h1: {scale['h1']};",
        f"  --text-h2: {scale['h2']};",
        f"  --text-h3: {scale['h3']};",
        f"  --text-subtitle: {scale['subtitle']};",
        f"  --text-body: {scale['body']};",
        f"  --text-body-sm: {scale['bodySm']};",
        f"  --text-caption: {scale['caption']};",
        f"  --text-fine: {scale['fine']};",
        f"  --text-micro: {scale['micro']};",
        f"  --radius-sm: {radii['sm']};",
        f"  --radius-md: {radii['md']};",
        f"  --radius-lg: {radii['lg']};",
        f"  --radius-pill: {radii['pill']};",
    ]
    for k, v in light_cpd.items():
        lines.append(f"  {k}: {v};")
    lines.append("}")
    lines.append("")
    lines.append('[data-theme="dark"] {')
    for k, v in dark_cpd.items():
        lines.append(f"  {k}: {v};")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def expected_themes(tokens: dict) -> list[dict]:
    return [tokens["themes"]["dark"], tokens["themes"]["light"]]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    css = render_css(tokens)
    themes = expected_themes(tokens)

    if args.write:
        CSS_PATH.write_text(css, encoding="utf-8")
        for cfg_path in CONFIG_PATHS:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["setting_defaults"]["custom_themes"] = themes
            cfg_path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
        return 0

    errors: list[str] = []
    if not CSS_PATH.exists() or CSS_PATH.read_text(encoding="utf-8") != css:
        errors.append(f"{CSS_PATH.name} is out of sync with tokens.json")
    for cfg_path in CONFIG_PATHS:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if cfg.get("setting_defaults", {}).get("custom_themes") != themes:
            errors.append(f"{cfg_path.relative_to(ROOT)} custom_themes out of sync with tokens.json")
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    print("OK: tokens.css and desktop configs match tokens.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
