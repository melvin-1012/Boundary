import unittest

import pandas as pd

from graph_analytics.run_graph import build_player_match_graph


class GraphAnalyticsTests(unittest.TestCase):
    def test_graph_uses_only_observed_player_match_relationships(self):
        deliveries = pd.DataFrame(
            {
                "match_id": [1, 1, 2],
                "striker_id": [10, 10, 11],
                "striker_name": ["A", "A", "B"],
                "bowler_id": [20, 20, 21],
                "bowler_name": ["X", "X", "Y"],
                "pressure_batter_ball": [True, False, True],
                "pressure_bowler_ball": [False, True, True],
            }
        )

        graph = build_player_match_graph(deliveries)

        self.assertEqual(graph.nodes["player:10"]["node_type"], "player")
        self.assertEqual(graph.nodes["match:1"]["node_type"], "match")
        self.assertEqual(graph["player:10"]["match:1"]["deliveries"], 2)
        self.assertEqual(graph["player:10"]["match:1"]["pressure_opportunities"], 1)
        self.assertNotIn("player:12", graph)


if __name__ == "__main__":
    unittest.main()
