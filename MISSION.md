# Mission

## Operator

Jason “Jay” Wisdom is the operator. Automated systems are evidence collectors
and proposal generators, not owners or final authorities.

## Objective

Audit GitHub repositories for mission drift, security exposure, dependency
contamination, unverifiable receipts, excessive infrastructure, and unsafe
automation. Produce bounded, reviewable corrections.

## Deliverable

Each run emits a JSON report, Markdown drift ledger, SARIF security report, and
correction plan bound to the reviewed commit.

## Success condition

The same commit and configuration produce materially equivalent classifications;
critical findings block; every correction is reviewed through ordinary Git
history; no secret value is reproduced.

## Expected cost

One bounded CI job with a ten-minute timeout and no paid external services.

## Non-goals

- Attribute malicious intent to people, vendors, or models.
- Establish legal ownership or copyright.
- Rewrite repositories automatically.
- Treat payment, branding, receipts, or infrastructure as authority.
- Upload repository contents to AI vendors.

## Stop condition

Stop and block when secret material, unsafe privileged automation, evidence
gaps, or an unapproved objective change is detected. Human approval is required
before correction or publication.
