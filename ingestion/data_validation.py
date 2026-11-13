"""Read-only validation and scope selection for the raw cricket CSV archive."""

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "raw"
DEFAULT_REPORT = ROOT / "reports" / "validation" / "data_validation_report.json"

EXPECTED_COLUMNS = {
    "ball_by_ball.csv": [
        "match_id", "innings", "overid", "over_ball_num", "innings_ball_num",
        "batting_team_id", "bowling_team_id", "striker_id", "striker_name",
        "non_striker_id", "non_striker_name", "bowler_id", "bowler_name",
        "batting_type", "bowling_type", "batting_order", "runs", "is_four",
        "is_six", "is_wicket", "dismissal_type_id", "dismissal_type",
        "dismissed_player_id", "extras_type", "extras1_runs", "extras_2_runs",
        "pace_or_spin", "bowl_speed", "stroke", "delivery_style",
        "over_or_around", "on_or_off", "delivery_ist_time",
    ],
    "matches.csv": [
        "match_id", "comp_id", "match_number", "match_date", "stage",
        "venue_id", "venue_country", "home_team_id", "home_team", "away_team_id",
        "away_team", "home_team_captain_id", "away_team_captain_id",
        "toss_win_team_id", "toss_opted", "man_of_the_match",
        "first_inn_revised_overs", "second_inn_revised_overs", "revised_target",
        "knock_out", "win_team_id", "result",
    ],
    "competitions.csv": ["comp_id", "comp_name", "match_format", "season"],
    "teams.csv": ["comp_id", "team_id", "team_name"],
    "playing_eleven.csv": [
        "match_id", "team_id", "player_id", "batting_order", "is_played",
        "is_captain", "is_wk", "is_impact", "is_impact_off",
    ],
    "competition_team_player_mapping.csv": [
        "comp_id", "comp_name", "team_id", "team_name", "player_id", "player_name",
    ],
}

KEY_COLUMNS = {
    "ball_by_ball.csv": ["match_id", "innings", "innings_ball_num"],
    "matches.csv": ["match_id"],
    "competitions.csv": ["comp_id"],
    "teams.csv": ["comp_id", "team_id"],
    "playing_eleven.csv": ["match_id", "team_id", "player_id"],
    "competition_team_player_mapping.csv": ["comp_id", "team_id", "player_id"],
}

REQUIRED_KEY_COLUMNS = {
    "ball_by_ball.csv": ["match_id", "innings", "innings_ball_num"],
    "matches.csv": ["match_id", "comp_id"],
    "competitions.csv": ["comp_id", "match_format"],
    "teams.csv": ["comp_id", "team_id"],
    "playing_eleven.csv": ["match_id", "team_id", "player_id"],
    "competition_team_player_mapping.csv": ["comp_id", "team_id", "player_id"],
}

IPL_COMPETITIONS = {
    1358: "IPL 2022",
    1715: "IPL 2023",
    2193: "IPL 2024",
    2725: "IPL 2025",
    3298: "IPL 2026",
}
IPL_COMPETITION_IDS = set(IPL_COMPETITIONS)
IPL_COMPETITION_NAMES = set(IPL_COMPETITIONS.values())
ANALYSIS_START = pd.Timestamp("2022-01-01")
def _check(checks, name, passed, detail, warning=False):
    status = "pass" if passed else ("warning" if warning else "fail")
    checks.append({"name": name, "status": status, "detail": detail})


def key_profile(frame, columns):
    key = frame[columns]
    null_rows = int(key.isna().any(axis=1).sum())
    duplicate_rows = int(key.duplicated(keep=False).sum())
    return {
        "columns": columns,
        "null_rows": null_rows,
        "duplicate_rows": duplicate_rows,
    }


