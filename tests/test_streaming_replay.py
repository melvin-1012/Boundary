import unittest

from analytics.cricket_metrics import PRESSURE_WEIGHTS
from streaming.replay import replay_events


def event(sequence, score, legal_balls, runs, extras_type=None):
    row = {
        "match_id": 1,
        "innings": 1,
        "innings_ball_num": sequence,
        "runs": runs,
        "extras1_runs": 1 if extras_type == "wide" else 0,
        "extras_2_runs": 0,
        "extras_type": extras_type,
        "is_legal_ball": extras_type != "wide",
        "is_wicket": False,
        "score_before": score,
        "wickets_before": 0,
        "legal_balls_before": legal_balls,
        "target": None,
        "batting_pressure": 50.0,
        "bowling_pressure": 50.0,
        "is_batting_pressure": True,
        "is_bowling_pressure": True,
    }
    for role, components in PRESSURE_WEIGHTS.items():
        for component in components:
            row[f"{role}_{component}_component"] = 0.5
    return row


class StreamingReplayTests(unittest.TestCase):
    def test_replay_reconstructs_state_and_pressure(self):
        events = [
            event(1, score=0, legal_balls=0, runs=1, extras_type="wide"),
            event(2, score=2, legal_balls=0, runs=1),
        ]

        result = replay_events(events)

        self.assertTrue(result["validated"])
        self.assertEqual(result["delivery_count"], 2)
        self.assertEqual(result["ordering_errors"], 0)
        self.assertEqual(result["state_mismatches"], 0)
        self.assertEqual(result["pressure_mismatches"], 0)

    def test_replay_reports_out_of_order_events(self):
        events = [
            event(2, score=0, legal_balls=0, runs=1),
            event(1, score=1, legal_balls=1, runs=0),
        ]

        result = replay_events(events)

        self.assertFalse(result["validated"])
        self.assertEqual(result["ordering_errors"], 1)


if __name__ == "__main__":
    unittest.main()
