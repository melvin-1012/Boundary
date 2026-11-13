import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analytics.analyst_tools import (
    CricketToolbox,
    analyze_with_tools,
)
from analytics.cricket_analyst import OpenAICompatibleProvider
from analytics.cricket_metrics import calculate_player_metrics
from tests.test_cricket_analyst import analyst_fixture


class ToolCallingProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []

    def chat_with_tools(self, messages, tools):
        self.messages.append((messages, tools))
        return self.responses.pop(0)


def _function_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class CricketToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp.name) / "data"
        raw = self.data_root / "raw"
        raw.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "match_id": 101,
                    "comp_id": 1,
                    "match_date": "2023-01-01",
                    "home_team": "Falcons",
                    "away_team": "Royals",
                    "venue_country": "India",
                },
                {
                    "match_id": 102,
                    "comp_id": 2,
                    "match_date": "2024-01-01",
                    "home_team": "Royals",
                    "away_team": "Falcons",
                    "venue_country": "Australia",
                },
            ]
        ).to_csv(raw / "matches.csv", index=False)
        pd.DataFrame(
            [
                {"comp_id": 1, "comp_name": "IPL 2023", "match_format": "T20", "season": "2023"},
                {"comp_id": 2, "comp_name": "T20I Series 2024", "match_format": "T20I", "season": "2024"},
            ]
        ).to_csv(raw / "competitions.csv", index=False)
        pd.DataFrame(
            [
                {"comp_id": 1, "team_id": 7, "team_name": "Falcons", "player_id": 1, "player_name": "Alex Alpha"},
                {"comp_id": 1, "team_id": 8, "team_name": "Royals", "player_id": 2, "player_name": "Blake Bravo"},
            ]
        ).to_csv(raw / "competition_team_player_mapping.csv", index=False)
        pd.DataFrame(
            [
                {"comp_id": 1, "team_id": 7, "team_name": "Falcons"},
                {"comp_id": 1, "team_id": 8, "team_name": "Royals"},
            ]
        ).to_csv(raw / "teams.csv", index=False)
        pd.DataFrame(
            [{"match_id": 101, "team_id": 7, "player_id": 1, "batting_order": 1}]
        ).to_csv(raw / "playing_eleven.csv", index=False)
        pd.DataFrame(
            [
                {
                    "match_id": 101,
                    "innings": 1,
                    "innings_ball_num": 1,
                    "striker_id": 1,
                    "striker_name": "Alex Alpha",
                    "runs": 4,
                }
            ]
        ).to_csv(raw / "ball_by_ball.csv", index=False)
        self.deliveries, self.teams = analyst_fixture()
        self.toolbox = CricketToolbox(
            self.data_root,
            curated_deliveries=self.deliveries,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_discovers_all_six_source_datasets_and_schema(self):
        catalog = self.toolbox.discover_data()
        source_tables = {item["table_name"] for item in catalog["datasets"]}

        self.assertEqual(
            source_tables,
            {
                "raw_ball_by_ball",
                "raw_matches",
                "raw_competitions",
                "raw_teams",
                "raw_playing_eleven",
                "raw_competition_team_player_mapping",
            },
        )
        matches = self.toolbox.inspect_table("raw_matches")
        self.assertEqual(matches["table"]["row_count"], 2)
        self.assertIn("match_date", matches["table"]["date_ranges"])

    def test_entity_lookups_and_match_filtering_use_registered_records(self):
        players = self.toolbox.find_players("Alex")
        teams = self.toolbox.find_teams("Royals")
        matches = self.toolbox.find_matches(season="2023", team="Falcons")

        self.assertEqual(players["rows"][0]["player_id"], 1)
        self.assertEqual(teams["rows"][0]["team_id"], 8)
        self.assertEqual([row["match_id"] for row in matches["rows"]], [101])

    def test_match_lookup_can_filter_a_date_range_and_venue(self):
        matches = self.toolbox.find_matches(
            start_date="2023-06-01",
            end_date="2023-12-31",
            venue="India",
        )

        self.assertEqual(matches["rows"], [])
        scoped = self.toolbox.find_matches(
            start_date="2023-01-01",
            end_date="2023-12-31",
            venue="India",
        )
        self.assertEqual([row["match_id"] for row in scoped["rows"]], [101])

    def test_read_only_query_supports_bound_parameters_and_catalog_tables(self):
        result = self.toolbox.query_cricket_data(
            "SELECT match_id, home_team FROM raw_matches WHERE match_id = ?",
            ["raw_matches"],
            [101],
        )

        self.assertTrue(result["read_only"])
        self.assertEqual(result["rows"], [{"match_id": 101, "home_team": "Falcons"}])

    def test_query_rejects_mutations_multiple_statements_unknown_tables_and_columns(self):
        for sql, tables in (
            ("DELETE FROM raw_matches", ["raw_matches"]),
            ("SELECT * FROM raw_matches; SELECT * FROM raw_matches", ["raw_matches"]),
            ("SELECT * FROM secret_table", ["raw_matches"]),
            ("SELECT secret_column FROM raw_matches", ["raw_matches"]),
        ):
            with self.subTest(sql=sql), self.assertRaises(ValueError):
                self.toolbox.query_cricket_data(sql, tables)

    def test_query_rejects_unapproved_functions(self):
        with self.assertRaises(ValueError):
            self.toolbox.query_cricket_data(
                "SELECT random() FROM raw_matches",
                ["raw_matches"],
            )

    def test_calculated_role_metrics_reuse_existing_verified_metric_functions(self):
        result = self.toolbox.calculate_role_metrics("batter", limit=10)
        existing = calculate_player_metrics(self.deliveries)["batters"]
        first = result["metrics"][0]
        expected = existing.loc[existing["striker_id"].eq(first["striker_id"])].iloc[0]

        self.assertAlmostEqual(
            first["pressure_strike_rate"],
            expected["pressure_strike_rate"],
        )
        self.assertGreater(result["scope"]["deliveries"], 0)
        self.assertTrue(result["evidence"])

    def test_role_metrics_support_filters_comparisons_and_spi_sample_warning(self):
        self.deliveries["pace_or_spin"] = [
            "spin" if index % 2 else "pace"
            for index in range(len(self.deliveries))
        ]
        toolbox = CricketToolbox(
            self.data_root,
            curated_deliveries=self.deliveries,
        )
        comparison = toolbox.calculate_role_metrics(
            "batter",
            player_ids=[1, 2],
            phase="death",
            bowling_type="spin",
            pressure_only=True,
            sort_by="pressure_strike_rate",
            limit=5,
        )
        self.assertEqual(comparison["scope"]["phase"], "death")
        self.assertEqual(comparison["scope"]["bowling_type"], "spin")
        self.assertTrue(comparison["verification"]["status"] == "passed")

        one_match = self.deliveries.loc[self.deliveries["match_id"].eq(1001)]
        small_toolbox = CricketToolbox(
            self.data_root,
            curated_deliveries=one_match,
        )
        small_sample = small_toolbox.calculate_role_metrics(
            "batter", sort_by="spi", limit=2
        )
        self.assertTrue(
            any("SPI is unavailable" in item for item in small_sample["limitations"])
        )

    def test_tool_orchestrator_executes_multiple_calls_and_returns_evidence(self):
        provider = ToolCallingProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        _function_call("call-1", "discover_data", {"query": "matches"})
                    ],
                },
                {
                    "content": None,
                    "tool_calls": [
                        _function_call(
                            "call-2",
                            "query_cricket_data",
                            {
                                "sql": "SELECT match_id, home_team FROM raw_matches WHERE match_id = ?",
                                "tables": ["raw_matches"],
                                "parameters": ["101"],
                            },
                        )
                    ],
                },
                {"content": "The requested records are available in the evidence table.", "tool_calls": []},
            ]
        )
        result = analyze_with_tools(
            "Investigate the 2023 Falcons match and show its source match record.",
            provider,
            self.toolbox,
        )

        self.assertEqual(result["status"], "answer")
        self.assertEqual([call["tool"] for call in result["tool_trace"]], ["discover_data", "query_cricket_data"])
        self.assertEqual(result["tool_results"][1]["result"]["rows"][0]["match_id"], 101)
        self.assertEqual(len(provider.messages), 3)

    def test_model_numeric_summary_is_withheld_but_calculated_values_remain(self):
        provider = ToolCallingProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        _function_call("call-1", "find_players", {"name_query": "Alex"})
                    ],
                },
                {"content": "Alex scored 42 runs.", "tool_calls": []},
            ]
        )
        result = analyze_with_tools("Find Alex Alpha.", provider, self.toolbox)

        self.assertIn("unverified numeric claims", result["answer"])
        self.assertEqual(result["tool_results"][0]["result"]["rows"][0]["player_id"], 1)

    def test_follow_up_context_is_sent_to_the_tool_calling_model(self):
        provider = ToolCallingProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        _function_call("call-1", "find_players", {"name_query": "Alex"})
                    ],
                },
                {"content": "The source mapping is shown in the evidence.", "tool_calls": []},
            ]
        )
        history = [
            {
                "question": "Find batter Alex Alpha",
                "result": {
                    "status": "answer",
                    "answer": "The player mapping is verified.",
                    "tool_results": [{"tool": "find_players", "result": {"rows": [{"player_id": 1}]}}],
                },
            }
        ]
        analyze_with_tools(
            "Show his player ID.",
            provider,
            self.toolbox,
            conversation=history,
        )

        serialized_context = json.dumps(provider.messages[0][0])
        self.assertIn("Find batter Alex Alpha", serialized_context)
        self.assertIn("player_id", serialized_context)
        self.assertIn("1", serialized_context)

    def test_provider_tool_errors_are_returned_without_exposing_secrets(self):
        provider = ToolCallingProvider(
            [
                {
                    "content": None,
                    "tool_calls": [
                        _function_call(
                            "call-1",
                            "query_cricket_data",
                            {
                                "sql": "DELETE FROM raw_matches",
                                "tables": ["raw_matches"],
                            },
                        )
                    ],
                },
                {"content": "The requested operation was not permitted.", "tool_calls": []},
            ]
        )
        result = analyze_with_tools("Delete the records.", provider, self.toolbox)

        self.assertEqual(result["status"], "insufficient")
        self.assertIn("error", result["tool_results"][0])
        self.assertIn("SELECT", result["tool_results"][0]["error"])

    def test_openai_compatible_provider_sends_structured_tool_requests(self):
        provider = OpenAICompatibleProvider("private-test-key", "test-model")
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                _function_call(
                                    "call-1",
                                    "discover_data",
                                    {"query": "matches"},
                                )
                            ],
                        }
                    }
                ]
            }
        ).encode()
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = provider.chat_with_tools(
                [{"role": "user", "content": "Inspect the match table."}],
                [{"type": "function", "function": {"name": "discover_data"}}],
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(result["tool_calls"][0]["function"]["name"], "discover_data")
        self.assertNotIn(b"private-test-key", request.data)
        self.assertTrue(request.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
