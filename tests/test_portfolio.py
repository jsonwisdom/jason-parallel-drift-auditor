import unittest
from datetime import datetime, timezone

from nightwatch.main import collect_evidence, select_mode
from nightwatch.scoring import Outcome, compute_score, rank_and_classify


class FakeClient:
    def __init__(self):
        self.paged_calls = []

    def paged(self, path):
        self.paged_calls.append(path)
        return []


def evidence(**changes):
    base = {
        "mission_alignment": 0,
        "completed_deliverables": 0,
        "economic_strategic": 0,
        "reuse": 0,
        "meaningful_activity": 0,
        "low_maintenance": 0,
        "external_adoption": 0,
    }
    base.update(changes)
    return base


class CompressionTests(unittest.TestCase):
    def test_scoring_weights_and_penalties(self):
        score = compute_score(
            {"full_name": "jsonwisdom/x"},
            evidence(
                mission_alignment=1,
                completed_deliverables=0.5,
                economic_strategic=1,
                reuse=1,
                meaningful_activity=1,
                low_maintenance=1,
                external_adoption=1,
                mission_drift=True,
            ),
        )
        self.assertEqual(score.score, 70)

    def test_never_emits_delete(self):
        ranked = rank_and_classify(
            [compute_score({"full_name": "x/y"}, evidence(no_recoverable_mission=True))]
        )
        self.assertNotEqual(ranked[0].outcome.value, "DELETE")

    def test_top_n_become_keep_active(self):
        scores = [
            compute_score({"full_name": f"x/{i}"}, evidence(mission_alignment=1))
            for i in range(12)
        ]
        ranked = rank_and_classify(scores, 10)
        self.assertEqual(sum(s.outcome == Outcome.KEEP_ACTIVE for s in ranked), 10)

    def test_consolidate_vs_archive_boundaries(self):
        consolidate = compute_score(
            {"full_name": "x/c"},
            evidence(mission_alignment=0.5, reuse_value=1),
        )
        archive = compute_score(
            {"full_name": "x/a"}, evidence(no_recoverable_mission=True)
        )
        ranked = rank_and_classify([consolidate, archive], target_keep=0)
        self.assertEqual(ranked[0].outcome, Outcome.CONSOLIDATE)
        self.assertEqual(ranked[1].outcome, Outcome.ARCHIVE_CANDIDATE)

    def test_hourly_vs_deep_mode_separation(self):
        client = FakeClient()
        repo = {
            "full_name": "jsonwisdom/x",
            "description": "mission",
            "pushed_at": "2026-07-27T00:00:00Z",
            "private": False,
        }
        collect_evidence(
            client, repo, "light", datetime(2026, 7, 27, tzinfo=timezone.utc)
        )
        self.assertEqual(client.paged_calls, [])
        collect_evidence(
            client, repo, "deep", datetime(2026, 7, 27, tzinfo=timezone.utc)
        )
        self.assertTrue(any("/pulls?" in path for path in client.paged_calls))

    def test_mode_schedule(self):
        self.assertEqual(
            select_mode(datetime(2026, 8, 2, 3, tzinfo=timezone.utc)), "weekly"
        )
        self.assertEqual(
            select_mode(datetime(2026, 8, 3, 1, tzinfo=timezone.utc)), "deep"
        )
        self.assertEqual(
            select_mode(datetime(2026, 8, 3, 2, tzinfo=timezone.utc)), "light"
        )


if __name__ == "__main__":
    unittest.main()