def select_hackathon_matches(matches, competitions):
    """Select exact IPL seasons and post-2022 T20Is using competition metadata."""
    joined = matches.merge(
        competitions[["comp_id", "comp_name", "match_format"]],
        on="comp_id",
        how="left",
        validate="many_to_one",
    )
    dates = pd.to_datetime(joined["match_date"], errors="coerce")
    ipl = (
        joined["comp_id"].isin(IPL_COMPETITION_IDS)
        & joined["comp_name"].eq(joined["comp_id"].map(IPL_COMPETITIONS))
        & joined["match_format"].eq("T20")
    )
    t20i = joined["match_format"].eq("T20I")
    return joined.loc[dates.ge(ANALYSIS_START) & (ipl | t20i)].copy()


def _unmapped_count(source, target, source_columns, target_columns):
    left = source[source_columns].dropna().drop_duplicates()
    right = target[target_columns].dropna().drop_duplicates()
    left.columns = [f"key_{i}" for i in range(len(source_columns))]
    right.columns = left.columns
    return int(left.merge(right, on=list(left.columns), how="left", indicator=True)
               .loc[lambda rows: rows["_merge"].eq("left_only")].shape[0])


def _dataset_profile(name, frame):
    key_columns = KEY_COLUMNS[name]
    available_key_columns = [column for column in key_columns if column in frame.columns]
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "column_names": list(frame.columns),
        "full_duplicate_rows": int(frame.duplicated().sum()),
        "missing_cells": int(frame.isna().sum().sum()),
        "missing_by_column": {
            column: int(count)
            for column, count in frame.isna().sum().items()
            if count
        },
        "candidate_key": (
            key_profile(frame, available_key_columns)
            if len(available_key_columns) == len(key_columns)
            else {
                "columns": key_columns,
                "null_rows": None,
                "duplicate_rows": None,
                "missing_columns": sorted(set(key_columns) - set(available_key_columns)),
            }
        ),
    }


