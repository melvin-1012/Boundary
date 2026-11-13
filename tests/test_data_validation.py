import unittest

import pandas as pd

from ingestion.data_validation import (
    audit_frames,
    key_profile,
    select_hackathon_matches,
    _unmapped_count,
)


class DataValidationTests(unittest.TestCase):
    def test_selects_exact_ipl_and_post_2022_t20i_only(self):
        competitions = pd.DataFrame(
            [
                (1715, "IPL 2023", "T20"),
                (2, "Other T20 tournament", "T20"),
                (3, "T20I series", "T20I"),
            ],
            columns=["comp_id", "comp_name", "match_format"],
        )
        matches = pd.DataFrame(
            [
                (10, 1715, "2023-04-01"),
                (20, 2, "2023-04-01"),
                (30, 3, "2022-01-01"),
                (31, 3, "2021-12-31"),
            ],
            columns=["match_id", "comp_id", "match_date"],
        )

        selected = select_hackathon_matches(matches, competitions)

        self.assertEqual(selected["match_id"].tolist(), [10, 30])
        self.assertEqual(selected["comp_name"].tolist(), ["IPL 2023", "T20I series"])

    def test_key_profile_reports_all_duplicate_and_null_key_rows(self):
        frame = pd.DataFrame({"match_id": [1, 1, 2, None], "innings": [1, 1, 1, 1]})

        profile = key_profile(frame, ["match_id", "innings"])

        self.assertEqual(profile["duplicate_rows"], 2)
        self.assertEqual(profile["null_rows"], 1)

    def test_foreign_key_check_uses_composite_keys(self):
        source = pd.DataFrame({"comp_id": [1, 1], "team_id": [10, 11]})
        target = pd.DataFrame({"competition": [1], "id": [10]})

        missing = _unmapped_count(
            source, target, ["comp_id", "team_id"], ["competition", "id"]
        )

        self.assertEqual(missing, 1)

    def test_missing_source_files_are_reported_without_crashing(self):
        report = audit_frames({})

        self.assertEqual(report["summary"]["status"], "fail")
        self.assertEqual(report["summary"]["failures"], 6)
        self.assertFalse(report["raw_data_modified"])


if __name__ == "__main__":
    unittest.main()
