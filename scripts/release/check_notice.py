#!/usr/bin/env python3
"""Require an AGPL source notice in packaged desktop configuration."""
import argparse, json
from pathlib import Path
parser=argparse.ArgumentParser(); parser.add_argument("config"); args=parser.parse_args()
config=json.loads(Path(args.config).read_text())
notice=config.get("source_code_notice"); url=config.get("source_code_url")
if not isinstance(notice,str) or not ("AGPL" in notice or "Affero General Public License" in notice): raise SystemExit("source_code_notice must identify AGPL")
if not isinstance(url,str) or not url.startswith("https://"): raise SystemExit("source_code_url must be HTTPS")
print("AGPL source notice valid")
