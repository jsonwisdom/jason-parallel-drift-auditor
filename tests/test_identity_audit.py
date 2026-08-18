import unittest

from auditor.identity_audit import audit_identity


class IdentityAuditTests(unittest.TestCase):
    def base_claim(self):
        return {
            "schema": "identity-audit-envelope/v0.1",
            "identity_label": "jaywisdom.eth",
            "identity_class": "OPERATOR_LABEL",
            "declared_association": True,
            "independent_person_bind": False,
            "ens_resolution_checked": False,
            "wallet_ownership_proven": False,
            "legal_identity_proven": False,
            "sources": [
                {
                    "source_id": "drive:economics-auditor-mechanics-v0.1",
                    "evidence_class": "USER_CONTROLLED_RECORD",
                    "uri": "gdrive:1SdtYnvpcwEUYmyEcyitZRp01xYOfMVXTbzAal6Z9OKY",
                }
            ],
            "disposition": "PASS",
            "authority_created": False,
        }

    def test_operator_label_passes_without_identity_promotion(self):
        receipt = audit_identity(self.base_claim())
        self.assertEqual(receipt["verdict"], "PASS")
        self.assertFalse(receipt["authority_created"])

    def test_wallet_ownership_without_control_proof_holds(self):
        claim = self.base_claim()
        claim["wallet_ownership_proven"] = True
        claim["disposition"] = "HOLD"
        receipt = audit_identity(claim)
        self.assertEqual(receipt["verdict"], "HOLD")
        self.assertIn("ID-011", {item["control"] for item in receipt["findings"]})

    def test_person_binding_without_independent_evidence_holds(self):
        claim = self.base_claim()
        claim["independent_person_bind"] = True
        claim["disposition"] = "HOLD"
        receipt = audit_identity(claim)
        self.assertEqual(receipt["verdict"], "HOLD")
        self.assertIn("ID-012", {item["control"] for item in receipt["findings"]})

    def test_legal_identity_without_person_binding_conflicts(self):
        claim = self.base_claim()
        claim["legal_identity_proven"] = True
        claim["disposition"] = "CONFLICT"
        receipt = audit_identity(claim)
        self.assertEqual(receipt["verdict"], "CONFLICT")
        self.assertIn("ID-013", {item["control"] for item in receipt["findings"]})

    def test_authority_creation_is_rejected(self):
        claim = self.base_claim()
        claim["authority_created"] = True
        claim["disposition"] = "REJECT"
        receipt = audit_identity(claim)
        self.assertEqual(receipt["verdict"], "REJECT")
        self.assertIn("ID-009", {item["control"] for item in receipt["findings"]})


if __name__ == "__main__":
    unittest.main()
