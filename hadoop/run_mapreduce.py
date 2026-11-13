"""Run Hadoop Streaming-compatible aggregation locally and compare with pandas."""

import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "curated" / "pressure_deliveries.parquet"
REPORT = ROOT / "reports" / "mapreduce_validation.json"
OUTPUT = ROOT / "reports" / "mapreduce" / "player_aggregates.csv"
MAPPER = ROOT / "hadoop" / "mapper.py"
REDUCER = ROOT / "hadoop" / "reducer.py"
INPUT_COLUMNS = [
    "striker_id",
    "batter_runs",
    "is_batter_ball_faced",
    "is_four",
    "is_six",
    "is_batting_pressure",
    "pressure_batter_ball",
    "bowler_id",
    "bowler_conceded_runs",
    "is_legal_ball",
    "pressure_bowler_ball",
    "is_bowler_wicket",
    "is_dot_ball",
    "has_boundary_flag",
    "is_bowling_pressure",
]


def _run_mapper(frame):
    mapper_input = frame.to_json(orient="records", lines=True)
    mapped = subprocess.run(
        [sys.executable, str(MAPPER)],
        input=mapper_input,
        text=True,
        capture_output=True,
        check=True,
    )
    sorted_output = "\n".join(sorted(mapped.stdout.splitlines())) + "\n"
    reduced = subprocess.run(
        [sys.executable, str(REDUCER)],
        input=sorted_output,
        text=True,
        capture_output=True,
        check=True,
    )
    result = {}
    for line in reduced.stdout.splitlines():
        key, values = line.split("\t", 1)
        result[key] = json.loads(values)
    return len(mapped.stdout.splitlines()), result


def _pandas_oracle(frame):
    output = {}
    for role, entity, scope_flag, ball_flag in [
        ("batter", "striker_id", "is_batting_pressure", "is_batter_ball_faced"),
        ("bowler", "bowler_id", "is_bowling_pressure", "is_legal_ball"),
    ]:
        for scope in ("all", "pressure"):
            selected = frame
            if scope == "pressure":
                selected = frame.loc[frame[scope_flag]]
            if role == "batter":
                grouped = selected.groupby(entity, dropna=True).agg(
                    runs=("batter_runs", "sum"),
                    balls=(ball_flag, "sum"),
                    fours=("is_four", "sum"),
                    sixes=("is_six", "sum"),
                )
            else:
                grouped = selected.groupby(entity, dropna=True).agg(
                    runs_conceded=("bowler_conceded_runs", "sum"),
                    legal_balls=(ball_flag, "sum"),
                    wickets=("is_bowler_wicket", "sum"),
                    dots=("is_dot_ball", "sum"),
                    boundaries=("has_boundary_flag", "sum"),
                )
            for player_id, row in grouped.iterrows():
                values = {key: float(value) for key, value in row.items()}
                output[f"{role}:{scope}:{int(player_id)}"] = values
    return output


def run_local_mapreduce(input_path=INPUT, report_path=REPORT, output_path=OUTPUT):
    frame = pd.read_parquet(input_path, columns=INPUT_COLUMNS)
    started = time.perf_counter()
    mapped_records, mapreduce = _run_mapper(frame)
    mapreduce_seconds = time.perf_counter() - started
    oracle = _pandas_oracle(frame)
    missing = sorted(set(oracle) - set(mapreduce))
    unexpected = sorted(set(mapreduce) - set(oracle))
    mismatches = []
    for key in sorted(set(oracle) & set(mapreduce)):
        for field, expected in oracle[key].items():
            actual = mapreduce[key].get(field, 0.0)
            if abs(float(actual) - float(expected)) > 1e-8:
                mismatches.append(
                    {
                        "key": key,
                        "field": field,
                        "mapreduce": actual,
                        "pandas": expected,
                    }
                )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for key, values in mapreduce.items():
        role, scope, player_id = key.split(":")
        records.append({"role": role, "scope": scope, "player_id": int(player_id), **values})
    pd.DataFrame(records).sort_values(["role", "scope", "player_id"]).to_csv(
        output_path, index=False
    )

    report = {
        "execution_mode": "local Python subprocess mapper/shuffle/reducer; not Hadoop or HDFS",
        "input": str(Path(input_path).relative_to(ROOT)),
        "input_rows": int(len(frame)),
        "mapped_records": int(mapped_records),
        "aggregates": len(mapreduce),
        "pandas_aggregates": len(oracle),
        "missing_keys": missing,
        "unexpected_keys": unexpected,
        "mismatches": mismatches[:100],
        "mismatch_count": len(mismatches),
        "parity": not missing and not unexpected and not mismatches,
        "local_mapreduce_seconds": mapreduce_seconds,
        "output": str(output_path.relative_to(ROOT)),
        "hadoop_cluster_executed": False,
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["parity"]:
        raise AssertionError(f"MapReduce/Pandas parity failed: {report}")
    print(
        f"Local Streaming-compatible MapReduce parity passed: "
        f"{len(mapreduce)} aggregates from {len(frame)} deliveries."
    )
    return report


if __name__ == "__main__":
    run_local_mapreduce()
