#!/usr/bin/env python3
"""Evidence-first GitHub repository auditor.

The auditor never attributes intent and never mutates source files. It emits
machine-readable findings, a human drift ledger, SARIF, and a correction plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_CONFIG = {
    "version": "1.0",
    "mission_files": [
        "MISSION.md",
        "README.md",
        "README",
        "docs/MISSION.md",
        ".github/PROJECT_MISSION.md",
    ],
    "exclude": [
        ".git",
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".venv",
        "__pycache__",
    ],
    "infrastructure_paths": [
        ".github",
        "infra",
        "terraform",
        "deploy",
        "deployment",
        "scripts",
        "receipts",
        "governance",
        "validators",
        "conformance",
    ],
    "mission_markers": [
        "mission",
        "objective",
        "deliverable",
        "success condition",
        "operator",
        "non-goal",
        "non-goals",
        "stop condition",
        "cost",
    ],
    "ai_fingerprints": [
        "agent",
        "orchestrator",
        "autonomous",
        "constitutional",
        "governance",
        "enterprise-ready",
        "production-ready",
        "openai",
        "grok",
        "xai",
        "anthropic",
        "gemini",
        "llm",
    ],
    "vendor_lenses": {
        "Larry / Oracle": ["oracle", "oci", "java licensing"],
        "Elon / xAI / X": ["grok", "xai", "twitter api", "x api"],
        "Sam / OpenAI": ["openai", "chatgpt", "agents sdk"],
        "Mark / Meta": ["meta", "facebook", "instagram", "llama"],
    },
    "secret_patterns": {
        "private_key_block": "-----BEGIN (?:PGP |RSA |EC |OPENSSH )?PRIVATE KEY",
        "aws_access_key": "\\bAKIA[0-9A-Z]{16}\\b",
        "github_token": "\\bgh[pousr]_[A-Za-z0-9_]{20,}\\b",
        "generic_secret_assignment": "(?i)(api[_-]?key|secret|token|password)\\s*[:=]\\s*['\\\"][^'\\\"]{8,}['\\\"]",
    },
    "dangerous_extensions": [".pem", ".p12", ".pfx", ".key", ".asc"],
    "secret_scan_exclude": ["tests/fixtures/", "tests/test_audit.py"],
    "influence_scan_exclude": [
        "auditor/",
        "tests/",
        ".github/jpa-audit.json",
        "audit-output/",
    ],
    "max_text_bytes": 2_000_000,
    "thresholds": {"warn_infrastructure_ratio": 0.6, "fail_severity": "critical"},
}

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Finding:
    test_id: str
    classification: str
    severity: str
    title: str
    evidence: str
    path: str | None = None
    line: int | None = None
    correction: str | None = None


def load_config(path: Path | None) -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and path.exists():
        supplied = json.loads(path.read_text(encoding="utf-8"))
        for key, value in supplied.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def iter_files(root: Path, excluded: set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.relative_to(root).parts):
            continue
        yield path


def text_content(path: Path, limit: int) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        raw = path.read_bytes()
        if b"\x00" in raw[:4096]:
            return None
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return None


def git_value(root: Path, args: list[str], fallback: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
        ).strip() or fallback
    except (subprocess.CalledProcessError, FileNotFoundError):
        return fallback


def find_line(text: str, needle: str) -> int:
    index = text.lower().find(needle.lower())
    return text.count("\n", 0, index) + 1 if index >= 0 else 1


def term_count(text: str, term: str) -> int:
    """Count terms as tokens/phrases rather than accidental substrings."""
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(term.lower()) + r"(?![A-Za-z0-9_])"
    return len(re.findall(pattern, text.lower()))


def audit(root: Path, config: dict) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    excluded = set(config["exclude"])
    files = list(iter_files(root, excluded))
    rels = [path.relative_to(root).as_posix() for path in files]
    mission_path = next(
        (root / name for name in config["mission_files"] if (root / name).is_file()),
        None,
    )

    mission_text = text_content(mission_path, config["max_text_bytes"]) if mission_path else ""
    if not mission_path:
        findings.append(
            Finding(
                "JPA-001",
                "OBSERVED",
                "high",
                "Original mission is not recoverable",
                "No configured mission file exists.",
                correction="Add MISSION.md with operator, deliverable, success, cost, non-goals, and stop condition.",
            )
        )
    else:
        missing = [
            marker for marker in config["mission_markers"] if marker not in mission_text.lower()
        ]
        if missing:
            findings.append(
                Finding(
                    "JPA-001",
                    "OBSERVED",
                    "medium",
                    "Mission declaration is incomplete",
                    "Missing markers: " + ", ".join(missing),
                    path=mission_path.relative_to(root).as_posix(),
                    correction="Complete the mission declaration; do not infer absent operator intent.",
                )
            )

    infra_prefixes = tuple(p.rstrip("/") + "/" for p in config["infrastructure_paths"])
    infra_files = [
        rel for rel in rels if rel in config["infrastructure_paths"] or rel.startswith(infra_prefixes)
    ]
    ratio = len(infra_files) / len(files) if files else 0.0
    if ratio >= config["thresholds"]["warn_infrastructure_ratio"]:
        findings.append(
            Finding(
                "JPA-002",
                "OBSERVED",
                "medium",
                "Infrastructure dominates repository surface",
                f"{len(infra_files)} of {len(files)} files ({ratio:.1%}) are under infrastructure paths.",
                correction="Prove each infrastructure component advances the declared deliverable or retire it.",
            )
        )

    compiled_secrets = {
        name: re.compile(pattern) for name, pattern in config["secret_patterns"].items()
    }
    ai_hits: dict[str, int] = {}
    vendor_hits: dict[str, int] = {lens: 0 for lens in config["vendor_lenses"]}
    receipt_files = 0
    receipt_fact_markers = 0

    for path, rel in zip(files, rels):
        text = text_content(path, config["max_text_bytes"])
        suffix = path.suffix.lower()
        if suffix in config["dangerous_extensions"]:
            findings.append(
                Finding(
                    "SEC-001",
                    "OBSERVED",
                    "high",
                    "Sensitive file type committed",
                    f"Extension {suffix} requires manual secret classification.",
                    path=rel,
                    correction="Remove secrets from history, revoke exposed credentials, and document rotation.",
                )
            )
        if text is None:
            continue
        secret_excluded = any(
            rel == prefix or rel.startswith(prefix)
            for prefix in config["secret_scan_exclude"]
        )
        if not secret_excluded:
            for name, pattern in compiled_secrets.items():
                match = pattern.search(text)
                if match:
                    findings.append(
                        Finding(
                            "SEC-002",
                            "OBSERVED",
                            "critical",
                            "Potential secret material detected",
                            f"Pattern matched: {name}. Secret value intentionally suppressed.",
                            path=rel,
                            line=text.count("\n", 0, match.start()) + 1,
                            correction="Treat as compromised; revoke, rotate, remove from history, and investigate access.",
                        )
                    )
        influence_excluded = any(
            rel == prefix or rel.startswith(prefix)
            for prefix in config["influence_scan_exclude"]
        )
        if influence_excluded:
            continue
        lowered = text.lower()
        for term in config["ai_fingerprints"]:
            count = term_count(lowered, term)
            if count:
                ai_hits[term] = ai_hits.get(term, 0) + count
        for lens, terms in config["vendor_lenses"].items():
            vendor_hits[lens] += sum(term_count(lowered, term) for term in terms)
        if "receipt" in rel.lower():
            receipt_files += 1
            if any(token in lowered for token in ("tx_hash", "transaction_hash", "evidence", "sha256")):
                receipt_fact_markers += 1

    if ai_hits:
        findings.append(
            Finding(
                "JPA-007",
                "OBSERVED",
                "info",
                "AI fingerprints present",
                ", ".join(f"{term}:{count}" for term, count in sorted(ai_hits.items())),
                correction="Confirm prompts and agents cannot reinterpret operator objectives or mutate without approval.",
            )
        )
    for lens, count in vendor_hits.items():
        if count:
            findings.append(
                Finding(
                    "JPA-005",
                    "OBSERVED",
                    "low",
                    f"{lens} dependency or influence terms present",
                    f"{count} textual matches; this does not establish improper influence.",
                    correction="Document necessity, substitutability, cost, lock-in, and direct mission value.",
                )
            )
    if receipt_files and receipt_fact_markers < receipt_files:
        findings.append(
            Finding(
                "JPA-008",
                "INFERRED",
                "medium",
                "Some receipt files may not prove new facts",
                f"{receipt_fact_markers} of {receipt_files} receipt-named files contain common evidence markers.",
                correction="Require a new observed fact, evidence pointer, timestamp, and canonical hash.",
            )
        )

    workflow_root = root / ".github" / "workflows"
    for workflow in workflow_root.glob("*.*") if workflow_root.exists() else []:
        text = text_content(workflow, config["max_text_bytes"]) or ""
        lowered = text.lower()
        if "pull_request_target" in lowered:
            findings.append(
                Finding(
                    "SEC-003",
                    "OBSERVED",
                    "high",
                    "Privileged pull_request_target workflow",
                    "This trigger can expose write permissions or secrets to untrusted changes.",
                    path=workflow.relative_to(root).as_posix(),
                    line=find_line(text, "pull_request_target"),
                    correction="Use pull_request where possible or isolate untrusted checkout from privileged steps.",
                )
            )
        if re.search(r"permissions:\s*write-all", lowered):
            findings.append(
                Finding(
                    "SEC-004",
                    "OBSERVED",
                    "high",
                    "Workflow grants write-all",
                    "Repository-wide write permission is broader than least privilege.",
                    path=workflow.relative_to(root).as_posix(),
                    line=find_line(text, "write-all"),
                    correction="Declare the minimum job-level permissions required.",
                )
            )
        for match in re.finditer(r"uses:\s*[^@\s]+@(?!(?:[0-9a-f]{40})\b)([^\s#]+)", text):
            findings.append(
                Finding(
                    "SUPPLY-001",
                    "OBSERVED",
                    "medium",
                    "GitHub Action is not pinned to a full commit SHA",
                    f"Reference: {match.group(0).strip()}",
                    path=workflow.relative_to(root).as_posix(),
                    line=text.count("\n", 0, match.start()) + 1,
                    correction="Pin third-party actions to reviewed 40-character commit SHAs.",
                )
            )

    metrics = {
        "total_files": len(files),
        "infrastructure_files": len(infra_files),
        "infrastructure_ratio": round(ratio, 4),
        "mission_file": mission_path.relative_to(root).as_posix() if mission_path else None,
        "ai_fingerprints": ai_hits,
        "vendor_lens_hits": vendor_hits,
    }
    return findings, metrics


def render_markdown(report: dict) -> str:
    lines = [
        "# GitHub Audit Drift Ledger",
        "",
        f"- Repository: `{report['repository']}`",
        f"- Commit: `{report['commit']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Verdict: **{report['verdict']}**",
        f"- Findings: **{len(report['findings'])}**",
        "",
        "## Metrics",
        "",
        f"- Mission file: `{report['metrics']['mission_file']}`",
        f"- Mission work proxy: `{1 - report['metrics']['infrastructure_ratio']:.1%}`",
        f"- Infrastructure proxy: `{report['metrics']['infrastructure_ratio']:.1%}`",
        "",
        "## Findings",
        "",
        "| Test | Class | Severity | Finding | Evidence |",
        "|---|---|---:|---|---|",
    ]
    for item in report["findings"]:
        location = f" ({item['path']}:{item['line']})" if item.get("path") else ""
        evidence = (item["evidence"] + location).replace("|", "\\|")
        lines.append(
            f"| {item['test_id']} | {item['classification']} | {item['severity']} | "
            f"{item['title'].replace('|', '\\|')} | {evidence} |"
        )
    if not report["findings"]:
        lines.append("| — | OBSERVED | info | No configured findings | Audit completed |")
    lines += ["", "## Correction Plan", ""]
    corrections = [
        item for item in report["findings"] if item.get("correction")
    ]
    for index, item in enumerate(corrections, 1):
        lines.append(
            f"{index}. **{item['test_id']} — {item['title']}**: {item['correction']}"
        )
    if not corrections:
        lines.append("No corrections proposed.")
    lines += [
        "",
        "## Evidence Boundary",
        "",
        "This report classifies repository evidence. It does not establish intent, legal ownership,",
        "vendor culpability, or successful correction. Corrections require a reviewed commit and a new audit.",
        "",
    ]
    return "\n".join(lines)


def render_sarif(report: dict) -> dict:
    results = []
    for item in report["findings"]:
        result = {
            "ruleId": item["test_id"],
            "level": {"critical": "error", "high": "error", "medium": "warning"}.get(
                item["severity"], "note"
            ),
            "message": {"text": f"{item['title']}: {item['evidence']}"},
        }
        if item.get("path"):
            result["locations"] = [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": item["path"]},
                        "region": {"startLine": item.get("line") or 1},
                    }
                }
            ]
        results.append(result)
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Jason Parallel-Drift Auditor",
                        "informationUri": "https://github.com/jsonwisdom",
                        "rules": [],
                    }
                },
                "results": results,
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("audit-output"))
    parser.add_argument("--fail-on", choices=SEVERITY_RANK, default=None)
    args = parser.parse_args()

    root = args.root.resolve()
    config = load_config(args.config)
    findings, metrics = audit(root, config)
    repository = os.environ.get("GITHUB_REPOSITORY") or root.name
    commit = os.environ.get("GITHUB_SHA") or git_value(root, ["rev-parse", "HEAD"], "UNVERIFIED")
    generated_at = datetime.now(timezone.utc).isoformat()
    threshold = args.fail_on or config["thresholds"]["fail_severity"]
    verdict = (
        "BLOCKED"
        if any(SEVERITY_RANK[f.severity] >= SEVERITY_RANK[threshold] for f in findings)
        else "REVIEW_REQUIRED"
        if findings
        else "PASS"
    )
    report = {
        "schema": "jpa-audit-report/v1",
        "repository": repository,
        "commit": commit,
        "generated_at": generated_at,
        "verdict": verdict,
        "metrics": metrics,
        "findings": [asdict(f) for f in findings],
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / "drift-ledger.md").write_text(render_markdown(report), encoding="utf-8")
    (output / "audit.sarif").write_text(
        json.dumps(render_sarif(report), indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verdict": verdict, "report_sha256": report["report_sha256"]}))
    return 2 if verdict == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
