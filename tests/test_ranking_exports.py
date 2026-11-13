import json
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


class RankingExportTests(unittest.TestCase):
    def test_top_ten_exports_match_full_rankings_and_manifest(self):
        manifest = json.loads((REPORTS / "final_rankings.json").read_text())
        for role, top_name, full_name in [
            ("batter", "top_10_batters.csv", "full_batter_ranking.csv"),
            ("bowler", "top_10_bowlers.csv", "full_bowler_ranking.csv"),
        ]:
            top = pd.read_csv(REPORTS / top_name)
            full = pd.read_csv(REPORTS / full_name)
            self.assertEqual(len(top), 10)
            self.assertEqual(top["rank"].tolist(), list(range(1, 11)))
            self.assertTrue(top["player_id"].is_unique)
            self.assertEqual(
                top["player_id"].tolist(),
                full.head(10)["player_id"].tolist(),
            )
            self.assertEqual(
                manifest["ranking_validation"][role]["selected_players"], 10
            )
            self.assertTrue(top["evidence_summary"].notna().all())
            self.assertTrue(top["competition_scope"].notna().all())

    def test_top_ranked_examples_reconcile_to_delivery_rows(self):
        batter = pd.read_csv(REPORTS / "top_10_batters.csv").iloc[0]
        batter_events = pd.read_parquet(
            ROOT / "data" / "curated" / "pressure_deliveries.parquet",
            columns=[
                "striker_id",
                "is_batting_pressure",
                "batter_runs",
                "pressure_batter_ball",
            ],
        )
        batter_events = batter_events[
            batter_events["striker_id"].eq(batter["player_id"])
            & batter_events["is_batting_pressure"]
        ]
        batter_rate = (
            100 * batter_events["batter_runs"].sum()
            / batter_events["pressure_batter_ball"].sum()
        )
        self.assertAlmostEqual(batter_rate, batter["pressure_strike_rate"], places=8)

        bowler = pd.read_csv(REPORTS / "top_10_bowlers.csv").iloc[0]
        bowler_events = pd.read_parquet(
            ROOT / "data" / "curated" / "pressure_deliveries.parquet",
            columns=[
                "bowler_id",
                "is_bowling_pressure",
                "bowler_conceded_runs",
                "pressure_bowler_ball",
            ],
        )
        bowler_events = bowler_events[
            bowler_events["bowler_id"].eq(bowler["player_id"])
            & bowler_events["is_bowling_pressure"]
        ]
        bowler_economy = (
            6 * bowler_events["bowler_conceded_runs"].sum()
            / bowler_events["pressure_bowler_ball"].sum()
        )
        self.assertAlmostEqual(
            bowler_economy, bowler["pressure_economy"], places=8
        )


if __name__ == "__main__":
    unittest.main()
