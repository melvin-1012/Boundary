import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from analytics.final_validation import run_final_validation


ROOT = Path(__file__).resolve().parents[1]


class FinalValidationTests(unittest.TestCase):
    def test_scoped_raw_calculations_match_curated_and_hash_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_final_validation(
                report_path=Path(temporary_directory) / "final_validation.json"
            )

        self.assertEqual(result["scope"]["selected_deliveries"], 194_014)
        self.assertTrue(result["raw_hashes_match_etl_manifest"])
        self.assertTrue(result["validation_checks"]["raw_curated_join_has_no_orphan_rows"])
        self.assertTrue(
            result["validation_checks"]["independently_recomputed_columns_match_curated"]
        )
        self.assertEqual(
            result["innings_and_not_outs"]["innings4_target_mismatch_deliveries"], 0
        )
        self.assertGreater(
            result["boundaries"]["four_flag_mismatches_against_source_runs_equals_4"], 0
        )
        self.assertFalse(result["raw_data_modified"])

    def test_ranking_files_are_exactly_ten_and_match_recorded_hashes(self):
        manifest = json.loads((ROOT / "reports" / "final_rankings.json").read_text())
        self.assertEqual(manifest["status"], "provisional")
        for role in ("batter", "bowler"):
            path = ROOT / "reports" / f"top_10_{role}s.csv"
            frame = pd.read_csv(path)
            self.assertEqual(len(frame), 10)
            self.assertTrue(frame["player_id"].is_unique)
            self.assertEqual(frame["rank"].tolist(), list(range(1, 11)))
            digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(manifest["ranking_file_sha256"][f"{role}s"], digest)
            self.assertTrue(
                manifest["independent_spi_checks"][role]["independent_recalculation_passed"]
            )
            self.assertEqual(
                manifest["independent_spi_checks"][role]["maximum_absolute_spi_error"],
                0.0,
            )


if __name__ == "__main__":
    unittest.main()
