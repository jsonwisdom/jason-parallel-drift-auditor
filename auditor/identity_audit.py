#!/usr/bin/env python3
"""Deterministic identity-claim auditor for identity-audit-envelope/v0.1.

The auditor checks promotion gates for labels, account associations, control
proofs, person bindings, and authority receipts. It never creates identity or
authority; it only evaluates the supplied envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

IDENTITY_CLASSES = {
    "OPERATOR_LABEL",
    "ACCOUNT_LABEL",
    "ENS_LABEL",
    "WALLET_LABEL",
    "NATURAL_PERSON_CLAIM",
}

BYTE_BOUND_CLASSES = {
    "CRYPTOGRAPHIC_CONTROL_PROOF",
    "INDEPENDENT_IDENTITY_EVIDENCE",
    "LAWFUL_AUTHORITY_RECEIPT",
}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def add(findings: list[dict], control: str, state: str, title: str, evidence: str) -> None:
    findings.append({"control": control, "state": state, "title": title, "evidence": evidence})


def audit_identity(claim: dict) -> dict:
    findings: list[dict] = []

    if claim.get("schema") != "identity-audit-envelope/v0.1":
        add(findings, "ID-001", "REJECT", "Unsupported identity schema", repr(claim.get("schema")))

    label = claim.get("identity_label")
    if not isinstance(label, str) or not label.strip():
        add(findings, "ID-002", "REJECT", "Identity label is missing", repr(label))

    identity_class = claim.get("identity_class")
    if identity_class not in IDENTITY_CLASSES:
        add(findings, "ID-003", "REJECT", "Identity class is invalid", repr(identity_class))

    if claim.get("authority_created") is not False:
        add(findings, "ID-009", "REJECT", "Envelope attempts to create authority", "authority_created must equal false")

    sources = claim.get("sources")
    if not isinstance(sources, list):
        sources = []
        add(findings, "ID-004", "REJECT", "Sources are missing", "sources must be an array")

    source_ids: set[str] = set()
    evidence_classes: set[str] = set()

    for source in sources:
        if not isinstance(source, dict):
            add(findings, "ID-004", "REJECT", "Malformed source entry", repr(source))
            continue
        source_id = source.get("source_id")
        evidence_class = source.get("evidence_class")
        if source_id in source_ids:
            add(findings, "ID-005", "CONFLICT", "Duplicate source identifier", repr(source_id))
        if isinstance(source_id, str) and source_id:
            source_ids.add(source_id)
        if isinstance(evidence_class, str) and evidence_class:
            evidence_classes.add(evidence_class)
        if evidence_class in BYTE_BOUND_CLASSES:
            digest = source.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                add(
                    findings,
                    "ID-006",
                    "HOLD",
                    "Byte-bound identity evidence lacks SHA-256",
                    f"source_id={source_id!r}; evidence_class={evidence_class!r}",
                )

    if claim.get("declared_association") is True and not (
        {"SELF_DECLARATION", "USER_CONTROLLED_RECORD"} & evidence_classes
    ):
        add(
            findings,
            "ID-010",
            "HOLD",
            "Declared association lacks a declaration receipt",
            "requires SELF_DECLARATION or USER_CONTROLLED_RECORD",
        )

    if claim.get("wallet_ownership_proven") is True and "CRYPTOGRAPHIC_CONTROL_PROOF" not in evidence_classes:
        add(
            findings,
            "ID-011",
            "HOLD",
            "Wallet ownership is promoted without control proof",
            "requires CRYPTOGRAPHIC_CONTROL_PROOF",
        )

    if claim.get("independent_person_bind") is True and "INDEPENDENT_IDENTITY_EVIDENCE" not in evidence_classes:
        add(
            findings,
            "ID-012",
            "HOLD",
            "Person binding lacks independent evidence",
            "requires INDEPENDENT_IDENTITY_EVIDENCE",
        )

    if claim.get("legal_identity_proven") is True:
        if claim.get("independent_person_bind") is not True:
            add(
                findings,
                "ID-013",
                "CONFLICT",
                "Legal identity is asserted without an independent person binding",
                "independent_person_bind must be true first",
            )
        if "INDEPENDENT_IDENTITY_EVIDENCE" not in evidence_classes:
            add(
                findings,
                "ID-013",
                "HOLD",
                "Legal identity lacks independent identity evidence",
                "requires INDEPENDENT_IDENTITY_EVIDENCE",
            )

    state_rank = {"PASS": 0, "HOLD": 1, "CONFLICT": 2, "REJECT": 3}
    computed = max(
        (item["state"] for item in findings),
        key=lambda state: state_rank[state],
        default="PASS",
    )

    declared_disposition = claim.get("disposition")
    if declared_disposition not in state_rank:
        add(findings, "ID-014", "REJECT", "Disposition is invalid", repr(declared_disposition))
        computed = "REJECT"
    elif state_rank[declared_disposition] < state_rank[computed]:
        add(
            findings,
            "ID-014",
            "CONFLICT",
            "Declared disposition is more promotional than replay result",
            f"declared={declared_disposition}; replayed={computed}",
        )
        computed = max(computed, "CONFLICT", key=lambda state: state_rank[state])

    clean_claim = dict(claim)
    clean_claim.pop("claim_sha256", None)
    claim_sha256 = canonical_sha256(clean_claim)

    receipt = {
        "schema": "identity-audit-receipt/v0.1",
        "auditor": "Jason Parallel-Drift Auditor / Identity v0.1",
        "identity_label": label,
        "claim_sha256": claim_sha256,
        "verdict": computed,
        "findings": findings,
        "authority_created": False,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claim", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    claim = json.loads(args.claim.read_text(encoding="utf-8"))
    receipt = audit_identity(claim)
    rendered = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 2 if receipt["verdict"] == "REJECT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
