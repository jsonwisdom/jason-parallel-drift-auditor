# Jason Parallel-Drift Auditor

A fail-closed GitHub auditing and correction-proposal workflow for repositories
operated by Jason Wisdom.

It answers:

1. What exact mission was declared?
2. Did infrastructure displace the deliverable?
3. Did an agent, vendor, dependency, workflow, or personality lens substitute a
   different objective?
4. What did the work cost?
5. What new evidence exists?
6. What forces the system to stop?

## Outputs

- `audit-report.json` — canonical machine-readable result
- `drift-ledger.md` — human review surface
- `audit.sarif` — GitHub code-scanning findings
- correction plan embedded in the ledger

The report is bound to the reviewed commit and includes a SHA-256 digest. Secret
values are never copied into evidence.

## Install in a repository

Copy these paths into the target repository:

```text
auditor/
tests/
schemas/
.github/jpa-audit.json
.github/workflows/jpa-audit.yml
MISSION.md
```

Complete `MISSION.md` before enabling corrections. Customize
`.github/jpa-audit.json` for repository-specific exclusions and thresholds.

## Run locally

```bash
python3 -m unittest discover -s tests -v
python3 auditor/audit.py \
  --root . \
  --config .github/jpa-audit.json \
  --output audit-output
```

## Decision model

| Verdict | Meaning |
|---|---|
| `PASS` | No configured finding was observed |
| `REVIEW_REQUIRED` | Findings exist below the blocking threshold |
| `BLOCKED` | A finding meets or exceeds the blocking threshold |

The workflow never silently edits source. “Correcting” means:

```text
observe → classify → propose → human review → commit → replay audit
```

That separation prevents the auditor from becoming the unauthorized operator it
was designed to detect.

## Initial controls

- JPA-001 original mission preservation
- JPA-002 deliverable-to-infrastructure ratio
- JPA-005 vendor-influence lens
- JPA-007 AI fingerprints
- JPA-008 receipts without common evidence markers
- SEC-001 sensitive file extensions
- SEC-002 secret-pattern detection with value suppression
- SEC-003 privileged `pull_request_target` workflows
- SEC-004 overbroad `write-all`
- SUPPLY-001 unpinned GitHub Actions

## Economics extension v0.1

Economic claims can be audited separately with:

```bash
python3 auditor/economics_audit.py \
  examples/economics-modeled-contribution.v0.1.json
```

The extension enforces independent `ECONOMIC_STATE` and `ACCOUNTING_CLASS`
labels, promotion gates, deterministic calculation replay, recurring-revenue
basis checks, SHA-256 identity for byte-bound commercial evidence, and
`authority_created=false`.

See `economics/ECONOMICS_AUDITOR_MECHANICS_v0.1.md` and
`schemas/economics-receipt.schema.json`.

## Deliberate boundary

Text hits establish presence, not motive. Vendor names are influence lenses, not
culpability findings. A receipt proves only the evidence it binds. This tool
does not determine copyright, legal ownership, or authorization outside the
repository record. The economics extension does not constitute a CPA audit,
GAAP opinion, tax determination, bank confirmation, or proof of an underlying
commercial event outside its bound evidence.
