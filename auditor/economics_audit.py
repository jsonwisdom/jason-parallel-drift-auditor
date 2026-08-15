#!/usr/bin/env python3
"""Replay-grade economics claim auditor.

Reads one economics-receipt/v0.1 claim, checks state/classification gates,
replays supported calculations, and emits a deterministic audit receipt.
It never mutates the source claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

STATES = ("MODELED", "PIPELINE", "CONTRACTED", "INVOICED", "COLLECTED", "VERIFIED")
ACCOUNTING_CLASSES = (
    "REVENUE",
    "COGS",
    "OPERATING_EXPENSE",
    "CAPITAL_EXPENDITURE",
    "UNCLASSIFIED",
)

REQUIRED_EVIDENCE = {
    "MODELED": {"MODELED_ASSUMPTION"},
    "PIPELINE": {"PIPELINE_RECORD"},
    "CONTRACTED": {"SIGNED_CONTRACT"},
    "INVOICED": {"SIGNED_CONTRACT", "INVOICE"},
    "COLLECTED": {"SIGNED_CONTRACT", "INVOICE", "PAYMENT_RECEIPT"},
    "VERIFIED": {"SIGNED_CONTRACT", "INVOICE", "PAYMENT_RECEIPT", "REPLAY_RECEIPT"},
}

BYTE_BOUND_CLASSES = {"SIGNED_CONTRACT", "INVOICE", "PAYMENT_RECEIPT", "REPLAY_RECEIPT"}
SEVERITY_RANK = {"info": 0, "medium": 1, "high": 2, "critical": 3}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def add(findings: list[dict], control: str, severity: str, title: str, evidence: str) -> None:
    findings.append(
        {"control": control, "severity": severity, "title": title, "evidence": evidence}
    )


def replay_calculation(claim: dict, findings: list[dict]) -> None:
    calculation = claim.get("calculation") or {"kind": "NONE"}
    kind = calculation.get("kind", "NONE")
    if kind == "NONE":
        return

    left = calculation.get("left")
    right = calculation.get("right")
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        add(findings, "ECON-005", "critical", "Calculation operands are incomplete", "left/right must be numeric")
        return

    if kind == "SUBTRACTION":
        replayed = left - right
    elif kind == "RATIO":
        if right == 0:
            add(findings, "ECON-005", "critical", "Calculation cannot replay", "ratio denominator is zero")
            return
        replayed = left / right
    else:
        add(findings, "ECON-005", "critical", "Unsupported calculation kind", str(kind))
        return

    claimed = claim.get("value")
    tolerance = calculation.get("tolerance", 1e-9)
    if not isinstance(claimed, (int, float)) or abs(replayed - claimed) > tolerance:
        add(
            findings,
            "ECON-005",
            "critical",
            "Claimed value does not replay",
            f"claimed={claimed!r}; replayed={replayed!r}; tolerance={tolerance!r}",
        )


def audit_claim(claim: dict) -> dict:
    findings: list[dict] = []

    if claim.get("schema") != "economics-receipt/v0.1":
        add(findings, "ECON-002", "critical", "Unsupported economics schema", repr(claim.get("schema")))

    state = claim.get("economic_state")
    if state not in STATES:
        add(findings, "ECON-001", "critical", "Economic state is invalid", repr(state))

    accounting_class = claim.get("accounting_class")
    if accounting_class not in ACCOUNTING_CLASSES:
        add(findings, "ECON-002", "critical", "Accounting class is invalid", repr(accounting_class))

    if claim.get("authority_created") is not False:
        add(findings, "ECON-009", "critical", "Receipt attempts to create authority", "authority_created must equal false")

    sources = claim.get("sources")
    if not isinstance(sources, list):
        sources = []
        add(findings, "ECON-001", "critical", "Sources are missing", "sources must be an array")

    source_ids: set[str] = set()
    evidence_classes: set[str] = set()
    claim_period = claim.get("period")

    for source in sources:
        if not isinstance(source, dict):
            add(findings, "ECON-008", "critical", "Malformed source entry", repr(source))
            continue
        source_id = source.get("source_id")
        evidence_class = source.get("evidence_class")
        if source_id in source_ids:
            add(findings, "ECON-006", "high", "Duplicate source identifier", repr(source_id))
        if source_id:
            source_ids.add(source_id)
        if evidence_class:
            evidence_classes.add(evidence_class)
        if evidence_class in BYTE_BOUND_CLASSES:
            digest = source.get("sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                add(
                    findings,
                    "ECON-008",
                    "critical",
                    "Byte-bound evidence lacks SHA-256 identity",
                    f"source_id={source_id!r}; evidence_class={evidence_class!r}",
                )
        source_period = source.get("period")
        if source_period and claim_period and source_period != claim_period:
            add(
                findings,
                "ECON-007",
                "medium",
                "Source period conflicts with claim period",
                f"source_id={source_id!r}; source_period={source_period!r}; claim_period={claim_period!r}",
            )

    if state in REQUIRED_EVIDENCE:
        missing = sorted(REQUIRED_EVIDENCE[state] - evidence_classes)
        if missing:
            add(
                findings,
                "ECON-001",
                "critical",
                "Economic-state promotion gate is not satisfied",
                "missing evidence classes: " + ", ".join(missing),
            )

    metric = str(claim.get("metric", "")).upper()
    recurring_claim = "ARR" in metric or "RECURRING" in metric
    if recurring_claim and claim.get("recurring_basis") is not True:
        add(
            findings,
            "ECON-004",
            "critical",
            "Recurring-revenue basis is not established",
            "recurring_basis must equal true for ARR/recurring metrics",
        )

    unclassified_costs = claim.get("unclassified_direct_costs") or []
    if "GROSS_MARGIN" in metric and unclassified_costs:
        severity = "critical" if state == "VERIFIED" else "high"
        add(
            findings,
            "ECON-003",
            severity,
            "Gross-margin boundary is incomplete",
            "unclassified direct costs: " + ", ".join(map(str, unclassified_costs)),
        )

    if state == "VERIFIED" and not claim.get("calculation_digest"):
        add(
            findings,
            "ECON-005",
            "critical",
            "Verified claim lacks calculation digest",
            "calculation_digest is required at VERIFIED",
        )

    replay_calculation(claim, findings)

    clean_claim = dict(claim)
    clean_claim.pop("claim_sha256", None)
    claim_sha256 = canonical_sha256(clean_claim)

    highest = max((SEVERITY_RANK[item["severity"]] for item in findings), default=-1)
    verdict = "BLOCKED" if highest >= SEVERITY_RANK["critical"] else "REVIEW_REQUIRED" if findings else "PASS"

    receipt = {
        "schema": "economics-audit-receipt/v0.1",
        "auditor": "Jason Parallel-Drift Auditor / Economics v0.1",
        "claim_sha256": claim_sha256,
        "verdict": verdict,
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
    receipt = audit_claim(claim)
    rendered = json.dumps(receipt, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 2 if receipt["verdict"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
