# JPA Portfolio Night Watch

Night Watch performs a read-only rotation across repositories owned by
`jsonwisdom`, including private repositories visible to its credential.

## Goal

Reduce the actively maintained governance surface to no more than 10
repositories. Compression is ranking and governance-surface reduction—not
deletion and not a claim that GitHub archive status reclaims storage.

## Schedule

- Hourly: light metadata and ranking delta
- Daily at 01:00 UTC: deep PR and repository evidence
- Sunday at 03:00 UTC: storage, artifact, and dependency evidence

A single hourly trigger selects the appropriate mode, avoiding duplicate runs.

## Required secret

Create the Actions secret `JPA_PORTFOLIO_TOKEN` in this repository. Use a
fine-grained token or GitHub App installation token restricted to the
`jsonwisdom` repositories and these read-only permissions:

- Metadata: read
- Pull requests: read
- Checks: read
- Actions: read

Do not grant contents, issues, pull requests, administration, or workflows
write access.

## Evidence

Each completed rotation uploads uniquely named, hash-bound ledgers:

- `rotation-<run-id>.json`
- `rotation-<run-id>.md`

The ledger ranks repositories as `KEEP_ACTIVE`, `CONSOLIDATE`,
`ARCHIVE_CANDIDATE`, or `HUMAN_DECISION`. It never emits `DELETE`.

## Notification boundary

Email delivery is intentionally outside GitHub Actions. A notification watcher
observes completed Night Watch runs and emails the authenticated operator only
when a new major rotation completes. GitHub credentials are never shared with
the email system.

## Non-authority

Night Watch never merges, closes, approves, labels, comments on, or rewrites
repositories or pull requests.
