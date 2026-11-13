"""Generate a data dictionary from the six source CSV files."""

import json
from pathlib import Path

import pandas as pd

from ingestion.data_validation import EXPECTED_COLUMNS, KEY_COLUMNS


ROOT = Path(__file__).resolve().parents[1]


def build_data_dictionary(data_dir=ROOT / "data" / "raw"):
    entries = []
    for filename in EXPECTED_COLUMNS:
        path = Path(data_dir) / filename
        if not path.exists():
            continue
        frame = pd.read_csv(path, low_memory=False)
        key_columns = set(KEY_COLUMNS[filename])
        for column in frame.columns:
            non_null = frame[column].dropna()
            examples = non_null.astype(str).drop_duplicates().head(3).tolist()
            entries.append(
                {
                    "dataset": filename,
                    "column": column,
                    "dtype": str(frame[column].dtype),
                    "nullable": bool(frame[column].isna().any()),
                    "missing_count": int(frame[column].isna().sum()),
                    "distinct_non_null": int(non_null.nunique()),
                    "candidate_key_column": column in key_columns,
                    "example_values": json.dumps(examples, ensure_ascii=False),
                }
            )
    return pd.DataFrame(entries)


def write_data_dictionary(data_dir=ROOT / "data" / "raw", output=None):
    output = Path(output or ROOT / "data" / "metadata" / "data_dictionary.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    dictionary = build_data_dictionary(data_dir)
    dictionary.to_csv(output, index=False)
    return dictionary


if __name__ == "__main__":
    result = write_data_dictionary()
    print(f"Wrote {len(result)} column definitions.")
