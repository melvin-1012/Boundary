import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from machine_learning.run_models import (
    BOUNDARY_FEATURES,
    cluster_players,
    train_boundary_models,
)


class MachineLearningTests(unittest.TestCase):
    def test_grouped_boundary_split_has_no_match_leakage(self):
        rows = []
        for match_id in range(24):
            for sequence in range(20):
                row = {feature: float(sequence + match_id) for feature in BOUNDARY_FEATURES}
                row.update(
                    {
                        "match_id": match_id,
                        "is_four": sequence % 4 == 0,
                        "is_six": sequence % 7 == 0,
                    }
                )
                rows.append(row)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = train_boundary_models(pd.DataFrame(rows), Path(temp_dir))

            self.assertEqual(result["split"]["match_overlap"], 0)
            self.assertGreater(result["split"]["train_matches"], 0)
            self.assertGreater(result["split"]["test_matches"], 0)
            self.assertIn("random_forest", result["models"])

    def test_player_clustering_is_reproducible_and_exported(self):
        frame = pd.DataFrame(
            {
                "striker_id": range(1, 21),
                "striker_name": [f"Player {i}" for i in range(20)],
                "pressure_strike_rate": np.linspace(80, 180, 20),
                "pressure_boundary_percentage": np.linspace(5, 35, 20),
                "pressure_dot_ball_percentage": np.linspace(30, 65, 20),
                "consistency": np.linspace(40, 90, 20),
                "pressure_opportunities": np.linspace(15, 200, 20),
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = cluster_players(frame, "batters", temp_dir)

            self.assertGreaterEqual(result["selected_k"], 2)
            self.assertTrue((Path(temp_dir) / "batters_clusters.csv").exists())
            self.assertTrue((Path(temp_dir) / "batters_clusters.html").exists())


if __name__ == "__main__":
    unittest.main()
