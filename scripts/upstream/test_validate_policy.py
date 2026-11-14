import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("validate_policy.py")
SPEC = importlib.util.spec_from_file_location("validate_policy", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ValidatePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy, cls.state = VALIDATOR.validate_policy_files()

    def test_repository_policy_is_valid(self) -> None:
        VALIDATOR.validate_ledger()

    def test_downloaded_bundle_selection_is_rejected(self) -> None:
        state = dict(self.state, selectedBundle={"tag": "v1.12.27"})
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "no downloaded bundle"):
            VALIDATOR.validate_policy_semantics(self.policy, state, VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["path_map"]), VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["invariants"]))

    def test_bundle_url_prefix_is_rejected(self) -> None:
        policy = json.loads(json.dumps(self.policy))
        policy["upstream"]["bundleReleaseUrlPrefix"] = "https://example.invalid/"
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "downloaded web bundles"):
            VALIDATOR.validate_policy_semantics(policy, self.state, VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["path_map"]), VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["invariants"]))

    def test_weakened_invariant_is_rejected(self) -> None:
        invariants = VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["invariants"])
        invariants["invariants"][0]["statement"] = "weakened"
        with self.assertRaisesRegex(VALIDATOR.ValidationError, "invariant"):
            VALIDATOR.validate_policy_semantics(self.policy, self.state, VALIDATOR.load_json(VALIDATOR.REQUIRED_FILES["path_map"]), invariants)

    def test_ledger_has_supersession_entry(self) -> None:
        lines = VALIDATOR.REQUIRED_FILES["ledger"].read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0])["eventId"], "baseline-element-web-v1.12.27-recorded")
        self.assertEqual(json.loads(lines[1])["supersedes"], "baseline-element-web-v1.12.27-recorded")


if __name__ == "__main__":
    unittest.main()
