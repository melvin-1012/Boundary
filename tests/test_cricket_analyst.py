import os
import unittest
from unittest.mock import patch

import pandas as pd

from analytics.cricket_analyst import (
    LLMProviderError,
    SUPPORTED_QUESTION_CATEGORIES,
    analyze_question,
    generate_commentary,
    parse_question,
    provider_from_environment,
    resolve_players,
)


def analyst_fixture():
    rows = []
    for match_id in range(1001, 1007):
        match_format = "T20" if match_id % 2 else "T20I"
        season = "2023" if match_id <= 1003 else "2024"
        competition = (
            f"IPL {season}"
            if match_format == "T20"
            else f"T20I Series {season}"
        )
        comp_id = 1 if match_format == "T20" else 2
        for ball in range(8):
            pressure = ball < 4
            batter_id = 1 + ball % 2
            bowler_id = 10 + ball % 2
            runs = (
                (4 if batter_id == 1 else 2)
                if pressure
                else (1 if batter_id == 1 else 0)
            )
            rows.append(
                {
                    "match_id": match_id,
                    "comp_id": comp_id,
                    "comp_name": competition,
                    "match_format": match_format,
                    "season": season,
                    "innings": 2,
                    "innings_ball_num": ball + 1,
                    "innings_phase": "death",
                    "striker_id": batter_id,
                    "striker_name": "Alex Alpha" if batter_id == 1 else "Blake Bravo",
                    "bowler_id": bowler_id,
                    "bowler_name": "Casey Charlie" if bowler_id == 10 else "Drew Delta",
                    "dismissed_player_id": None,
                    "is_batting_pressure": pressure,
                    "is_bowling_pressure": pressure,
                    "pressure_batter_ball": pressure,
                    "pressure_bowler_ball": pressure,
                    "batter_runs": runs,
                    "is_batter_ball_faced": True,
                    "is_four": runs == 4,
                    "is_six": False,
                    "is_legal_ball": True,
                    "bowler_conceded_runs": runs,
                    "is_bowler_wicket": False,
                    "is_dot_ball": runs == 0,
                    "has_boundary_flag": runs == 4,
                    "team_runs": runs,
                    "score_before": ball * 3,
                    "wickets_before": ball // 3,
                    "legal_balls_before": ball,
                    "balls_remaining": 120 - ball,
                    "target": 160,
                    "runs_required": 100 - ball,
                    "required_run_rate": 5.0,
                    "current_run_rate": 6.0,
                    "reference_run_rate": 8.0,
                    "innings_progress": ball / 20,
                    "batting_pressure": 70.0 if pressure else 20.0,
                    "bowling_pressure": 70.0 if pressure else 20.0,
                    "batting_team_id": 7,
                    "bowling_team_id": 8,
                }
            )
    deliveries = pd.DataFrame(rows)
    teams = pd.DataFrame(
        [
            {"comp_id": 1, "team_id": 7, "team_name": "Falcons"},
            {"comp_id": 1, "team_id": 8, "team_name": "Royals"},
            {"comp_id": 2, "team_id": 7, "team_name": "Falcons"},
            {"comp_id": 2, "team_id": 8, "team_name": "Royals"},
        ]
    )
    return deliveries, teams


class StaticProvider:
    def __init__(self, response="", interpretation=None):
        self.response = response
        self.interpretation = interpretation
        self.received = None

    def interpret_question(self, question, allowed_context):
        return self.interpretation

    def explain(self, verified_summary):
        self.received = verified_summary
        return self.response


class CricketAnalystTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deliveries, cls.teams = analyst_fixture()

    def test_player_name_and_id_resolution(self):
        self.assertEqual(
            resolve_players("Compare batter Alex Alpha with player ID 2", self.deliveries),
            [(1, "Alex Alpha"), (2, "Blake Bravo")],
        )
        shared_surname = self.deliveries.copy()
        shared_surname.loc[shared_surname["striker_id"].eq(1), "striker_name"] = "Rinku Singh"
        shared_surname.loc[shared_surname["striker_id"].eq(2), "striker_name"] = "Mandeep Singh"
        self.assertEqual(
            resolve_players("Show batter Rinku Singh", shared_surname),
            [(1, "Rinku Singh")],
        )

    def test_ambiguous_role_and_indian_scope_are_clarified(self):
        general = analyze_question("Who is the best batter?", self.deliveries)
        indian = analyze_question("Who is the best Indian player in 2023?", self.deliveries)

        self.assertEqual(general["status"], "clarification")
        self.assertEqual(indian["status"], "clarification")
        self.assertIn("Players in IPL 2025", indian["clarification_options"])

    def test_natural_language_rank_questions_use_defaults_and_calculate_results(self):
        questions = [
            "How much is the difference between first and second best player under pressure?",
            "How far ahead is the best batter from the second best?",
            "Who is the second most reliable bowler?",
            "Compare the top three pressure performers.",
            "How much better is the top batter than the average batter?",
            "Who ranks first overall in pressure performance?",
            "Is the gap between first and second significant?",
            "Why is the top-ranked player better?",
        ]
        results = [
            analyze_question(question, self.deliveries, teams=self.teams)
            for question in questions
        ]

        for question, result in zip(questions, results):
            with self.subTest(question=question):
                self.assertNotEqual(result["status"], "clarification")
                self.assertTrue(result["metrics"])
                self.assertTrue(result["verification"])
        self.assertEqual(
            {row["role"] for row in results[0]["metrics"]},
            {"batter", "bowler"},
        )
        self.assertIn(
            results[0]["comparison_results"]["relative_comparison_support"][
                "more_supported_role"
            ],
            {"batter", "bowler"},
        )
        self.assertIsNotNone(
            results[0]["comparison_results"]["batter"]["comparison"]["first_minus_second"]
        )
        self.assertIn("Alex Alpha", results[0]["answer"])
        self.assertIn("Drew Delta", results[0]["answer"])
        self.assertIn("SPI points", results[0]["answer"])
        self.assertIn("pressure opportunities", results[0]["answer"])
        self.assertEqual(
            results[2]["metrics"][0]["rank"],
            2,
        )
        self.assertTrue(
            any("Only 2 eligible" in item for item in results[3]["limitations"])
        )
        self.assertEqual(
            results[4]["scope"]["ranking_comparison"],
            "top_vs_average",
        )
        self.assertTrue(
            any("statistical significance test" in item.lower() for item in results[6]["limitations"])
        )

    def test_season_competition_and_phase_filters(self):
        parsed = parse_question(
            "Show batter Alex Alpha under pressure in death overs, IPL 2023",
            self.deliveries,
            self.teams,
        )
        result = analyze_question(
            "Show batter Alex Alpha under pressure in death overs, IPL 2023",
            self.deliveries,
            teams=self.teams,
        )

        self.assertEqual(parsed.season, "2023")
        self.assertEqual(parsed.format, "T20")
        self.assertEqual(parsed.phase, "death")
        self.assertEqual(result["status"], "answer")
        self.assertEqual(result["scope"]["seasons"], ["2023"])
        self.assertEqual(result["scope"]["competitions"], ["IPL 2023"])

    def test_batter_and_bowler_metrics_have_verified_match_evidence(self):
        batter = analyze_question("Show batter Alex Alpha pressure performance", self.deliveries)
        bowler = analyze_question("Show bowler Casey Charlie pressure economy", self.deliveries)

        self.assertEqual(batter["status"], "answer")
        self.assertEqual(batter["verification"][:8], "Player I")
        self.assertEqual(batter["metrics"][0]["pressure_opportunities"], 12)
        self.assertEqual(batter["metrics"][0]["performance"], 400.0)
        self.assertIn("SPI", batter["metrics"][0])
        self.assertIn("reliability", batter["metrics"][0])
        self.assertTrue(batter["evidence"])
        self.assertEqual(bowler["status"], "answer")
        self.assertEqual(bowler["metrics"][0]["pressure_opportunities"], 12)
        self.assertTrue(bowler["evidence"])

    def test_bowler_verification_counts_extras_runs_but_only_legal_balls(self):
        deliveries = self.deliveries.copy()
        wide = deliveries.index[
            deliveries["match_id"].eq(1001)
            & deliveries["innings_ball_num"].eq(1)
        ][0]
        deliveries.loc[wide, "is_legal_ball"] = False
        deliveries.loc[wide, "pressure_bowler_ball"] = False
        deliveries.loc[wide, "bowler_conceded_runs"] = 6

        result = analyze_question(
            "Show bowler Casey Charlie pressure economy", deliveries
        )

        self.assertEqual(result["status"], "answer")
        self.assertEqual(result["metrics"][0]["pressure_opportunities"], 11)
        self.assertEqual(result["metrics"][0]["performance"], 6 * 50 / 11)

    def test_player_comparison_and_spi_explanation(self):
        comparison = analyze_question(
            "Compare batter Alex Alpha versus Blake Bravo under pressure",
            self.deliveries,
        )
        explanation = analyze_question(
            "Explain the SPI ranking of batter Alex Alpha",
            self.deliveries,
        )

        self.assertEqual(comparison["status"], "answer")
        self.assertEqual({row["player_id"] for row in comparison["metrics"]}, {1, 2})
        self.assertTrue(all("spi" in row for row in comparison["metrics"]))
        self.assertEqual(explanation["status"], "answer")
        self.assertIn("spi", explanation["metrics"][0])
        self.assertTrue(explanation["evidence"])

    def test_format_and_season_comparisons_include_evidence(self):
        formats = analyze_question(
            "Show me the difference between the best IPL batter and best T20I batter",
            self.deliveries,
        )
        seasons = analyze_question(
            "Show batter pressure leaders by season", self.deliveries
        )

        self.assertEqual(formats["intent"], "format_comparison")
        self.assertEqual(formats["status"], "insufficient")
        self.assertIn("eligibility", " ".join(formats["limitations"]).lower())
        self.assertEqual(seasons["status"], "answer")
        self.assertTrue(seasons["metrics"])
        self.assertTrue(seasons["evidence"])
        season_comparison = analyze_question(
            "Compare batter Alex Alpha across 2023 and 2024", self.deliveries
        )
        self.assertEqual(season_comparison["intent"], "season_comparison")
        self.assertEqual(season_comparison["status"], "answer")
        self.assertEqual(
            {row["season"] for row in season_comparison["metrics"]},
            {"2023", "2024"},
        )
        self.assertTrue(season_comparison["evidence"])

    def test_team_and_match_level_analysis(self):
        team = analyze_question(
            "Best batter under pressure for Falcons", self.deliveries, teams=self.teams
        )
        match = analyze_question(
            "Show batting pressure for match 1001", self.deliveries
        )

        self.assertEqual(team["status"], "answer")
        self.assertEqual(team["scope"]["team"], "Falcons")
        self.assertEqual(match["status"], "answer")
        self.assertEqual(match["scope"]["match_id"], 1001)
        self.assertTrue(match["evidence"])

    def test_consistency_reliability_and_sample_eligibility(self):
        consistent = analyze_question(
            "Most consistent batter under pressure", self.deliveries
        )
        reliable = analyze_question(
            "Most reliable bowler under pressure", self.deliveries
        )
        sample = analyze_question(
            "Show batter sample size and eligibility for Alex Alpha",
            self.deliveries,
        )

        self.assertEqual(consistent["status"], "answer")
        self.assertEqual(reliable["status"], "answer")
        self.assertEqual(sample["status"], "answer")
        self.assertEqual(consistent["metrics"][0]["rank"], 1)
        self.assertEqual(reliable["metrics"][0]["rank"], 1)
        self.assertTrue(sample["metrics"][0]["eligible"])

    def test_unsupported_sql_and_empty_scope_are_not_executed(self):
        sql = analyze_question("DROP TABLE pressure_deliveries", self.deliveries)
        empty = analyze_question(
            "Best batter under pressure in IPL 2022", self.deliveries
        )

        self.assertEqual(sql["status"], "unsupported")
        self.assertIn("No SQL", sql["answer"])
        self.assertEqual(empty["status"], "insufficient")
        self.assertEqual(empty["metrics"], [])

    def test_empty_input_and_supported_category_catalogue(self):
        empty = analyze_question("Best batter under pressure", self.deliveries.iloc[0:0])

        self.assertEqual(empty["status"], "insufficient")
        self.assertIn("format_comparison", SUPPORTED_QUESTION_CATEGORIES)

    def test_commentary_receives_verified_results_and_numeric_claims_are_rejected(self):
        result = analyze_question("Best batter under pressure", self.deliveries)
        provider = StaticProvider("The results show a strong pressure response.")

        commentary = generate_commentary(provider, result)

        self.assertTrue(commentary)
        self.assertTrue(provider.received["verified_metrics"])
        with self.assertRaises(LLMProviderError):
            generate_commentary(StaticProvider("The top score is 99."), result)

    def test_llm_question_interpretation_is_validated_against_archive_entities(self):
        valid = StaticProvider(
            interpretation={
                "intent": "player_profile",
                "role": "batter",
                "player_ids": [1],
                "season": "2023",
                "format": "T20",
                "competition": "IPL 2023",
                "phase": "death",
                "match_id": None,
                "team": None,
            }
        )
        result = analyze_question(
            "Show batter Alex Alpha pressure performance in IPL 2023 death overs",
            self.deliveries,
            teams=self.teams,
            provider=valid,
        )
        self.assertEqual(result["status"], "answer")
        self.assertEqual(result["scope"]["competitions"], ["IPL 2023"])
        invalid = StaticProvider(
            interpretation={
                "intent": "player_profile",
                "role": "batter",
                "player_ids": [999999],
                "season": None,
                "format": None,
                "competition": None,
                "phase": None,
                "match_id": None,
                "team": None,
            }
        )
        fallback = analyze_question(
            "Show batter Alex Alpha pressure performance in IPL 2023 death overs",
            self.deliveries,
            provider=invalid,
        )
        self.assertEqual(fallback["status"], "answer")
        self.assertEqual(fallback["metrics"][0]["player_id"], 1)

    def test_provider_configuration_does_not_require_a_key(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(provider_from_environment())


if __name__ == "__main__":
    unittest.main()
