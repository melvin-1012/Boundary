import unittest

import pandas as pd

from analytics.cricket_metrics import (
    apply_pressure_model,
    calculate_player_metrics,
    rank_players,
    reconstruct_match_state,
)


def match_fixture():
    matches = pd.DataFrame(
        [
            {
                "match_id": 1,
                "comp_id": 1358,
                "match_date": "2022-04-01",
                "first_inn_revised_overs": 1,
                "second_inn_revised_overs": 1,
                "revised_target": None,
            }
        ]
    )
    competitions = pd.DataFrame(
        [
            {
                "comp_id": 1358,
                "comp_name": "IPL 2022",
                "match_format": "T20",
                "season": "2022",
            }
        ]
    )
    rows = []
    events = [
        (1, 0, 0, None, False, None),
        (0, 1, 0, "wide", False, None),
        (2, 1, 0, "Overstep", False, None),
        (0, 2, 0, "byes", False, None),
        (0, 0, 0, None, True, "Bowled"),
        (0, 0, 0, None, True, "RunOut"),
    ]
    for innings in (1, 2, 3, 4):
        for ball, (runs, extra1, extra2, extras, wicket, dismissal) in enumerate(
            events, start=1
        ):
            rows.append(
                {
                    "match_id": 1,
                    "innings": innings,
                    "overid": 0,
                    "over_ball_num": ball,
                    "innings_ball_num": ball,
                    "batting_team_id": 10 + innings,
                    "bowling_team_id": 20 + innings,
                    "striker_id": 100 + innings,
                    "striker_name": f"Batter {innings}",
                    "non_striker_id": 300 + innings,
                    "non_striker_name": f"Partner {innings}",
                    "bowler_id": 200 + innings,
                    "bowler_name": f"Bowler {innings}",
                    "runs": runs,
                    "is_four": False,
                    "is_six": False,
                    "is_wicket": wicket,
                    "dismissal_type": dismissal,
                    "dismissed_player_id": (
                        300 + innings if dismissal == "RunOut" else 100 + innings
                    ) if wicket else None,
                    "extras_type": extras,
                    "extras1_runs": extra1,
                    "extras_2_runs": extra2,
                }
            )
    return pd.DataFrame(rows), matches, competitions


