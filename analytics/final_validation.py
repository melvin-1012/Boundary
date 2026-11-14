"""Independently audit raw cricket calculations and preserve source provenance."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.cricket_metrics import BOWLER_CREDITED_DISMISSALS, NON_BOWLER_RUN_EXTRAS
from ingestion.data_validation import EXPECTED_COLUMNS, select_hackathon_matches


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CURATED = ROOT / "data" / "curated"
REPORTS = ROOT / "reports"
QUALITY_REPORT = REPORTS / "data_quality_report.json"
OUTPUT = REPORTS / "final_validation.json"
ANALYSIS_START = pd.Timestamp("2022-01-01")
NON_LEGAL_EXTRAS = {"wide", "Overstep"}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        content = source.read().replace(b"\r\n", b"\n")
        digest.update(content)
    return digest.hexdigest()


def _bool_series(series):
    return series.fillna(False).astype(bool)


def _compare_to_curated(raw, curated, raw_fields):
    keys = ["match_id", "innings", "innings_ball_num"]
    merged = raw[keys + list(raw_fields)].merge(
        curated[keys + list(raw_fields)],
        on=keys,
        how="outer",
        suffixes=("_raw_independent", "_curated"),
        indicator=True,
        validate="one_to_one",
    )
    results = {}
    for field in raw_fields:
        left = merged[f"{field}_raw_independent"]
        right = merged[f"{field}_curated"]
        if pd.api.types.is_numeric_dtype(left) or pd.api.types.is_numeric_dtype(right):
            equal = np.isclose(
                pd.to_numeric(left, errors="coerce"),
                pd.to_numeric(right, errors="coerce"),
                equal_nan=True,
            )
        else:
            equal = left.eq(right) | (left.isna() & right.isna())
        mismatches = merged.loc[~equal, keys].head(5).to_dict("records")
        results[field] = {
            "matched_rows": int(len(merged) - (merged["_merge"] != "both").sum()),
            "mismatch_rows": int((~equal).sum()),
            "examples": mismatches,
        }
    results["raw_only_rows"] = int(merged["_merge"].eq("left_only").sum())
    results["curated_only_rows"] = int(merged["_merge"].eq("right_only").sum())
    return results


def run_final_validation(raw_dir=RAW, curated_dir=CURATED, report_path=OUTPUT):
    raw_dir, curated_dir, report_path = map(Path, (raw_dir, curated_dir, report_path))
    frames = {
        filename: pd.read_csv(raw_dir / filename, low_memory=False)
        for filename in EXPECTED_COLUMNS
    }
    matches = frames["matches.csv"]
    competitions = frames["competitions.csv"]
    scoped_matches = select_hackathon_matches(matches, competitions)
    match_ids = set(scoped_matches["match_id"])
    balls = frames["ball_by_ball.csv"].loc[
        frames["ball_by_ball.csv"]["match_id"].isin(match_ids)
    ].copy().reset_index(drop=True)

    extras = balls["extras_type"].fillna("").astype(str)
    runs = pd.to_numeric(balls["runs"], errors="coerce").fillna(0)
    extra1 = pd.to_numeric(balls["extras1_runs"], errors="coerce").fillna(0)
    extra2 = pd.to_numeric(balls["extras_2_runs"], errors="coerce").fillna(0)
    team_runs = runs + extra1 + extra2
    legal = ~extras.isin(NON_LEGAL_EXTRAS)
    non_bowler_runs = extras.isin(NON_BOWLER_RUN_EXTRAS)
    bowler_runs = team_runs - (extra1 + extra2).where(non_bowler_runs, 0)
    bowler_wickets = (
        _bool_series(balls["is_wicket"])
        & balls["dismissal_type"].isin(BOWLER_CREDITED_DISMISSALS)
    )
    four_flag = _bool_series(balls["is_four"])
    six_flag = _bool_series(balls["is_six"])

    independent = balls[
        ["match_id", "innings", "innings_ball_num"]
    ].copy()
    independent["team_runs"] = team_runs
    independent["batter_runs"] = runs
    independent["is_legal_ball"] = legal
    independent["bowler_conceded_runs"] = bowler_runs
    independent["is_bowler_wicket"] = bowler_wickets
    independent["has_boundary_flag"] = four_flag | six_flag
    innings_runs = (
        balls.assign(_team_runs=team_runs)
        .groupby(["match_id", "innings"], as_index=False)["_team_runs"]
        .sum()
    )
    target_source = innings_runs.loc[
        innings_runs["innings"].isin([1, 3])
    ].copy()
    target_source["target_innings"] = target_source["innings"] + 1
    target_source = target_source.rename(
        columns={"_team_runs": "preceding_innings_runs"}
    )[["match_id", "target_innings", "preceding_innings_runs"]]
    target_rows = balls[["match_id", "innings"]].merge(
        target_source,
        left_on=["match_id", "innings"],
        right_on=["match_id", "target_innings"],
        how="left",
        validate="many_to_one",
    )
    target_rows = target_rows.merge(
        matches[["match_id", "revised_target"]],
        on="match_id",
        how="left",
        validate="many_to_one",
    )
    independent["target"] = (
        target_rows["preceding_innings_runs"] + 1
    ).where(target_rows["innings"].isin([2, 4]))
    independent.loc[
        target_rows["innings"].eq(2) & target_rows["revised_target"].notna(),
        "target",
    ] = target_rows.loc[
        target_rows["innings"].eq(2) & target_rows["revised_target"].notna(),
        "revised_target",
    ].to_numpy()
    curated = pd.read_parquet(
        curated_dir / "pressure_deliveries.parquet",
        columns=[
            "match_id",
            "innings",
            "innings_ball_num",
            "team_runs",
            "batter_runs",
            "is_legal_ball",
            "bowler_conceded_runs",
            "is_bowler_wicket",
            "has_boundary_flag",
            "target",
        ],
    )
    curated = curated.loc[curated["match_id"].isin(match_ids)]
    independent_comparison = _compare_to_curated(
        independent, curated, independent.columns.difference(
            ["match_id", "innings", "innings_ball_num"]
        ).tolist()
    )

    extras_summary = []
    for kind, group in balls.assign(
        _type=extras.replace("", "(none)"),
        _team_runs=team_runs,
        _batter_runs=runs,
        _legal=legal,
        _bowler_runs=bowler_runs,
    ).groupby("_type", dropna=False):
        extras_summary.append(
            {
                "extras_type": str(kind),
                "deliveries": int(len(group)),
                "team_runs": int(group["_team_runs"].sum()),
                "source_runs": int(group["_batter_runs"].sum()),
                "extras1_runs": int(pd.to_numeric(group["extras1_runs"], errors="coerce").fillna(0).sum()),
                "extras_2_runs": int(pd.to_numeric(group["extras_2_runs"], errors="coerce").fillna(0).sum()),
                "legal_deliveries_under_current_rule": int(group["_legal"].sum()),
                "bowler_conceded_runs_under_current_rule": int(group["_bowler_runs"].sum()),
            }
        )

    mismatch_four = balls.loc[
        four_flag.ne(runs.eq(4)),
        ["match_id", "innings", "innings_ball_num", "runs", "is_four", "extras_type"],
    ].head(10)
    mismatch_six = balls.loc[
        six_flag.ne(runs.eq(6)),
        ["match_id", "innings", "innings_ball_num", "runs", "is_six", "extras_type"],
    ].head(10)

    source_out = balls.loc[
        balls["dismissed_player_id"].notna()
        & balls["dismissed_player_id"].eq(balls["striker_id"]),
        ["match_id", "innings", "striker_id"],
    ].drop_duplicates()
    appearances = balls[["match_id", "innings", "striker_id"]].drop_duplicates()
    not_out_approx = int(
        (appearances.merge(source_out.drop_duplicates(), how="left", indicator=True)
         ["_merge"].eq("left_only")).sum()
    )

    innings_summary = (
        balls.assign(_legal=legal, _team_runs=team_runs)
        .groupby(["match_id", "innings"], as_index=False)
        .agg(
            deliveries=("innings_ball_num", "size"),
            legal_balls=("_legal", "sum"),
            team_runs=("_team_runs", "sum"),
            max_overid=("overid", "max"),
            max_over_ball_num=("over_ball_num", "max"),
        )
    )
    over_ball_num = pd.to_numeric(balls["over_ball_num"], errors="coerce")
    over_ball_anomaly = balls.loc[
        over_ball_num.gt(6),
        ["match_id", "innings", "overid", "over_ball_num", "innings_ball_num"],
    ].head(10)
    super_over = innings_summary[innings_summary["innings"].isin([3, 4])]
    first_super = innings_runs.loc[
        innings_runs["innings"].eq(3), ["match_id", "_team_runs"]
    ].rename(columns={"_team_runs": "innings3_runs"})
    chase_super = (
        independent.loc[independent["innings"].eq(4), ["match_id", "innings", "target"]]
        .merge(first_super, on="match_id", how="left", validate="many_to_one")
    )
    super_target_mismatch_count = int(
        chase_super["target"].ne(chase_super["innings3_runs"] + 1).sum()
    )
    revised_matches = matches.loc[
        matches["match_id"].isin(match_ids) & matches["revised_target"].notna()
    ]
    chase_rows = balls.loc[balls["innings"].eq(2), ["match_id"]].drop_duplicates()
    revised_target_chases = int(
        revised_matches["match_id"].isin(chase_rows["match_id"]).sum()
    )

    dismissals = (
        balls.loc[_bool_series(balls["is_wicket"])]
        ["dismissal_type"].fillna("(missing)").value_counts()
    )
    wicket_counts = {
        str(kind): int(count) for kind, count in dismissals.items()
    }
    scoped_ipl = scoped_matches.loc[scoped_matches["match_format"].eq("T20")]
    scoped_t20i = scoped_matches.loc[scoped_matches["match_format"].eq("T20I")]

    quality = json.loads((ROOT / "reports" / "data_quality_report.json").read_text())
    current_hashes = {
        filename: _sha256(raw_dir / filename) for filename in sorted(EXPECTED_COLUMNS)
    }
    recorded_hashes = quality["etl"]["input_sha256"]
    hash_matches = current_hashes == recorded_hashes

    result = {
        "status": "calculation_mismatches",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "methodology_version": "pressure-spi-v1-provisional",
        "raw_data_modified": False,
        "scope": {
            "start_date": ANALYSIS_START.date().isoformat(),
            "selected_matches": int(len(scoped_matches)),
            "selected_deliveries": int(len(balls)),
            "ipl_matches": int(len(scoped_ipl)),
            "t20i_matches": int(len(scoped_t20i)),
            "ipl_competitions": sorted(scoped_ipl["comp_name"].dropna().unique().tolist()),
            "t20i_competitions": sorted(scoped_t20i["comp_name"].dropna().unique().tolist()),
        },
        "raw_input_sha256": current_hashes,
        "raw_hashes_match_etl_manifest": bool(hash_matches),
        "independent_raw_to_curated_comparison": independent_comparison,
        "run_and_extras": {
            "source_runs_sum": int(runs.sum()),
            "team_runs_sum": int(team_runs.sum()),
            "difference_from_extras_sum": int((extra1 + extra2).sum()),
            "nonzero_source_runs_on_byes_legbyes_or_penalty": int(
                (runs.ne(0) & extras.isin(NON_BOWLER_RUN_EXTRAS)).sum()
            ),
            "records_with_extras_runs_but_no_extras_type": int(
                ((extra1 + extra2).ne(0) & extras.eq("")).sum()
            ),
            "by_extras_type": extras_summary,
        },
        "delivery_rules": {
            "legal_deliveries_under_current_rule": int(legal.sum()),
            "excluded_wides_and_oversteps": int((~legal).sum()),
            "bowler_conceded_runs_sum_under_current_rule": int(bowler_runs.sum()),
            "bowler_conceded_runs_formula": "team runs excluding byes, legbyes, and Penalty extras",
            "unknown_other_extra_deliveries": int(extras.eq("other").sum()),
        },
        "wickets": {
            "dismissal_counts": wicket_counts,
            "bowler_credited_count_under_current_policy": int(bowler_wickets.sum()),
            "run_out_count_not_credited": int(
                dismissals.get("RunOut", 0)
            ),
            "policy": "Bowled, Caught, LBW, Stump, Hit Wicket",
        },
        "boundaries": {
            "four_flag_mismatches_against_source_runs_equals_4": int(
                four_flag.ne(runs.eq(4)).sum()
            ),
            "six_flag_mismatches_against_source_runs_equals_6": int(
                six_flag.ne(runs.eq(6)).sum()
            ),
            "four_examples": mismatch_four.astype(object).where(pd.notna(mismatch_four), None).to_dict("records"),
            "six_examples": mismatch_six.astype(object).where(pd.notna(mismatch_six), None).to_dict("records"),
        },
        "innings_and_not_outs": {
            "innings_count": int(len(innings_summary)),
            "innings_3_4_rows": int(len(super_over)),
            "innings_3_4_legal_balls_min_max": [
                int(super_over["legal_balls"].min()) if not super_over.empty else 0,
                int(super_over["legal_balls"].max()) if not super_over.empty else 0,
            ],
            "innings_3_4_observed_over_ball_num_max": int(
                super_over["max_over_ball_num"].max()
            ) if not super_over.empty else None,
            "over_ball_num_above_six_rows": int(over_ball_num.gt(6).sum()),
            "over_ball_num_above_six_examples": over_ball_anomaly.to_dict("records"),
            "approximate_striker_appearances": int(len(appearances)),
            "approximate_striker_outs": int(len(source_out)),
            "approximate_striker_not_out_appearances": not_out_approx,
            "not_out_limitation": "Only recorded striker appearances and dismissed_player_id are compared; non-striker-only participation and official innings scorecards are unavailable.",
            "innings3_to_innings4_chase_rows": int(len(chase_super)),
            "innings4_target_mismatch_deliveries": super_target_mismatch_count,
            "innings4_target_matches_preceding_super_over_plus_one": super_target_mismatch_count == 0,
            "super_over_target_reconstruction": "Innings 4 target is independently reconstructed as innings 3 total plus one and compared with the curated state.",
            "revised_target_matches_with_innings2_chase": revised_target_chases,
            "revised_target_limitation": "Source revised_target semantics and Duckworth-Lewis adjustments are not independently documented.",
            "innings3_4_legal_ball_totals": [
                int(value) for value in super_over["legal_balls"].tolist()
            ],
            "innings3_4_match_ids": [
                int(value) for value in super_over["match_id"].tolist()[:20]
            ],
        },
        "limitations": [
            "No official Round 1 problem statement or independent scorecard oracle exists in the workspace.",
            "Source definitions for runs, other extras, boundary flags, revised targets, and innings numbering are not authoritative.",
            "A one-over super-over interpretation is used for innings 3 and 4; source convention requires confirmation.",
            "Not-out counts are approximate striker appearances, not a reconstruction of official batting scorecards.",
            "The validation independently re-derives arithmetic from the raw CSV but uses the same supplied records; it cannot establish that the source itself is correct.",
        ],
    }
    result["validation_checks"] = {
        "raw_hashes_match_etl_manifest": bool(hash_matches),
        "raw_curated_join_has_no_orphan_rows": (
            independent_comparison["raw_only_rows"] == 0
            and independent_comparison["curated_only_rows"] == 0
        ),
        "independently_recomputed_columns_match_curated": all(
            detail["mismatch_rows"] == 0 for detail in independent_comparison.values()
            if isinstance(detail, dict) and "mismatch_rows" in detail
        ),
    }
    if all(result["validation_checks"].values()):
        result["status"] = "validated_with_source_limitations"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n")
    return result


def main():
    result = run_final_validation()
    print(
        "Final validation: "
        f"{result['scope']['selected_matches']} matches, "
        f"{result['scope']['selected_deliveries']} deliveries; "
        f"raw hashes match={result['raw_hashes_match_etl_manifest']}"
    )
    print(f"Report: {OUTPUT}")


if __name__ == "__main__":
    main()
