from __future__ import annotations

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
from typing import Any

from nightwatch.scoring import Outcome, compute_score, rank_and_classify


API = "https://api.github.com"


@dataclass
class Client:
    token: str

    def get(self, path: str) -> Any:
        request = urllib.request.Request(
            API + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "jpa-night-watch",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"GitHub API {error.code}: {detail}") from error

    def paged(self, path: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        separator = "&" if "?" in path else "?"
        page = 1
        while True:
            batch = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError(f"Expected list response for {path}")
            result.extend(batch)
            if len(batch) < 100:
                return result
            page += 1


def select_mode(now: datetime, requested: str | None = None) -> str:
    if requested:
        if requested not in {"light", "deep", "weekly"}:
            raise ValueError("mode must be light, deep, or weekly")
        return requested
    if now.weekday() == 6 and now.hour == 3:
        return "weekly"
    if now.hour == 1:
        return "deep"
    return "light"


def _activity(pushed_at: str | None, now: datetime) -> float:
    if not pushed_at:
        return 0.0
    age = (now - datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))).days
    if age <= 30:
        return 1.0
    if age <= 90:
        return 0.5
    return 0.0


def collect_evidence(
    client: Client, repo: dict[str, Any], mode: str, now: datetime
) -> dict[str, Any]:
    description = (repo.get("description") or "").strip()
    stars = int(repo.get("stargazers_count", 0))
    forks = int(repo.get("forks_count", 0))
    watchers = int(repo.get("subscribers_count", repo.get("watchers_count", 0)))
    open_issues = int(repo.get("open_issues_count", 0))
    evidence: dict[str, Any] = {
        "mission_alignment": 1.0 if description else 0.0,
        "completed_deliverables": 0.0,
        "economic_strategic": 0.0,
        "reuse": min(1.0, forks / 5),
        "meaningful_activity": _activity(repo.get("pushed_at"), now),
        "low_maintenance": max(0.0, 1.0 - min(open_issues, 20) / 20),
        "external_adoption": min(1.0, (stars + forks + watchers) / 20),
        "no_recoverable_mission": not bool(description),
        "mission_value": 1.0 if description else 0.0,
        "new_evidence_value": 0.0,
        "estimated_operator_hours": float(open_issues),
        "maintenance_burden": float(open_issues),
        "reuse_value": float(forks),
        "storage_bytes": int(repo.get("size", 0)) * 1024,
        "duplicate_overlap": 0.0,
        "visibility": "private" if repo.get("private") else "public",
        "pushed_at": repo.get("pushed_at"),
        "stars": stars,
        "forks": forks,
        "open_issues": open_issues,
    }
    encoded = urllib.parse.quote(repo["full_name"], safe="/")
    if mode in {"deep", "weekly"}:
        pulls = client.paged(f"/repos/{encoded}/pulls?state=open")
        evidence["open_pr_count"] = len(pulls)
        evidence["new_evidence_value"] = float(
            sum(bool(item.get("body")) for item in pulls)
        )
        evidence["estimated_operator_hours"] += len(pulls)
        evidence["completed_deliverables"] = 0.5 if repo.get("has_releases") else 0.0
    if mode == "weekly":
        artifact_page = client.get(f"/repos/{encoded}/actions/artifacts?per_page=100")
        artifacts = (
            artifact_page.get("artifacts", [])
            if isinstance(artifact_page, dict)
            else []
        )
        evidence["artifact_count"] = len(artifacts)
        evidence["artifact_storage_bytes"] = sum(
            int(item.get("size_in_bytes", 0)) for item in artifacts
        )
    return evidence


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Night Watch Compression Ledger",
        "",
        f"- Rotation: `{report['rotation_id']}`",
        f"- Mode: `{report['mode']}`",
        f"- Generated: `{report['timestamp']}`",
        f"- Repositories: **{report['repository_count']}**",
        f"- Target active repositories: **{report['target_keep']}**",
        f"- Previous hash: `{report.get('previous_report_sha256') or 'UNAVAILABLE'}`",
        f"- Report hash: `{report['report_sha256']}`",
        "- Authority: **false**",
        "- Mutations: **0**",
    ]
    for outcome in Outcome:
        members = [r for r in report["repositories"] if r["outcome"] == outcome.value]
        lines += ["", f"## {outcome.value}", ""]
        if not members:
            lines.append("None.")
            continue
        lines += [
            "| Rank | Repository | Score | Storage | Reasons |",
            "|---:|---|---:|---:|---|",
        ]
        for item in members:
            reasons = "; ".join(item["reasons"]).replace("|", "\\|")
            lines.append(
                f"| {item['rank']} | `{item['full_name']}` | {item['score']} | "
                f"{item['economics']['storage_bytes']} | "
                f"{reasons} |"
            )
    lines += [
        "",
        "## Evidence boundary",
        "",
        "This rotation ranks evidence. It never merges, closes, approves, comments,",
        "rewrites, archives, transfers, or deletes repositories or pull requests.",
        "",
    ]
    return "\n".join(lines)


def run(client: Client, owner: str, mode: str, now: datetime) -> dict[str, Any]:
    repos = client.paged(
        "/user/repos?visibility=all&affiliation=owner&sort=full_name&direction=asc"
    )
    repos = [
        repo
        for repo in repos
        if repo.get("owner", {}).get("login", "").lower() == owner.lower()
    ]
    scores = [
        compute_score(repo, collect_evidence(client, repo, mode, now))
        for repo in repos
    ]
    ranked = rank_and_classify(scores, target_keep=10)
    entries = []
    for rank, item in enumerate(ranked, 1):
        entry = item.to_dict()
        entry.update({"rank": rank, "mode": mode, "timestamp": now.isoformat()})
        entries.append(entry)
    report = {
        "schema": "jpa-compression-ledger/v1",
        "rotation_id": os.environ.get("GITHUB_RUN_ID", f"local-{int(time.time())}"),
        "timestamp": now.isoformat(),
        "mode": mode,
        "owner": owner,
        "target_keep": 10,
        "repository_count": len(entries),
        "public_repository_count": sum(not repo.get("private") for repo in repos),
        "private_repository_count": sum(bool(repo.get("private")) for repo in repos),
        "previous_report_sha256": os.environ.get("PREVIOUS_REPORT_SHA256"),
        "authority": False,
        "mutations_performed": 0,
        "repositories": entries,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> int:
    token = os.environ.get("JPA_PORTFOLIO_TOKEN")
    if not token:
        raise SystemExit("JPA_PORTFOLIO_TOKEN is required")
    now = datetime.now(timezone.utc)
    mode = select_mode(now, os.environ.get("MODE") or None)
    report = run(Client(token), "jsonwisdom", mode, now)
    output = Path("ledgers")
    output.mkdir(exist_ok=True)
    stem = f"rotation-{report['rotation_id']}"
    (output / f"{stem}.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (output / f"{stem}.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"mode": mode, "report_sha256": report["report_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
