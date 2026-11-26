import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class SeventwosTokenTests(unittest.TestCase):
    def test_canonical_tokens_brand_and_targets(self) -> None:
        tokens = json.loads((ROOT / "tokens.json").read_text(encoding="utf-8"))
        self.assertEqual(tokens["targets"], ["desktop", "web"])
        self.assertEqual(tokens["brand"]["red"], "#ce2d4f")
        self.assertEqual(tokens["brand"]["redDark"], "#b02543")
        self.assertEqual(tokens["brand"]["blue"], "#1369a8")
        self.assertEqual(tokens["brand"]["blueDark"], "#0f5a91")
        self.assertIn("Inter", tokens["typography"]["fontSans"])
        self.assertIn("dark", tokens["themes"])
        self.assertIn("light", tokens["themes"])

    def test_generator_check_passes(self) -> None:
        res = subprocess.run(
            [sys.executable, str(ROOT / "generate_tokens.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
