# JPA Portfolio Night Watch

Night Watch performs a read-only rotation across repositories owned by
`jsonwisdom`, including private repositories visible to its credential.

## Schedule

The workflow runs nightly at `11:00 UTC` and may also be started manually.

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

Each completed rotation uploads:

- `portfolio-ledger.json`
- `portfolio-ledger.md`

The JSON report contains a SHA-256 digest, the observed head SHA of every open
pull request, check totals, classification reasons, and explicit
`authority: false` / `mutations_performed: 0` fields.

## Notification boundary

Email delivery is intentionally outside GitHub Actions. A notification watcher
observes completed Night Watch runs and emails the authenticated operator only
when a new major rotation completes. GitHub credentials are never shared with
the email system.

## Non-authority

Night Watch never merges, closes, approves, labels, comments on, or rewrites
repositories or pull requests.