def audit_frames(frames):
    """Inspect loaded source frames and return evidence without modifying them."""
    checks = []
    profiles = {}
    for name, required in EXPECTED_COLUMNS.items():
        if name not in frames:
            _check(checks, f"{name}: present", False, "Required source file is missing.")
            continue
        frame = frames[name]
        missing_columns = sorted(set(required) - set(frame.columns))
        _check(
            checks,
            f"{name}: schema",
            not missing_columns,
            "All expected columns are present."
            if not missing_columns
            else f"Missing columns: {missing_columns}",
        )
        profiles[name] = _dataset_profile(name, frame)
        candidate_key = profiles[name]["candidate_key"]
        null_keys = candidate_key["null_rows"]
        duplicate_keys = candidate_key["duplicate_rows"]
        _check(
            checks,
            f"{name}: candidate key",
            null_keys == 0 and duplicate_keys == 0
            if null_keys is not None and duplicate_keys is not None
            else False,
            (
                f"Null-key rows: {null_keys}; duplicate-key rows: {duplicate_keys}."
                if null_keys is not None and duplicate_keys is not None
                else f"Cannot assess; missing key columns: {candidate_key['missing_columns']}."
            ),
            warning=name == "playing_eleven.csv"
            and null_keys is not None
            and duplicate_keys is not None
            and (null_keys > 0 or duplicate_keys > 0),
        )
        required_columns = REQUIRED_KEY_COLUMNS[name]
        if not set(required_columns).issubset(frame.columns):
            required_nulls = None
            required_detail = (
                "Cannot assess; missing required identifier columns: "
                f"{sorted(set(required_columns) - set(frame.columns))}."
            )
        else:
            required_nulls = int(frame[required_columns].isna().any(axis=1).sum())
            required_detail = f"Rows missing a required identifier: {required_nulls}."
        _check(
            checks,
            f"{name}: required identifiers",
            required_nulls == 0 if required_nulls is not None else False,
            required_detail,
        )
        if not missing_columns:
            numeric_columns = [
                column
                for column in required
                if column.endswith("_id")
                or column in {
                    "innings",
                    "overid",
                    "over_ball_num",
                    "innings_ball_num",
                    "runs",
                    "extras1_runs",
                    "extras_2_runs",
                    "comp_id",
                    "team_id",
                    "player_id",
                }
            ]
            invalid_types = [
                column
                for column in numeric_columns
                if not pd.api.types.is_numeric_dtype(frame[column])
            ]
            _check(
                checks,
                f"{name}: numeric identifier/metric types",
                not invalid_types,
                "Numeric identifiers and measures have numeric dtypes."
                if not invalid_types
                else f"Columns with non-numeric dtypes: {invalid_types}.",
            )

    if any(
        name not in frames
        or not set(columns).issubset(frames[name].columns)
        for name, columns in EXPECTED_COLUMNS.items()
    ):
        return _finish(checks, profiles, {})

    matches = frames["matches.csv"]
    competitions = frames["competitions.csv"]
    balls = frames["ball_by_ball.csv"]
    teams = frames["teams.csv"]
    playing_eleven = frames["playing_eleven.csv"]
    roster = frames["competition_team_player_mapping.csv"]

    references = [
        ("ball deliveries -> matches", balls, matches, ["match_id"], ["match_id"]),
        ("matches -> competitions", matches, competitions, ["comp_id"], ["comp_id"]),
        ("teams -> competitions", teams, competitions, ["comp_id"], ["comp_id"]),
        ("player mapping -> competitions", roster, competitions, ["comp_id"], ["comp_id"]),
        ("playing eleven -> matches", playing_eleven, matches, ["match_id"], ["match_id"]),
    ]
    for name, source, target, source_key, target_key in references:
        missing = _unmapped_count(source, target, source_key, target_key)
        _check(checks, name, missing == 0, f"Unmapped distinct key values: {missing}.")

    match_competitions = matches[["match_id", "comp_id"]]
    ball_competitions = balls.merge(
        match_competitions, on="match_id", how="left", validate="many_to_one"
    )
    team_keys = teams[["comp_id", "team_id"]]
    player_keys = roster[["comp_id", "player_id"]]
    scoped_team_orphans = sum(
        _unmapped_count(
            ball_competitions[["comp_id", team_column]],
            team_keys,
            ["comp_id", team_column],
            ["comp_id", "team_id"],
        )
        for team_column in ("batting_team_id", "bowling_team_id")
    )
    _check(
        checks,
        "delivery teams -> competition team mapping",
        scoped_team_orphans == 0,
        f"Unmapped competition/team pairs across batting and bowling teams: {scoped_team_orphans}.",
    )
    scoped_player_orphans = sum(
        _unmapped_count(
            ball_competitions[["comp_id", player_column]].dropna(),
            player_keys,
            ["comp_id", player_column],
            ["comp_id", "player_id"],
        )
        for player_column in ("striker_id", "bowler_id")
    )
    _check(
        checks,
        "delivery players -> competition player mapping",
        scoped_player_orphans == 0,
        f"Unmapped competition/player pairs across striker and bowler: {scoped_player_orphans}.",
    )

    represented_matches = set(balls["match_id"].dropna())
    match_ids = set(matches["match_id"].dropna())
    missing_delivery_count = len(match_ids - represented_matches)
    _check(
        checks,
        "matches with ball-by-ball coverage",
        missing_delivery_count == 0,
        f"Matches without deliveries: {missing_delivery_count}.",
        warning=missing_delivery_count > 0,
    )
    missing_matches = matches.loc[~matches["match_id"].isin(represented_matches)]
    missing_results = (
        missing_matches["result"].fillna("(missing result)").value_counts().to_dict()
    )

    ball_keys = KEY_COLUMNS["ball_by_ball.csv"]
    key_duplicates = int(balls[ball_keys].duplicated().sum())
    _check(
        checks,
        "delivery sequence key",
        key_duplicates == 0,
        f"Duplicate (match_id, innings, innings_ball_num) rows: {key_duplicates}.",
    )
    ordered = balls.sort_values(ball_keys)
    sequence_gaps = int(
        ordered.groupby(["match_id", "innings"])["innings_ball_num"]
        .diff()
        .dropna()
        .ne(1)
        .sum()
    )
    _check(
        checks,
        "innings delivery sequence",
        sequence_gaps == 0,
        f"Non-unit gaps in innings_ball_num: {sequence_gaps}.",
    )

    over_ball_gt_six = int(balls["over_ball_num"].gt(6).sum())
    extras = balls["extras_type"].fillna("(not recorded)").value_counts(dropna=False)
    _check(
        checks,
        "ball-count interpretation",
        over_ball_gt_six == 0,
        f"{over_ball_gt_six} rows have over_ball_num > 6; over_ball_num is not a legal-ball counter.",
        warning=over_ball_gt_six > 0,
    )
    negative_runs = int((balls[["runs", "extras1_runs", "extras_2_runs"]] < 0).any(axis=1).sum())
    _check(
        checks,
        "non-negative run fields",
        negative_runs == 0,
        f"Rows containing a negative run/extras value: {negative_runs}.",
    )
    invalid_innings = int(
        (balls["innings"].isna() | balls["innings"].lt(1)).sum()
    )
    _check(
        checks,
        "positive innings identifiers",
        invalid_innings == 0,
        f"Rows with missing or non-positive innings identifiers: {invalid_innings}.",
    )

    four_mismatches = int(balls["is_four"].ne(balls["runs"].eq(4)).sum())
    six_mismatches = int(balls["is_six"].ne(balls["runs"].eq(6)).sum())
    _check(
        checks,
        "boundary flags versus batter runs",
        four_mismatches == 0 and six_mismatches == 0,
        f"is_four/runs mismatches: {four_mismatches}; is_six/runs mismatches: {six_mismatches}. "
        "Do not replace supplied event flags without investigating their semantics.",
        warning=four_mismatches > 0 or six_mismatches > 0,
    )
    ambiguous_batter_runs = int(
        balls["extras_type"].isin(["byes", "legbyes", "Penalty"])
        .where(balls["runs"].ne(0), False)
        .sum()
    )
    _check(
        checks,
        "runs field on non-batter extras",
        ambiguous_batter_runs == 0,
        f"Byes/legbyes/penalty rows with non-zero source runs: {ambiguous_batter_runs}; "
        "the source runs field is retained and these rows need semantic review.",
        warning=ambiguous_batter_runs > 0,
    )

    wicket_without_type = int((balls["is_wicket"] & balls["dismissal_type"].isna()).sum())
    type_without_wicket = int((~balls["is_wicket"] & balls["dismissal_type"].notna()).sum())
    _check(
        checks,
        "wicket flag and dismissal type",
        wicket_without_type == 0 and type_without_wicket == 0,
        f"Wicket flags without type: {wicket_without_type}; types without wicket flag: {type_without_wicket}.",
    )

    comp_formats = set(competitions["match_format"].dropna().astype(str))
    _check(
        checks,
        "competition format values",
        comp_formats <= {"T20", "T20I"},
        f"Observed formats: {sorted(comp_formats)}.",
    )
    t20_competitions = competitions.loc[
        competitions["match_format"].eq("T20"), ["comp_id", "comp_name", "season"]
    ].sort_values(["season", "comp_id"])
    observed_ipl = competitions.loc[
        competitions["comp_id"].isin(IPL_COMPETITION_IDS),
        ["comp_id", "comp_name", "match_format"],
    ]
    recognized_ipl = {
        int(row.comp_id): row.comp_name for row in observed_ipl.itertuples()
    }
    _check(
        checks,
        "IPL competition IDs and metadata",
        recognized_ipl == IPL_COMPETITIONS
        and observed_ipl["match_format"].eq("T20").all(),
        f"Observed IPL ID/name mapping: {recognized_ipl}; "
        f"other T20 competitions kept separate: "
        f"{sorted(set(t20_competitions['comp_name']) - IPL_COMPETITION_NAMES)}.",
    )

    scoped_matches = select_hackathon_matches(matches, competitions)
    scoped_ipl = scoped_matches["comp_name"].isin(IPL_COMPETITION_NAMES)
    scoped_t20i = scoped_matches["match_format"].eq("T20I")
    date_values = pd.to_datetime(scoped_matches["match_date"], errors="coerce")
    _check(
        checks,
        "hackathon analysis scope",
        bool(date_values.ge(ANALYSIS_START).all())
        and bool((scoped_ipl | scoped_t20i).all()),
        f"Selected matches: {len(scoped_matches)}; IPL: {int(scoped_ipl.sum())}; "
        f"T20I: {int(scoped_t20i.sum())}; date range: "
        f"{date_values.min().date() if len(date_values) else 'n/a'} to "
        f"{date_values.max().date() if len(date_values) else 'n/a'}.",
    )

    anomalies = {
        "matches_without_deliveries": missing_delivery_count,
        "matches_without_deliveries_by_result": {
            str(key): int(value) for key, value in missing_results.items()
        },
        "playing_eleven_duplicate_candidate_key_rows": profiles["playing_eleven.csv"][
            "candidate_key"
        ]["duplicate_rows"],
        "playing_eleven_repeated_player_groups": int(
            playing_eleven.groupby(
                ["match_id", "team_id", "player_id"], dropna=False
            )
            .size()
            .gt(1)
            .sum()
        ),
        "playing_eleven_repeated_keys_with_multiple_batting_orders": int(
            playing_eleven.groupby(
                ["match_id", "team_id", "player_id"], dropna=False
            )["batting_order"]
            .nunique(dropna=True)
            .gt(1)
            .sum()
        ),
        "innings_ball_num_sequence_gaps": sequence_gaps,
        "over_ball_num_greater_than_six": over_ball_gt_six,
        "four_flag_vs_runs_mismatches": four_mismatches,
        "six_flag_vs_runs_mismatches": six_mismatches,
        "nonzero_runs_on_non_batter_extras": ambiguous_batter_runs,
        "negative_run_rows": negative_runs,
        "invalid_innings_rows": invalid_innings,
        "observed_innings_values": sorted(
            int(value) for value in balls["innings"].dropna().unique()
        ),
        "wicket_flag_without_dismissal_type": wicket_without_type,
        "dismissal_type_without_wicket_flag": type_without_wicket,
        "extras_type_counts": {str(key): int(value) for key, value in extras.items()},
        "dismissal_type_counts": {
            str(key): int(value)
            for key, value in balls["dismissal_type"].value_counts(dropna=False).items()
        },
    }
    return _finish(checks, profiles, anomalies, scoped_matches)


