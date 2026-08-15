import unittest

from auditor.economics_audit import audit_claim


class EconomicsAuditTests(unittest.TestCase):
    def base_claim(self):
        return {
            "schema": "economics-receipt/v0.1",
            "metric": "INFRASTRUCTURE_CONTRIBUTION",
            "period": "MODEL-v0.3",
            "currency": "USD",
            "value": 535560,
            "economic_state": "MODELED",
            "accounting_class": "UNCLASSIFIED",
            "classification_version": "economics-v0.3",
            "calculation": {
                "kind": "SUBTRACTION",
                "left": 688560,
                "right": 153000,
                "tolerance": 0,
            },
            "sources": [
                {
                    "source_id": "MODEL-001",
                    "evidence_class": "MODELED_ASSUMPTION",
                    "period": "MODEL-v0.3",
                }
            ],
            "authority_created": False,
        }

    def test_modeled_contribution_passes(self):
        receipt = audit_claim(self.base_claim())
        self.assertEqual(receipt["verdict"], "PASS")
        self.assertFalse(receipt["authority_created"])

    def test_verified_arr_without_evidence_is_blocked(self):
        claim = self.base_claim()
        claim.update(
            {
                "metric": "VERIFIED_ARR",
                "economic_state": "VERIFIED",
                "accounting_class": "REVENUE",
                "recurring_basis": True,
                "sources": [],
            }
        )
        receipt = audit_claim(claim)
        self.assertEqual(receipt["verdict"], "BLOCKED")
        controls = {item["control"] for item in receipt["findings"]}
        self.assertIn("ECON-001", controls)
        self.assertIn("ECON-005", controls)

    def test_modeled_gross_margin_with_unclassified_costs_requires_review(self):
        claim = self.base_claim()
        claim.update(
            {
                "metric": "GROSS_MARGIN",
                "value": 0.778,
                "calculation": {
                    "kind": "RATIO",
                    "left": 535560,
                    "right": 688560,
                    "tolerance": 0.0003,
                },
                "unclassified_direct_costs": ["human verification labor"],
            }
        )
        receipt = audit_claim(claim)
        self.assertEqual(receipt["verdict"], "REVIEW_REQUIRED")
        self.assertIn("ECON-003", {item["control"] for item in receipt["findings"]})

    def test_calculation_mismatch_is_blocked(self):
        claim = self.base_claim()
        claim["value"] = 1
        receipt = audit_claim(claim)
        self.assertEqual(receipt["verdict"], "BLOCKED")
        self.assertIn("ECON-005", {item["control"] for item in receipt["findings"]})

    def test_authority_creation_is_blocked(self):
        claim = self.base_claim()
        claim["authority_created"] = True
        receipt = audit_claim(claim)
        self.assertEqual(receipt["verdict"], "BLOCKED")
        self.assertIn("ECON-009", {item["control"] for item in receipt["findings"]})


if __name__ == "__main__":
    unittest.main()