class CricketAnalyticsTests(unittest.TestCase):
    def test_match_state_uses_pre_delivery_values_and_reconstructed_target(self):
        balls, matches, competitions = match_fixture()

        state = reconstruct_match_state(balls, matches, competitions)
        first_innings = state[state["innings"].eq(1)].reset_index(drop=True)
        chase = state[state["innings"].eq(2)].reset_index(drop=True)

        self.assertEqual(first_innings.loc[1, "legal_balls_before"], 1)
        self.assertEqual(first_innings.loc[3, "score_before"], 5)
        self.assertEqual(first_innings.loc[3, "legal_balls_before"], 1)
        self.assertEqual(first_innings.loc[5, "wickets_before"], 1)
        self.assertEqual(int(chase.loc[0, "target"]), 8)
        self.assertEqual(int(chase.loc[0, "runs_required"]), 8)
        super_over_chase = state[
            state["innings"].eq(4)
        ].sort_values("innings_ball_num")
        self.assertEqual(int(super_over_chase.iloc[0]["target"]), 8)
        self.assertEqual(float(super_over_chase.iloc[0]["innings_overs"]), 1.0)
        self.assertEqual(int(super_over_chase.iloc[0]["runs_required"]), 8)
        self.assertEqual(float(super_over_chase.iloc[0]["required_run_rate"]), 8.0)
        self.assertTrue(state["batting_pressure"].between(0, 100).all())
        self.assertTrue(state["bowling_pressure"].between(0, 100).all())

    def test_extras_and_bowler_dismissal_credit_are_explicit(self):
        balls, matches, competitions = match_fixture()

        state = reconstruct_match_state(balls, matches, competitions)
        first = state[state["innings"].eq(1)].reset_index(drop=True)

        self.assertFalse(bool(first.loc[1, "is_legal_ball"]))
        self.assertFalse(bool(first.loc[2, "is_legal_ball"]))
        self.assertTrue(bool(first.loc[3, "is_legal_ball"]))
        self.assertEqual(first.loc[3, "bowler_conceded_runs"], 0)
        self.assertTrue(bool(first.loc[4, "is_bowler_wicket"]))
        self.assertFalse(bool(first.loc[5, "is_bowler_wicket"]))
        self.assertTrue(bool(first.loc[2, "is_batter_ball_faced"]))
        self.assertEqual(int(first["is_batter_ball_faced"].sum()), 5)
        self.assertEqual(int(first["is_legal_ball"].sum()), 4)
        self.assertEqual(int(first["batter_runs"].sum()), 3)
        self.assertEqual(int(first["team_runs"].sum()), 7)
        self.assertEqual(int(first["bowler_conceded_runs"].sum()), 5)
        self.assertEqual(int(first["is_bowler_wicket"].sum()), 1)

        metrics = calculate_player_metrics(state)
        batter = metrics["batters"].loc[metrics["batters"]["striker_id"].eq(101)].iloc[0]
        self.assertEqual(int(batter["outs"]), 1)

    def test_pressure_labels_follow_component_scores_and_supported_innings(self):
        state = pd.DataFrame(
            {
                "innings": [1, 2, 5],
                "target": [None, 100, None],
                "is_batter_ball_faced": [True, True, True],
                "is_legal_ball": [True, True, True],
                **{
                    f"{role}_{component}_component": [0.5, 0.4, 0.5]
                    for role in ("batting", "bowling")
                    for component in ("run_rate", "wickets", "time", "closeness")
                },
            }
        )

        labeled = apply_pressure_model(state)

        self.assertEqual(labeled["batting_pressure"].iloc[0], 50.0)
        self.assertEqual(labeled["bowling_pressure"].iloc[0], 50.0)
        self.assertTrue(bool(labeled["is_batting_pressure"].iloc[0]))
        self.assertFalse(bool(labeled["is_batting_pressure"].iloc[1]))
        self.assertTrue(pd.isna(labeled["batting_pressure"].iloc[2]))
        self.assertFalse(bool(labeled["is_batting_pressure"].iloc[2]))
        self.assertEqual(int(labeled["pressure_batter_ball"].sum()), 1)

    def test_player_metrics_and_ranking_are_deterministic(self):
        balls, matches, competitions = match_fixture()
        state = reconstruct_match_state(balls, matches, competitions)
        state["is_batting_pressure"] = True
        state["is_bowling_pressure"] = True
        state["pressure_batter_ball"] = state["is_batter_ball_faced"]
        state["pressure_bowler_ball"] = state["is_legal_ball"]
        metrics = calculate_player_metrics(state)

        self.assertEqual(metrics["batters"].loc[0, "balls_faced"], 5)
        self.assertEqual(metrics["bowlers"].loc[0, "legal_balls"], 4)
        ranked = rank_players(
            {
                "batters": pd.DataFrame(
                    [
                        {
                            "striker_id": 1,
                            "striker_name": "A",
                            "matches": 4,
                            "pressure_matches": 4,
                            "pressure_opportunities": 24,
                            "pressure_strike_rate": 140,
                            "normal_strike_rate": 120,
                            "competition_adjusted_difference": 20,
                            "consistency": 80,
                        },
                        {
                            "striker_id": 2,
                            "striker_name": "B",
                            "matches": 4,
                            "pressure_matches": 4,
                            "pressure_opportunities": 24,
                            "pressure_strike_rate": 120,
                            "normal_strike_rate": 125,
                            "competition_adjusted_difference": -5,
                            "consistency": 90,
                        },
                    ]
                )
            },
            "batter",
        )
        self.assertEqual(ranked["player_id"].tolist(), [1, 2])
        self.assertEqual(ranked["rank"].tolist(), [1, 2])

    def test_invalid_spi_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            rank_players({"batters": pd.DataFrame()}, "batter", weights=(0.5, 0.3, 0.3))


if __name__ == "__main__":
    unittest.main()
