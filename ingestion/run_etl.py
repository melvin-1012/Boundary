"""Run the read-only, reproducible CSV-to-Parquet and analytics ETL."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

from analytics.cricket_metrics import calculate_player_metrics, reconstruct_match_state
from ingestion.data_dictionary import write_data_dictionary
from ingestion.dataset_relationships import write_relationships
from ingestion.data_validation import (
    EXPECTED_COLUMNS,
    audit_frames,
    select_hackathon_matches,
)


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CURATED = ROOT / "data" / "curated"
REPORT = ROOT / "reports" / "data_quality_report.json"


def load_source_frames(data_dir=RAW):
    frames = {}
    for filename in EXPECTED_COLUMNS:
        path = Path(data_dir) / filename
        if path.exists():
            frames[filename] = pd.read_csv(path, low_memory=False)
    return frames


def run_etl(data_dir=RAW, processed_dir=PROCESSED, curated_dir=CURATED):
    data_dir, processed_dir, curated_dir = map(
        Path, (data_dir, processed_dir, curated_dir)
    )
    frames = load_source_frames(data_dir)
    validation = audit_frames(frames)
    if validation["summary"]["failures"]:
        raise ValueError(
            "Source validation has blocking failures: "
            f"{validation['summary']['failures']} checks failed."
        )
    if len(frames) != len(EXPECTED_COLUMNS):
        raise FileNotFoundError("All six raw source datasets are required for ETL.")

    processed_dir.mkdir(parents=True, exist_ok=True)
    curated_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    source_hashes = {}
    for filename, frame in frames.items():
        source_path = data_dir / filename
        digest = hashlib.sha256()
        with source_path.open("rb") as source_file:
            for block in iter(lambda: source_file.read(1024 * 1024), b""):
                digest.update(block)
        source_hashes[filename] = digest.hexdigest()
        target = processed_dir / f"{Path(filename).stem}.parquet"
        frame.to_parquet(target, index=False, compression="snappy")
        outputs[str(target.relative_to(ROOT))] = {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "bytes": int(target.stat().st_size),
            "content": "source values retained; no row-level cleaning or deduplication",
        }

    matches = frames["matches.csv"]
    competitions = frames["competitions.csv"]
    scoped_matches = select_hackathon_matches(matches, competitions)
    scoped_ids = set(scoped_matches["match_id"])
    balls = frames["ball_by_ball.csv"]
    scoped_balls = balls.loc[balls["match_id"].isin(scoped_ids)].copy()
    reconstructed = reconstruct_match_state(
        scoped_balls, scoped_matches, competitions
    )
    metrics = calculate_player_metrics(reconstructed)

    curated_frames = {
        "pressure_deliveries": reconstructed,
        "batter_match_metrics": metrics["batter_matches"],
        "bowler_match_metrics": metrics["bowler_matches"],
        "batter_metrics": metrics["batters"],
        "bowler_metrics": metrics["bowlers"],
    }
    for name, frame in curated_frames.items():
        target = curated_dir / f"{name}.parquet"
        frame.to_parquet(target, index=False, compression="snappy")
        outputs[str(target.relative_to(ROOT))] = {
            "rows": int(len(frame)),
            "columns": int(len(frame.columns)),
            "bytes": int(target.stat().st_size),
        }

    write_data_dictionary(data_dir)
    relationships = write_relationships()
    quality_report = {
        "validation": validation,
        "etl": {
            "status": "completed_with_warnings"
            if validation["summary"]["warnings"]
            else "completed",
            "pipeline_version": "1.0",
            "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "input_files": sorted(frames),
            "input_sha256": source_hashes,
            "raw_data_modified": False,
            "scope": {
                "start_date": "2022-01-01",
                "selected_matches": int(len(scoped_matches)),
                "selected_deliveries": int(len(reconstructed)),
                "competitions": sorted(scoped_matches["comp_name"].dropna().unique()),
            },
            "pressure_reference_run_rate": reconstructed.attrs.get(
                "pressure_reference_run_rate"
            ),
            "pressure_reference_source": reconstructed.attrs.get(
                "pressure_reference_source"
            ),
            "pressure_definition": "transparent heuristic; see docs/pressure_methodology.md",
            "source_interpretation": {
                "team_runs": "runs + extras1_runs + extras_2_runs",
                "legal_ball": "extras_type not in {'wide', 'Overstep'}",
                "batter_runs": "source runs field; flagged discrepancies are retained",
                "bowler_runs": "team runs excluding byes, legbyes, and penalty extras",
                "bowler_wickets": "only observed Bowled, Caught, LBW, Stump, Hit Wicket",
                "unknown_extras": "other extras remain included in bowler runs and legal-ball treatment is provisional",
            },
            "outputs": outputs,
            "metadata_outputs": [
                "data/metadata/data_dictionary.csv",
                str(relationships.relative_to(ROOT)),
            ],
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(quality_report, indent=2, default=str) + "\n")
    return quality_report


def main():
    report = run_etl()
    summary = report["validation"]["summary"]
    print(
        "ETL completed: "
        f"{summary['passed_checks']} checks passed, "
        f"{summary['warnings']} warnings, {summary['failures']} failures."
    )
    print(f"Quality report: {REPORT}")


if __name__ == "__main__":
    main()