def _finish(checks, profiles, anomalies, scoped_matches=None):
    failures = sum(check["status"] == "fail" for check in checks)
    warnings = sum(check["status"] == "warning" for check in checks)
    scope_summary = {}
    if scoped_matches is not None:
        scope_summary = {
            "selected_matches": int(len(scoped_matches)),
            "ipl_matches": int(scoped_matches["comp_name"].isin(IPL_COMPETITION_NAMES).sum()),
            "t20i_matches": int(scoped_matches["match_format"].eq("T20I").sum()),
            "selected_match_ids": sorted(
                int(match_id) for match_id in scoped_matches["match_id"].dropna().unique()
            ),
        }
    return {
        "summary": {
            "status": "fail" if failures else ("warning" if warnings else "pass"),
            "passed_checks": sum(check["status"] == "pass" for check in checks),
            "warnings": warnings,
            "failures": failures,
        },
        "datasets": profiles,
        "analysis_scope": scope_summary,
        "observed_anomalies": anomalies,
        "checks": checks,
        "raw_data_modified": False,
    }


def validate_data_directory(data_dir=DEFAULT_DATA_DIR):
    data_dir = Path(data_dir)
    frames = {}
    for name in EXPECTED_COLUMNS:
        path = data_dir / name
        if path.exists():
            frames[name] = pd.read_csv(path, low_memory=False)
    return audit_frames(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = validate_data_directory(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "Validation: "
        f"{report['summary']['status']} "
        f"({report['summary']['passed_checks']} passed, "
        f"{report['summary']['warnings']} warnings, "
        f"{report['summary']['failures']} failures)"
    )
    print(f"Report: {args.output}")
    for check in report["checks"]:
        if check["status"] != "pass":
            print(f"{check['status'].upper()}: {check['name']}: {check['detail']}")
    return 1 if report["summary"]["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
