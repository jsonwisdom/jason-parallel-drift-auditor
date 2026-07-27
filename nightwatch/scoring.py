from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    KEEP_ACTIVE = "KEEP_ACTIVE"
    CONSOLIDATE = "CONSOLIDATE"
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"
    HUMAN_DECISION = "HUMAN_DECISION"


@dataclass
class Economics:
    mission_value: float = 0.0
    new_evidence_value: float = 0.0
    estimated_operator_hours: float = 0.0
    maintenance_burden: float = 0.0
    reuse_value: float = 0.0
    storage_bytes: int = 0
    duplicate_overlap: float = 0.0
    roi_score: float = 0.0


@dataclass
class RepoScore:
    full_name: str
    score: float = 0.0
    outcome: Outcome = Outcome.HUMAN_DECISION
    economics: Economics = field(default_factory=Economics)
    reasons: list[str] = field(default_factory=list)
    penalties_applied: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["outcome"] = self.outcome.value
        return result


WEIGHTS = {
    "mission_alignment": 30,
    "completed_deliverables": 20,
    "economic_strategic": 15,
    "reuse": 10,
    "meaningful_activity": 10,
    "low_maintenance": 10,
    "external_adoption": 5,
}

PENALTIES = {
    "mission_drift": -20,
    "duplicate_purpose": -15,
    "critical_security": -30,
    "infra_no_deliverable": -15,
    "no_recoverable_mission": -20,
}


def _factor(evidence: dict[str, Any], key: str) -> float:
    value = float(evidence.get(key, 0.0))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{key} must be normalized between 0 and 1")
    return value


def compute_score(repo: dict[str, Any], evidence: dict[str, Any]) -> RepoScore:
    score = RepoScore(full_name=repo["full_name"], evidence=dict(evidence))
    total = sum(_factor(evidence, key) * weight for key, weight in WEIGHTS.items())
    for key, value in PENALTIES.items():
        if evidence.get(key, False):
            total += value
            score.penalties_applied.append(key)
    score.score = round(total, 2)
    score.economics = Economics(
        mission_value=float(evidence.get("mission_value", 0.0)),
        new_evidence_value=float(evidence.get("new_evidence_value", 0.0)),
        estimated_operator_hours=float(evidence.get("estimated_operator_hours", 0.0)),
        maintenance_burden=float(evidence.get("maintenance_burden", 0.0)),
        reuse_value=float(evidence.get("reuse_value", 0.0)),
        storage_bytes=int(evidence.get("storage_bytes", 0)),
        duplicate_overlap=float(evidence.get("duplicate_overlap", 0.0)),
        roi_score=round(total, 2),
    )
    return score


def rank_and_classify(scores: list[RepoScore], target_keep: int = 10) -> list[RepoScore]:
    ranked = sorted(scores, key=lambda item: (-item.score, item.full_name.lower()))
    for index, score in enumerate(ranked):
        if index < target_keep and score.score > 0:
            score.outcome = Outcome.KEEP_ACTIVE
            score.reasons.append(
                f"Rank {index + 1} of {len(ranked)}; score {score.score}"
            )
        elif score.score >= 15 and (
            score.economics.reuse_value > 0 or score.economics.mission_value > 0
        ):
            score.outcome = Outcome.CONSOLIDATE
            score.reasons.append(
                "Positive mission or reuse value; material should move into a keeper"
            )
        elif score.score < 5 or "no_recoverable_mission" in score.penalties_applied:
            score.outcome = Outcome.ARCHIVE_CANDIDATE
            score.reasons.append(
                "Low score or no recoverable mission; preserve read-only"
            )
        else:
            score.outcome = Outcome.HUMAN_DECISION
            score.reasons.append("Evidence insufficient or conflicting")
    return ranked
