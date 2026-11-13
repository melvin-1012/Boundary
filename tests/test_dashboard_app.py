import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class DashboardIntegrationTests(unittest.TestCase):
    def test_dashboard_renders_analytics_tabs_and_theme_switch(self):
        app = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=90).run()

        self.assertEqual(len(app.exception), 0)
        self.assertTrue(
            any("BOUNDARY" in element.value for element in app.markdown)
        )
        theme_selector = next(widget for widget in app.selectbox if widget.key == "dashboard_theme")
        self.assertEqual(theme_selector.value, "Rajasthan Royals Theme")
        self.assertEqual(
            [tab.label.strip() for tab in app.tabs],
            [
                "Match centre",
                "Pressure Analytics",
                "Batting room",
                "Bowling lab",
                "Player Insights",
                "Methodology",
                "Fixtures",
                "Final Methodology & Validation",
                "AI Cricket Analyst",
            ],
        )
        appearance_selector = next(
            widget for widget in app.selectbox if widget.key == "dashboard_appearance"
        )
        self.assertEqual(appearance_selector.value, "Dark mode")
        appearance_selector.select("Light mode").run()
        self.assertEqual(len(app.exception), 0)
        appearance_selector = next(
            widget for widget in app.selectbox if widget.key == "dashboard_appearance"
        )
        self.assertEqual(appearance_selector.value, "Light mode")
        theme_selector = next(
            widget for widget in app.selectbox if widget.key == "dashboard_theme"
        )
        theme_selector.select("IPL Theme").run()
        self.assertEqual(len(app.exception), 0)
        theme_selector = next(widget for widget in app.selectbox if widget.key == "dashboard_theme")
        self.assertEqual(theme_selector.value, "IPL Theme")
        theme_selector.select("Rajasthan Royals Theme").run()
        self.assertEqual(len(app.exception), 0)
        theme_selector = next(widget for widget in app.selectbox if widget.key == "dashboard_theme")
        self.assertEqual(theme_selector.value, "Rajasthan Royals Theme")
        appearance_selector = next(
            widget for widget in app.selectbox if widget.key == "dashboard_appearance"
        )
        appearance_selector.select("Dark mode").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.chat_input), 1)
        app.chat_input[0].set_value(
            "Show batter Rinku Singh pressure performance in IPL 2023"
        ).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            app.session_state["cricket_analyst_conversation"][0]["result"]["status"],
            "answer",
        )
        app.chat_input[0].set_value(
            "How much is the difference between first and second best player under pressure?"
        ).run()
        self.assertEqual(len(app.exception), 0)
        comparison = app.session_state["cricket_analyst_conversation"][1]["result"]
        self.assertEqual(comparison["status"], "answer")
        self.assertEqual(
            set(comparison["comparison_results"]) - {"relative_comparison_support"},
            {"batter", "bowler"},
        )
        self.assertTrue(
            comparison["comparison_results"]["batter"]["comparison"][
                "first_minus_second"
            ]
            is not None
        )
        app.chat_input[0].set_value(
            "how much better is the best player under pressure from the second best player"
        ).run()
        self.assertEqual(len(app.exception), 0)
        screenshot_phrase = app.session_state["cricket_analyst_conversation"][2]["result"]
        self.assertEqual(screenshot_phrase["status"], "answer")
        self.assertNotIn("clarification_options", screenshot_phrase)
        self.assertEqual(len(screenshot_phrase["metrics"]), 4)


if __name__ == "__main__":
    unittest.main()
