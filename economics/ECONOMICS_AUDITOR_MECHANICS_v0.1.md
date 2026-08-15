# Economics Auditor Mechanics v0.1

Status: CANDIDATE / HUMAN REVIEW REQUIRED  
Operator: Jay Wisdom / jaywisdom.eth  
Authority created: false

## Purpose

Extend the Jason Parallel-Drift Auditor so economic claims can be inspected as stateful evidence objects rather than trusted spreadsheet cells.

Core rule:

> Never promote an economic claim beyond the evidence supporting it.

A financial number is treated as a claim with two independent dimensions:

```text
ECONOMIC_STATE
├─ MODELED
├─ PIPELINE
├─ CONTRACTED
├─ INVOICED
├─ COLLECTED
└─ VERIFIED

ACCOUNTING_CLASS
├─ REVENUE
├─ COGS
├─ OPERATING_EXPENSE
├─ CAPITAL_EXPENDITURE
└─ UNCLASSIFIED
```

`STATE != ACCOUNTING_CLASS != CLAIM != AUTHORITY`

## Audit pipeline

```text
observe
  ↓
bind source references
  ↓
classify economic state
  ↓
classify accounting class
  ↓
recalculate metric when deterministic operands exist
  ↓
check promotion gates
  ↓
quarantine unresolved classifications
  ↓
emit findings + canonical audit receipt
  ↓
human review
```

The auditor does not change source accounting records, contracts, invoices, payment records, or repository files under review.

## Promotion gates

No state is inherited merely because a later-looking artifact exists.

| Claimed state | Minimum evidence class |
|---|---|
| MODELED | MODELED_ASSUMPTION |
| PIPELINE | PIPELINE_RECORD |
| CONTRACTED | SIGNED_CONTRACT |
| INVOICED | SIGNED_CONTRACT + INVOICE |
| COLLECTED | SIGNED_CONTRACT + INVOICE + PAYMENT_RECEIPT |
| VERIFIED | all COLLECTED evidence + REPLAY_RECEIPT |

These gates are intentionally strict in v0.1. A later version may separate verification status from commercial lifecycle state, but v0.1 does not silently reinterpret the declared ladder.

## Accounting gate

`UNCLASSIFIED` is a quarantine state, not an error by itself.

An economic claim may remain MODELED while direct costs are unclassified. It may not be promoted to a verified gross-margin claim while material delivery-linked costs remain unresolved.

Current unresolved direct-cost classes include:

- human verification labor
- customer-specific processing
- implementation labor
- delivery-linked support
- storage
- compute
- third-party APIs

Until that boundary is frozen:

```text
77.8% = MODELED_INFRASTRUCTURE_CONTRIBUTION_MARGIN
77.8% != VERIFIED_GROSS_MARGIN
```

## Initial controls

- `ECON-001` — economic-state promotion without required evidence
- `ECON-002` — accounting class absent or outside the allowed vocabulary
- `ECON-003` — gross-margin claim while direct-cost boundary remains unresolved
- `ECON-004` — recurring-revenue claim without recurring-basis evidence
- `ECON-005` — deterministic calculation does not replay to the claimed value
- `ECON-006` — duplicate source identifiers in one claim
- `ECON-007` — source period conflicts with the claim period
- `ECON-008` — evidence requiring byte identity lacks a SHA-256 digest
- `ECON-009` — receipt attempts to create authority

## Current economic checkpoint

```text
MODELED_REVENUE                     = 688560 USD
MODELED_INFRASTRUCTURE_COST         = 153000 USD
MODELED_INFRASTRUCTURE_CONTRIBUTION = 535560 USD
MODELED_INFRASTRUCTURE_MARGIN       = 0.778 (77.8%)

CONTRACTED_REVENUE                  = 0 USD
INVOICED_REVENUE                    = 0 USD
COLLECTED_REVENUE                   = 0 USD
VERIFIED_RECURRING_REVENUE          = 0 USD
```

The checkpoint is a declared model, not traction.

## Auditor mechanics

The executable auditor accepts one JSON economic claim and emits:

```text
verdict
findings[]
claim_sha256
receipt_sha256
```

Verdicts:

- `PASS` — configured gates are satisfied for the declared state.
- `REVIEW_REQUIRED` — the claim is bounded but unresolved classification remains.
- `BLOCKED` — the claim attempts an inadmissible promotion, cannot replay, lacks required evidence, or attempts to create authority.

## Receipt boundary

A successful audit proves only that the supplied claim passed the configured v0.1 mechanics. It does not constitute a CPA audit, GAAP opinion, legal conclusion, investment recommendation, bank confirmation, tax determination, or proof that an underlying business event occurred outside the bound evidence.

`authority_created = false`
