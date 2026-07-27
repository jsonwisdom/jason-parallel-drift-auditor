import unittest

from auditor.portfolio import classify


class PortfolioTests(unittest.TestCase):
    def base(self):
        return {
            "age_days": 1,
            "title": "Deliver report",
            "body": "Mission: deliver the requested report.",
            "mergeable": True,
            "draft": False,
        }

    def test_failed_check_blocks(self):
        state, _ = classify(self.base(), {"failed": 1, "pending": 0}, 30)
        self.assertEqual(state, "BLOCKED")

    def test_stale_is_observed(self):
        pr = self.base()
        pr["age_days"] = 31
        state, _ = classify(pr, {"failed": 0, "pending": 0}, 30)
        self.assertEqual(state, "STALE")

    def test_empty_body_is_mission_unclear(self):
        pr = self.base()
        pr["body"] = ""
        state, _ = classify(pr, {"failed": 0, "pending": 0}, 30)
        self.assertEqual(state, "MISSION_UNCLEAR")

    def test_governance_language_is_drift_suspect(self):
        pr = self.base()
        pr["body"] = "Create governance framework."
        state, _ = classify(pr, {"failed": 0, "pending": 0}, 30)
        self.assertEqual(state, "DRIFT_SUSPECT")

    def test_clean_pr_requires_human_review(self):
        state, _ = classify(self.base(), {"failed": 0, "pending": 0}, 30)
        self.assertEqual(state, "READY_FOR_HUMAN_REVIEW")


if __name__ == "__main__":
    unittest.main()
