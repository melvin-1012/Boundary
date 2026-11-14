import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RawImmutabilityTests(unittest.TestCase):
    def test_raw_sources_match_latest_etl_hash_manifest(self):
        report = json.loads((ROOT / "reports" / "data_quality_report.json").read_text())
        expected = report["etl"]["input_sha256"]
        self.assertEqual(len(expected), 6)
        for filename, digest in expected.items():
            path = ROOT / "data" / "raw" / filename
            actual = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            self.assertEqual(actual, digest, filename)
        self.assertFalse(report["etl"]["raw_data_modified"])


if __name__ == "__main__":
    unittest.main()
