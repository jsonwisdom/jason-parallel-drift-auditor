#!/usr/bin/env python3
"""Read-only portfolio PR rotation for the JPA accountability plane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


@dataclass
class Client:
    token: str

    def get(self, path: str) -> tuple[object, dict]:
        request = urllib.request.Request(
            API + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "jason-parallel-drift-auditor",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response), dict(response.headers)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")[:500]
            raise GitHubError(f"GitHub API {error.code} for {path}: {body}") from error

    def paged(self, path: str) -> list[dict]:
        items: list[dict] = []
        separator = "&" if "?" in path else "?"
        page = 1
        while True:
            data, _ = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(data, list):
                raise GitHubError(f"Expected list response for {path}")
            items.extend(data)
            if len(data) < 100:
                return items
            page += 1


def classify(pr: dict, checks: dict, stale_days: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    age_days = pr["age_days"]
    title = pr["title"].lower()
    body = (pr.get("body") or "").lower()

    if pr.get("mergeable") is False:
        reasons.append("merge conflict observed")
        return "BLOCKED", reasons
    if checks["failed"]:
        reasons.append(f"{checks['failed']} check run(s) failed")
        return "BLOCKED", reasons
    if any(term in title for term in ("intentional", "fire drill", "negative control")):
        reasons.append("title declares adversarial or negative-control intent")
        return "EXPECTED_FAILURE", reasons
    if age_days >= stale_days:
        reasons.append(f"no update for {age_days} days")
        return "STALE", reasons
    if not body.strip():
        reasons.append("pull request body is empty")
        return "MISSION_UNCLEAR", reasons
    if any(term in body for term in ("governance", "framework", "scaffold", "infrastructure")):
        reasons.append("infrastructure/governance language requires mission review")
        return "DRIFT_SUSPECT", reasons
    if pr.get("draft"):
        reasons.append("draft pull request")
        return "READY_FOR_HUMAN_REVIEW", reasons
    if checks["pending"]:
        reasons.append(f"{checks['pending']} check run(s) pending")
        return "BLOCKED", reasons
    reasons.append("no blocking condition observed; human review still required")
    return "READY_FOR_HUMAN_REVIEW", reasons


def check_summary(client: Client, repo: str, sha: str) -> dict:
    encoded = urllib.parse.quote(repo, safe="/")
    data, _ = client.get(f"/repos/{encoded}/commits/{sha}/check-runs?per_page=100")
    runs = data.get("check_runs", []) if isinstance(data, dict) else []
    failed = sum(
        run.get("conclusion") in {"failure", "cancelled", "timed_out", "action_required"}
        for run in runs
    )
    pending = sum(run.get("status") != "completed" for run in runs)
    return {"total": len(runs), "failed": failed, "pending": pending}


def rotation(client: Client, owner: str, stale_days: int) -> dict:
    repos = client.paged(
        "/user/repos?visibility=all&affiliation=owner&sort=full_name&direction=asc"
    )
    selected = [
        repo
        for repo in repos
        if repo.get("owner", {}).get("login", "").lower() == owner.lower()
    ]
    now = datetime.now(timezone.utc)
    records: list[dict] = []

    for repo in selected:
        full_name = repo["full_name"]
        pulls = client.paged(
            f"/repos/{urllib.parse.quote(full_name, safe='/')}/pulls?state=open&sort=updated&direction=desc"
        )
        for item in pulls:
            detail, _ = client.get(
                f"/repos/{urllib.parse.quote(full_name, safe='/')}/pulls/{item['number']}"
            )
            if not isinstance(detail, dict):
                raise GitHubError(
                    f"Expected pull-request detail for {full_name}#{item['number']}"
                )
            updated = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
            checks = check_summary(client, full_name, item["head"]["sha"])
            record = {
                "repository": full_name,
                "private": bool(repo.get("private")),
                "number": item["number"],
                "url": item["html_url"],
                "title": item["title"],
                "body": item.get("body"),
                "draft": bool(item.get("draft")),
                "head_sha": item["head"]["sha"],
                "base": item["base"]["ref"],
                "updated_at": item["updated_at"],
                "age_days": (now - updated).days,
                "mergeable": detail.get("mergeable"),
                "checks": checks,
            }
            record["classification"], record["reasons"] = classify(
                record, checks, stale_days
            )
            records.append(record)

    counts: dict[str, int] = {}
    for item in records:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
    report = {
        "schema": "jpa-portfolio-ledger/v1",
        "rotation_id": os.environ.get("GITHUB_RUN_ID", f"local-{int(time.time())}"),
        "generated_at": now.isoformat(),
        "owner": owner,
        "repository_count": len(selected),
        "private_repository_count": sum(bool(repo.get("private")) for repo in selected),
        "open_pr_count": len(records),
        "classification_counts": counts,
        "authority": False,
        "mutations_performed": 0,
        "pull_requests": records,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def markdown(report: dict) -> str:
    lines = [
        "# JPA Portfolio Night Watch",
        "",
        f"- Rotation: `{report['rotation_id']}`",
        f"- Generated: `{report['generated_at']}`",
        f"- Repositories: **{report['repository_count']}** "
        f"({report['private_repository_count']} private)",
        f"- Open pull requests: **{report['open_pr_count']}**",
        f"- Report SHA-256: `{report['report_sha256']}`",
        "- Authority: **false**",
        "- Mutations performed: **0**",
        "",
        "## Classification totals",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for name, count in sorted(report["classification_counts"].items()):
        lines.append(f"| {name} | {count} |")
    lines += [
        "",
        "## Pull requests",
        "",
        "| Repository | PR | Classification | Age | Checks | Reason |",
        "|---|---:|---|---:|---|---|",
    ]
    for item in report["pull_requests"]:
        checks = item["checks"]
        reason = "; ".join(item["reasons"]).replace("|", "\\|")
        lines.append(
            f"| `{item['repository']}` | [#{item['number']}]({item['url']}) | "
            f"{item['classification']} | {item['age_days']}d | "
            f"{checks['failed']} failed / {checks['pending']} pending | {reason} |"
        )
    lines += [
        "",
        "## Evidence boundary",
        "",
        "This rotation observed GitHub metadata and check runs. It did not merge, close,",
        "approve, comment on, or rewrite any pull request or repository.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default="jsonwisdom")
    parser.add_argument("--output", type=Path, default=Path("portfolio-output"))
    parser.add_argument("--stale-days", type=int, default=30)
    args = parser.parse_args()
    token = os.environ.get("JPA_PORTFOLIO_TOKEN")
    if not token:
        raise SystemExit("JPA_PORTFOLIO_TOKEN is required for public/private rotation")
    report = rotation(Client(token), args.owner, args.stale_days)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "portfolio-ledger.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "portfolio-ledger.md").write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {"rotation_id": report["rotation_id"], "sha256": report["report_sha256"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
