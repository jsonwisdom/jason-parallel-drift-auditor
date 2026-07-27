import json
import tempfile
import unittest
from pathlib import Path

from auditor.audit import (
    DEFAULT_CONFIG,
    audit,
    load_config,
    render_sarif,
    term_count,
)


MISSION = """# Mission
operator: Jason
objective: test
deliverable: report
success condition: deterministic
cost: bounded
non-goals: mutation
stop condition: secret
"""


class AuditorTests(unittest.TestCase):
    def test_missing_mission_is_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            findings, _ = audit(Path(directory), DEFAULT_CONFIG)
            self.assertTrue(any(f.test_id == "JPA-001" for f in findings))

    def test_private_key_is_critical_and_suppressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MISSION.md").write_text(MISSION)
            (root / "secret.asc").write_text(
                "-----BEGIN PGP PRIVATE KEY BLOCK-----\nDO_NOT_PRINT\n"
            )
            findings, _ = audit(root, DEFAULT_CONFIG)
            hits = [f for f in findings if f.test_id == "SEC-002"]
            self.assertEqual(hits[0].severity, "critical")
            self.assertNotIn("DO_NOT_PRINT", hits[0].evidence)

    def test_infrastructure_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "MISSION.md").write_text(MISSION)
            (root / "scripts").mkdir()
            for index in range(3):
                (root / "scripts" / f"{index}.py").write_text("print('ok')")
            findings, metrics = audit(root, DEFAULT_CONFIG)
            self.assertGreaterEqual(metrics["infrastructure_ratio"], 0.6)
            self.assertTrue(any(f.test_id == "JPA-002" for f in findings))

    def test_custom_config_merges_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"thresholds": {"fail_severity": "high"}}))
            config = load_config(path)
            self.assertEqual(config["thresholds"]["fail_severity"], "high")
            self.assertIn("warn_infrastructure_ratio", config["thresholds"])

    def test_vendor_terms_do_not_match_substrings(self):
        self.assertEqual(term_count("associated software", "oci"), 0)
        self.assertEqual(term_count("Oracle dependency", "oracle"), 1)

    def test_sarif_preserves_file_location(self):
        report = {
            "findings": [
                {
                    "test_id": "SEC-001",
                    "severity": "high",
                    "title": "Sensitive file",
                    "evidence": "Observed",
                    "path": "secrets/example.asc",
                    "line": 7,
                }
            ]
        }
        result = render_sarif(report)["runs"][0]["results"][0]
        location = result["locations"][0]["physicalLocation"]
        self.assertEqual(location["artifactLocation"]["uri"], "secrets/example.asc")
        self.assertEqual(location["region"]["startLine"], 7)

    def test_location_completeness_uses_repository_fallback(self):
        report = {
            "findings": [
                {
                    "test_id": "JPA-002",
                    "severity": "medium",
                    "title": "Repository-level finding",
                    "evidence": "Observed",
                    "path": None,
                    "line": None,
                },
                {
                    "test_id": "SEC-003",
                    "severity": "high",
                    "title": "File-level finding",
                    "evidence": "Observed",
                    "path": ".github/workflows/audit.yml",
                    "line": 12,
                },
            ]
        }
        results = render_sarif(report)["runs"][0]["results"]
        self.assertTrue(all(result.get("locations") for result in results))
        fallback = results[0]["locations"][0]["physicalLocation"]
        self.assertEqual(fallback["artifactLocation"]["uri"], ".github/jpa-audit.json")
        self.assertEqual(fallback["region"]["startLine"], 1)


if __name__ == "__main__":
    unittest.main()
