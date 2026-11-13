"""Explicit source-field interpretations used by cricket analytics."""

import numpy as np
import pandas as pd


NON_LEGAL_EXTRAS = {"wide", "Overstep"}
WIDE_EXTRAS = {"wide"}
NON_BOWLER_DISMISSALS = {
    "RunOut",
    "Retire Out",
    "Obstracting the field",
    "Obstructing the field",
}
BOWLER_CREDITED_DISMISSALS = {
    "Bowled",
    "Caught",
    "LBW",
    "Stump",
    "Hit Wicket",
}
NON_BOWLER_RUN_EXTRAS = {"byes", "legbyes", "Penalty"}
PRESSURE_WEIGHTS = {
    "batting": {"run_rate": 0.35, "wickets": 0.25, "time": 0.20, "closeness": 0.20},
    "bowling": {"run_rate": 0.30, "wickets": 0.25, "time": 0.20, "closeness": 0.25},
}
PRESSURE_THRESHOLD = 50.0
PRESSURE_PRIOR_OPPORTUNITIES = 30.0
COMPETITION_BASELINE_PRIOR_BALLS = 30.0


def _bounded_ratio(numerator, denominator):
    numerator = np.asarray(numerator, dtype="float64")
    denominator = np.asarray(denominator, dtype="float64")
    result = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator, dtype="float64"),
        where=np.isfinite(denominator) & (denominator > 0),
    )
    return np.clip(result, 0.0, 1.0)


def _pressure_score(components, weights):
    return 100.0 * sum(components[name] * weights[name] for name in weights)


def apply_pressure_model(deliveries, weights=None, threshold=PRESSURE_THRESHOLD):
    """Apply selected weighted pressure definitions to stored state components."""
    weights = weights or PRESSURE_WEIGHTS
    result = deliveries.copy()
    for role in ("batting", "bowling"):
        role_components = {
            name: result[f"{role}_{name}_component"].to_numpy(dtype="float64")
            for name in PRESSURE_WEIGHTS[role]
        }
        score = _pressure_score(role_components, weights[role])
        result[f"{role}_pressure"] = np.clip(score, 0, 100)
        supported = result["innings"].isin([1, 3]) | (
            result["innings"].isin([2, 4]) & result["target"].notna()
        )
        result.loc[~supported, f"{role}_pressure"] = np.nan
        result[f"is_{role}_pressure"] = result[f"{role}_pressure"].ge(threshold)
    result["pressure_batter_ball"] = (
        result["is_batting_pressure"] & result["is_batter_ball_faced"]
    )
    result["pressure_bowler_ball"] = (
        result["is_bowling_pressure"] & result["is_legal_ball"]
    )
    return result


def reconstruct_match_state(balls, matches, competitions):
    """Create pre-delivery match state and separate batting/bowling pressure."""
    match_columns = [
        "match_id",
        "comp_id",
        "match_date",
        "first_inn_revised_overs",
        "second_inn_revised_overs",
        "revised_target",
    ]
    match_columns.extend(
        column for column in ("result", "win_team_id") if column in matches.columns
    )
    match_metadata = matches[match_columns].copy()
    competition_metadata = competitions[
        ["comp_id", "comp_name", "match_format", "season"]
    ]
    metadata = match_metadata.merge(
        competition_metadata, on="comp_id", how="left", validate="many_to_one"
    )
    delivery = balls.merge(
        metadata, on="match_id", how="left", validate="many_to_one"
    ).copy()
    delivery = delivery.sort_values(
        ["match_id", "innings", "innings_ball_num"], kind="stable"
    ).reset_index(drop=True)

    extras_type = delivery["extras_type"].fillna("").astype(str)
    delivery["team_runs"] = (
        delivery["runs"].fillna(0)
        + delivery["extras1_runs"].fillna(0)
        + delivery["extras_2_runs"].fillna(0)
    )
    delivery["batter_runs"] = delivery["runs"].fillna(0)
    delivery["is_legal_ball"] = ~extras_type.isin(NON_LEGAL_EXTRAS)
    delivery["is_batter_ball_faced"] = ~extras_type.isin(WIDE_EXTRAS)
    delivery["bowler_conceded_runs"] = delivery["team_runs"] - np.where(
        extras_type.isin(NON_BOWLER_RUN_EXTRAS),
        delivery["extras1_runs"].fillna(0) + delivery["extras_2_runs"].fillna(0),
        0,
    )
    delivery["is_bowler_wicket"] = (
        delivery["is_wicket"].fillna(False).astype(bool)
        & delivery["dismissal_type"].isin(BOWLER_CREDITED_DISMISSALS)
    )
    delivery["is_dot_ball"] = delivery["team_runs"].eq(0)
    delivery["has_boundary_flag"] = (
        delivery["is_four"].fillna(False).astype(bool)
        | delivery["is_six"].fillna(False).astype(bool)
    )

    group_columns = ["match_id", "innings"]
    group = delivery.groupby(group_columns, sort=False, observed=True)
    delivery["score_before"] = group["team_runs"].cumsum() - delivery["team_runs"]
    wicket_increment = delivery["is_wicket"].fillna(False).astype("int8")
    delivery["wickets_before"] = (
        wicket_increment.groupby([delivery[column] for column in group_columns], sort=False)
        .cumsum()
        - wicket_increment
    )
    legal_increment = delivery["is_legal_ball"].astype("int8")
    delivery["legal_balls_before"] = (
        legal_increment.groupby([delivery[column] for column in group_columns], sort=False)
        .cumsum()
        - legal_increment
    )

    innings_totals = (
        delivery.groupby(group_columns, as_index=False, observed=True)
        .agg(
            innings_runs=("team_runs", "sum"),
            innings_legal_balls=("is_legal_ball", "sum"),
        )
    )
    target_source = innings_totals.loc[
        innings_totals["innings"].isin([1, 3]), ["match_id", "innings", "innings_runs"]
    ].copy()
    target_source["target_innings"] = target_source["innings"] + 1
    target_source = target_source.rename(
        columns={"innings_runs": "preceding_innings_runs"}
    )[["match_id", "target_innings", "preceding_innings_runs"]]
    delivery = delivery.merge(
        target_source,
        left_on=["match_id", "innings"],
        right_on=["match_id", "target_innings"],
        how="left",
        validate="many_to_one",
    )
    target = delivery["preceding_innings_runs"] + 1
    target = target.where(
        ~delivery["innings"].eq(2) | delivery["revised_target"].isna(),
        delivery["revised_target"],
    )
    delivery["target"] = target.where(delivery["innings"].isin([2, 4]))

    limits = np.where(
        delivery["innings"].eq(1),
        delivery["first_inn_revised_overs"],
        np.where(
            delivery["innings"].eq(2),
            delivery["second_inn_revised_overs"],
            np.where(delivery["innings"].isin([3, 4]), 1.0, np.nan),
        ),
    )
    delivery["innings_overs"] = pd.Series(limits, index=delivery.index).fillna(20.0)
    delivery["innings_balls"] = (delivery["innings_overs"].clip(lower=1) * 6).round()
    delivery["balls_remaining"] = (
        delivery["innings_balls"] - delivery["legal_balls_before"]
    ).clip(lower=0)
    delivery["wickets_remaining"] = (10 - delivery["wickets_before"]).clip(0, 10)
    delivery["innings_progress"] = _bounded_ratio(
        delivery["legal_balls_before"], delivery["innings_balls"]
    )
    delivery["current_run_rate"] = (
        6.0
        * delivery["score_before"]
        / delivery["legal_balls_before"].replace(0, np.nan)
    ).fillna(0.0)
    delivery["runs_required"] = (
        delivery["target"] - delivery["score_before"]
    ).where(delivery["innings"].isin([2, 4]))
    delivery["required_run_rate"] = (
        6.0
        * delivery["runs_required"].clip(lower=0)
        / delivery["balls_remaining"].replace(0, np.nan)
    ).where(delivery["innings"].isin([2, 4]))
    delivery["required_run_rate"] = delivery["required_run_rate"].replace(
        [np.inf, -np.inf], np.nan
    )
    delivery["innings_phase"] = pd.cut(
        delivery["innings_progress"],
        bins=[-0.001, 1 / 3, 0.75, 1.001],
        labels=["powerplay", "middle", "death"],
    ).astype("string")

    complete_first = innings_totals.loc[
        innings_totals["innings"].eq(1) & innings_totals["innings_legal_balls"].gt(0)
    ].copy()
    complete_first = complete_first.merge(
        metadata[["match_id", "match_date", "match_format"]],
        on="match_id",
        how="left",
        validate="many_to_one",
    )
    complete_first["match_date"] = pd.to_datetime(
        complete_first["match_date"], errors="coerce"
    )
    complete_first["innings_run_rate"] = (
        6.0 * complete_first["innings_runs"] / complete_first["innings_legal_balls"]
    )
    complete_first = complete_first.sort_values(
        ["match_date", "match_id"], kind="stable"
    )
    complete_first["prior_reference_run_rate"] = (
        complete_first.groupby("match_format", dropna=False)["innings_run_rate"]
        .transform(lambda rates: rates.shift().expanding(min_periods=5).median())
    )
    format_fallback = {"T20": 8.0, "T20I": 7.5}
    complete_first["prior_reference_run_rate"] = complete_first[
        "prior_reference_run_rate"
    ].fillna(complete_first["match_format"].map(format_fallback))
    reference_by_match = complete_first.set_index("match_id")[
        "prior_reference_run_rate"
    ]
    delivery["reference_run_rate"] = delivery["match_id"].map(reference_by_match)
    delivery["reference_run_rate"] = delivery["reference_run_rate"].fillna(
        delivery["match_format"].map(format_fallback).fillna(8.0)
    )
    delivery["reference_run_rate"] = delivery["reference_run_rate"].clip(lower=1.0)

    chase = delivery["innings"].isin([2, 4]) & delivery["target"].notna()
    first = delivery["innings"].isin([1, 3])
    rr = delivery["current_run_rate"].to_numpy(dtype="float64")
    reference = delivery["reference_run_rate"].to_numpy(dtype="float64")
    progress = delivery["innings_progress"].to_numpy(dtype="float64")
    wickets_lost = _bounded_ratio(delivery["wickets_before"], 10)
    wickets_available = _bounded_ratio(delivery["wickets_remaining"], 10)
    required = delivery["required_run_rate"].fillna(0).to_numpy(dtype="float64")
    required_normalized = required / reference

    chase_components = {
        "run_rate": np.clip((required_normalized - 1.0) / 1.5, 0.0, 1.0),
        "wickets": wickets_lost,
        "time": progress,
        "closeness": np.exp(-np.abs(required_normalized - 1.0)),
    }
    first_components = {
        "run_rate": np.clip((reference - rr) / reference, 0.0, 1.0) * progress,
        "wickets": wickets_lost,
        "time": progress,
        "closeness": np.exp(-np.abs(rr - reference) / reference) * progress,
    }
    batting_components = {
        name: np.where(chase, chase_components[name], first_components[name])
        for name in PRESSURE_WEIGHTS["batting"]
    }
    for name, component in batting_components.items():
        delivery[f"batting_{name}_component"] = component

    bowling_chase = {
        "run_rate": np.clip((1.0 - required_normalized) / 1.5, 0.0, 1.0),
        "wickets": wickets_available,
        "time": progress,
        "closeness": np.exp(-np.abs(required_normalized - 1.0)),
    }
    first_innings_bowling = {
        "run_rate": np.clip((rr - reference) / reference, 0.0, 1.0) * progress,
        "wickets": _bounded_ratio(10 - delivery["wickets_before"], 10),
        "time": progress,
        "closeness": np.exp(-np.abs(rr - reference) / reference) * progress,
    }
    bowling_components = {
        name: np.where(chase, bowling_chase[name], first_innings_bowling[name])
        for name in PRESSURE_WEIGHTS["bowling"]
    }
    for name, component in bowling_components.items():
        delivery[f"bowling_{name}_component"] = component
    delivery = apply_pressure_model(delivery)
    delivery.attrs["pressure_reference_run_rate"] = float(
        delivery["reference_run_rate"].median()
    )
    delivery.attrs["pressure_reference_source"] = (
        "median of up to prior first-innings rates, within format, with documented "
        "T20/T20I fallback for the first five available matches"
    )
    return delivery


def _safe_rate(numerator, denominator, multiplier=1.0):
    numerator = np.asarray(numerator, dtype="float64")
    denominator = np.asarray(denominator, dtype="float64")
    result = np.full(np.broadcast_shapes(numerator.shape, denominator.shape), np.nan)
    np.divide(
        multiplier * numerator,
        denominator,
        out=result,
        where=denominator > 0,
    )
    return result


def _consistency(values):
    clean = pd.Series(values).dropna()
    if len(clean) < 2:
        return np.nan
    coefficient_of_variation = clean.std(ddof=1) / max(abs(clean.mean()), 1e-9)
    return float(100.0 / (1.0 + coefficient_of_variation))


def calculate_player_metrics(deliveries):
    """Return batter/bowler summary frames and match-level evidence frames."""
    batting = deliveries.copy()
    batting["is_batter_out"] = (
        batting["dismissed_player_id"].notna()
        & batting["dismissed_player_id"].eq(batting["striker_id"])
    )
    batting["is_batting_pressure"] = batting["is_batting_pressure"].astype(bool)
    batting["pressure_batter_runs"] = batting["batter_runs"].where(
        batting["is_batting_pressure"], 0
    )
    batting["normal_batter_runs"] = batting["batter_runs"].where(
        ~batting["is_batting_pressure"], 0
    )
    batting["normal_batter_ball"] = (
        ~batting["is_batting_pressure"] & batting["is_batter_ball_faced"]
    )
    batting["batter_dot_ball"] = (
        batting["batter_runs"].eq(0) & batting["is_batter_ball_faced"]
    )
    batting["pressure_batter_dot"] = (
        batting["is_batting_pressure"] & batting["batter_dot_ball"]
    )
    batting["pressure_four"] = (
        batting["is_batting_pressure"] & batting["is_four"].fillna(False)
    )
    batting["pressure_six"] = (
        batting["is_batting_pressure"] & batting["is_six"].fillna(False)
    )
    bat_groups = ["striker_id", "striker_name"]
    bat_summary = (
        batting.groupby(bat_groups, dropna=False, as_index=False, observed=True)
        .agg(
            batter_runs=("batter_runs", "sum"),
            balls_faced=("is_batter_ball_faced", "sum"),
            legal_balls=("is_legal_ball", "sum"),
            fours=("is_four", "sum"),
            sixes=("is_six", "sum"),
            team_runs=("team_runs", "sum"),
            outs=("is_batter_out", "sum"),
            matches=("match_id", "nunique"),
            pressure_balls=("pressure_batter_ball", "sum"),
            pressure_runs=("pressure_batter_runs", "sum"),
            pressure_fours=("pressure_four", "sum"),
            pressure_sixes=("pressure_six", "sum"),
            normal_balls=("normal_batter_ball", "sum"),
            normal_runs=("normal_batter_runs", "sum"),
            dot_balls=("batter_dot_ball", "sum"),
            pressure_dot_balls=("pressure_batter_dot", "sum"),
        )
    )
    bat_summary["strike_rate"] = _safe_rate(
        bat_summary["batter_runs"], bat_summary["balls_faced"], 100
    )
    bat_summary["batting_average"] = _safe_rate(
        bat_summary["batter_runs"], bat_summary["outs"]
    )
    bat_summary["boundary_percentage"] = _safe_rate(
        bat_summary["fours"] + bat_summary["sixes"],
        bat_summary["balls_faced"],
        100,
    )
    bat_summary["dot_ball_percentage"] = _safe_rate(
        bat_summary["dot_balls"], bat_summary["balls_faced"], 100
    )
    bat_summary["dismissal_rate"] = _safe_rate(
        bat_summary["outs"], bat_summary["balls_faced"], 100
    )
    bat_summary["pressure_strike_rate"] = _safe_rate(
        bat_summary["pressure_runs"], bat_summary["pressure_balls"], 100
    )
    bat_summary["pressure_boundary_percentage"] = _safe_rate(
        bat_summary["pressure_fours"] + bat_summary["pressure_sixes"],
        bat_summary["pressure_balls"],
        100,
    )
    bat_summary["pressure_dot_ball_percentage"] = _safe_rate(
        bat_summary["pressure_dot_balls"], bat_summary["pressure_balls"], 100
    )
    bat_summary["pressure_opportunities"] = bat_summary["pressure_balls"]
    bat_summary["normal_strike_rate"] = _safe_rate(
        bat_summary["normal_runs"], bat_summary["normal_balls"], 100
    )
    bat_summary["strike_rate_difference"] = (
        bat_summary["pressure_strike_rate"] - bat_summary["normal_strike_rate"]
    )
    bat_comp = (
        batting.groupby(bat_groups + ["comp_name"], dropna=False, as_index=False)
        .agg(
            pressure_runs=("pressure_batter_runs", "sum"),
            pressure_balls=("pressure_batter_ball", "sum"),
            normal_runs=("normal_batter_runs", "sum"),
            normal_balls=("normal_batter_ball", "sum"),
        )
    )
    bat_comp_baselines = (
        bat_comp.groupby("comp_name", dropna=False, as_index=False)
        .agg(
            comp_pressure_runs=("pressure_runs", "sum"),
            comp_pressure_balls=("pressure_balls", "sum"),
            comp_normal_runs=("normal_runs", "sum"),
            comp_normal_balls=("normal_balls", "sum"),
        )
    )
    bat_comp_baselines["comp_pressure_rate"] = _safe_rate(
        bat_comp_baselines["comp_pressure_runs"],
        bat_comp_baselines["comp_pressure_balls"],
    )
    bat_comp_baselines["comp_normal_rate"] = _safe_rate(
        bat_comp_baselines["comp_normal_runs"],
        bat_comp_baselines["comp_normal_balls"],
    )
    bat_comp = bat_comp.merge(
        bat_comp_baselines[["comp_name", "comp_pressure_rate", "comp_normal_rate"]],
        on="comp_name",
        how="left",
    )
    prior = COMPETITION_BASELINE_PRIOR_BALLS
    bat_comp["pressure_strike_rate"] = _safe_rate(
        bat_comp["pressure_runs"] + prior * bat_comp["comp_pressure_rate"],
        bat_comp["pressure_balls"] + prior,
        100,
    )
    bat_comp["normal_strike_rate"] = _safe_rate(
        bat_comp["normal_runs"] + prior * bat_comp["comp_normal_rate"],
        bat_comp["normal_balls"] + prior,
        100,
    )
    bat_comp["difference"] = (
        bat_comp["pressure_strike_rate"] - bat_comp["normal_strike_rate"]
    )
    bat_comp["difference_weight"] = bat_comp["pressure_balls"].where(
        bat_comp["difference"].notna(), 0
    )
    bat_adjusted = (
        bat_comp.assign(weighted_difference=bat_comp["difference"] * bat_comp["difference_weight"])
        .groupby(bat_groups, as_index=False)
        .agg(
            competition_adjusted_difference=("weighted_difference", "sum"),
            comparison_pressure_balls=("difference_weight", "sum"),
        )
    )
    bat_adjusted["competition_adjusted_difference"] = _safe_rate(
        bat_adjusted["competition_adjusted_difference"],
        bat_adjusted["comparison_pressure_balls"],
    )
    bat_summary = bat_summary.merge(
        bat_adjusted[bat_groups + ["competition_adjusted_difference"]],
        on=bat_groups,
        how="left",
    )
    bat_match = (
        batting.groupby(bat_groups + ["match_id", "comp_name"], dropna=False, as_index=False)
        .agg(
            batter_runs=("batter_runs", "sum"),
            balls_faced=("is_batter_ball_faced", "sum"),
            pressure_runs=("pressure_batter_runs", "sum"),
            pressure_balls=("pressure_batter_ball", "sum"),
        )
    )
    bat_match["strike_rate"] = _safe_rate(
        bat_match["batter_runs"], bat_match["balls_faced"], 100
    )
    bat_match["pressure_strike_rate"] = _safe_rate(
        bat_match["pressure_runs"], bat_match["pressure_balls"], 100
    )
    bat_consistency = (
        bat_match.groupby(bat_groups)["pressure_strike_rate"]
        .apply(_consistency)
        .rename("consistency")
        .reset_index()
    )
    bat_summary = bat_summary.merge(bat_consistency, on=bat_groups, how="left")
    bat_pressure_match_counts = (
        bat_match.loc[bat_match["pressure_balls"].gt(0)]
        .groupby(bat_groups)["match_id"]
        .nunique()
        .rename("pressure_matches")
        .reset_index()
    )
    bat_pressure_innings = (
        batting.groupby(bat_groups + ["match_id", "innings"], dropna=False)
        .agg(pressure_balls=("pressure_batter_ball", "sum"))
        .reset_index()
        .loc[lambda frame: frame["pressure_balls"].gt(0)]
        .groupby(bat_groups)
        .size()
        .rename("pressure_innings")
        .reset_index()
    )
    bat_summary = bat_summary.merge(
        bat_pressure_match_counts, on=bat_groups, how="left"
    ).merge(bat_pressure_innings, on=bat_groups, how="left")
    bat_summary[["pressure_matches", "pressure_innings"]] = (
        bat_summary[["pressure_matches", "pressure_innings"]].fillna(0).astype(int)
    )

    bowling = deliveries.copy()
    bowling["is_bowling_pressure"] = bowling["is_bowling_pressure"].astype(bool)
    bowling["pressure_bowler_runs"] = bowling["bowler_conceded_runs"].where(
        bowling["is_bowling_pressure"], 0
    )
    bowling["normal_bowler_runs"] = bowling["bowler_conceded_runs"].where(
        ~bowling["is_bowling_pressure"], 0
    )
    bowling["normal_bowler_ball"] = (
        ~bowling["is_bowling_pressure"] & bowling["is_legal_ball"]
    )
    bowling["pressure_bowler_wicket"] = (
        bowling["is_bowling_pressure"] & bowling["is_bowler_wicket"]
    )
    bowling["pressure_bowler_dot"] = (
        bowling["is_bowling_pressure"] & bowling["is_dot_ball"]
    )
    bowling["pressure_bowler_boundary"] = (
        bowling["is_bowling_pressure"] & bowling["has_boundary_flag"]
    )
    bowl_groups = ["bowler_id", "bowler_name"]
    bowl_summary = (
        bowling.groupby(bowl_groups, dropna=False, as_index=False, observed=True)
        .agg(
            legal_balls=("is_legal_ball", "sum"),
            runs_conceded=("bowler_conceded_runs", "sum"),
            wickets=("is_bowler_wicket", "sum"),
            matches=("match_id", "nunique"),
            pressure_balls=("pressure_bowler_ball", "sum"),
            pressure_runs=("pressure_bowler_runs", "sum"),
            pressure_wickets=("pressure_bowler_wicket", "sum"),
            pressure_dots=("pressure_bowler_dot", "sum"),
            pressure_boundaries=("pressure_bowler_boundary", "sum"),
            normal_balls=("normal_bowler_ball", "sum"),
            normal_runs=("normal_bowler_runs", "sum"),
        )
    )
    bowl_summary["overs"] = bowl_summary["legal_balls"] / 6.0
    bowl_summary["economy"] = _safe_rate(
        bowl_summary["runs_conceded"], bowl_summary["legal_balls"], 6
    )
    bowl_summary["bowling_average"] = _safe_rate(
        bowl_summary["runs_conceded"], bowl_summary["wickets"]
    )
    bowl_summary["bowling_strike_rate"] = _safe_rate(
        bowl_summary["legal_balls"], bowl_summary["wickets"]
    )
    bowl_dots = (
        bowling.assign(dot=bowling["is_dot_ball"] & bowling["is_legal_ball"])
        .groupby(bowl_groups, dropna=False)["dot"]
        .sum()
        .reindex(pd.MultiIndex.from_frame(bowl_summary[bowl_groups]), fill_value=0)
        .to_numpy()
    )
    bowl_boundaries = (
        bowling.assign(boundary=bowling["has_boundary_flag"])
        .groupby(bowl_groups, dropna=False)["boundary"]
        .sum()
        .reindex(pd.MultiIndex.from_frame(bowl_summary[bowl_groups]), fill_value=0)
        .to_numpy()
    )
    bowl_summary["dot_ball_percentage"] = _safe_rate(
        bowl_dots, bowl_summary["legal_balls"], 100
    )
    bowl_summary["boundary_percentage_conceded"] = _safe_rate(
        bowl_boundaries, bowl_summary["legal_balls"], 100
    )
    bowl_summary["pressure_opportunities"] = bowl_summary["pressure_balls"]
    bowl_summary["normal_economy"] = _safe_rate(
        bowl_summary["normal_runs"], bowl_summary["normal_balls"], 6
    )
    bowl_summary["pressure_economy"] = _safe_rate(
        bowl_summary["pressure_runs"], bowl_summary["pressure_balls"], 6
    )
    bowl_summary["economy_difference"] = (
        bowl_summary["normal_economy"] - bowl_summary["pressure_economy"]
    )
    bowl_comp = (
        bowling.groupby(bowl_groups + ["comp_name"], dropna=False, as_index=False)
        .agg(
            pressure_runs=("pressure_bowler_runs", "sum"),
            pressure_balls=("pressure_bowler_ball", "sum"),
            normal_runs=("normal_bowler_runs", "sum"),
            normal_balls=("normal_bowler_ball", "sum"),
        )
    )
    bowl_comp_baselines = (
        bowl_comp.groupby("comp_name", dropna=False, as_index=False)
        .agg(
            comp_pressure_runs=("pressure_runs", "sum"),
            comp_pressure_balls=("pressure_balls", "sum"),
            comp_normal_runs=("normal_runs", "sum"),
            comp_normal_balls=("normal_balls", "sum"),
        )
    )
    bowl_comp_baselines["comp_pressure_rate"] = _safe_rate(
        bowl_comp_baselines["comp_pressure_runs"],
        bowl_comp_baselines["comp_pressure_balls"],
    )
    bowl_comp_baselines["comp_normal_rate"] = _safe_rate(
        bowl_comp_baselines["comp_normal_runs"],
        bowl_comp_baselines["comp_normal_balls"],
    )
    bowl_comp = bowl_comp.merge(
        bowl_comp_baselines[["comp_name", "comp_pressure_rate", "comp_normal_rate"]],
        on="comp_name",
        how="left",
    )
    bowl_comp["pressure_economy"] = _safe_rate(
        bowl_comp["pressure_runs"] + prior * bowl_comp["comp_pressure_rate"],
        bowl_comp["pressure_balls"] + prior,
        6,
    )
    bowl_comp["normal_economy"] = _safe_rate(
        bowl_comp["normal_runs"] + prior * bowl_comp["comp_normal_rate"],
        bowl_comp["normal_balls"] + prior,
        6,
    )
    bowl_comp["difference"] = (
        bowl_comp["normal_economy"] - bowl_comp["pressure_economy"]
    )
    bowl_comp["difference_weight"] = bowl_comp["pressure_balls"].where(
        bowl_comp["difference"].notna(), 0
    )
    bowl_adjusted = (
        bowl_comp.assign(weighted_difference=bowl_comp["difference"] * bowl_comp["difference_weight"])
        .groupby(bowl_groups, as_index=False)
        .agg(
            competition_adjusted_difference=("weighted_difference", "sum"),
            comparison_pressure_balls=("difference_weight", "sum"),
        )
    )
    bowl_adjusted["competition_adjusted_difference"] = _safe_rate(
        bowl_adjusted["competition_adjusted_difference"],
        bowl_adjusted["comparison_pressure_balls"],
    )
    bowl_summary = bowl_summary.merge(
        bowl_adjusted[bowl_groups + ["competition_adjusted_difference"]],
        on=bowl_groups,
        how="left",
    )
    bowl_match = (
        bowling.groupby(bowl_groups + ["match_id", "comp_name"], dropna=False, as_index=False)
        .agg(
            legal_balls=("is_legal_ball", "sum"),
            runs_conceded=("bowler_conceded_runs", "sum"),
            pressure_balls=("pressure_bowler_ball", "sum"),
            pressure_runs=("pressure_bowler_runs", "sum"),
            wickets=("is_bowler_wicket", "sum"),
        )
    )
    bowl_match["economy"] = _safe_rate(
        bowl_match["runs_conceded"], bowl_match["legal_balls"], 6
    )
    bowl_match["pressure_economy"] = _safe_rate(
        bowl_match["pressure_runs"], bowl_match["pressure_balls"], 6
    )
    bowl_consistency = (
        bowl_match.groupby(bowl_groups)["pressure_economy"]
        .apply(_consistency)
        .rename("consistency")
        .reset_index()
    )
    bowl_summary = bowl_summary.merge(bowl_consistency, on=bowl_groups, how="left")
    bowl_pressure_match_counts = (
        bowl_match.loc[bowl_match["pressure_balls"].gt(0)]
        .groupby(bowl_groups)["match_id"]
        .nunique()
        .rename("pressure_matches")
        .reset_index()
    )
    bowl_pressure_innings = (
        bowling.groupby(bowl_groups + ["match_id", "innings"], dropna=False)
        .agg(pressure_balls=("pressure_bowler_ball", "sum"))
        .reset_index()
        .loc[lambda frame: frame["pressure_balls"].gt(0)]
        .groupby(bowl_groups)
        .size()
        .rename("pressure_innings")
        .reset_index()
    )
    bowl_summary = bowl_summary.merge(
        bowl_pressure_match_counts, on=bowl_groups, how="left"
    ).merge(bowl_pressure_innings, on=bowl_groups, how="left")
    bowl_summary[["pressure_matches", "pressure_innings"]] = (
        bowl_summary[["pressure_matches", "pressure_innings"]]
        .fillna(0)
        .astype(int)
    )

    bat_competitions = (
        batting.groupby(bat_groups)["comp_name"].nunique().rename("competition_coverage").reset_index()
    )
    bowl_competitions = (
        bowling.groupby(bowl_groups)["comp_name"].nunique().rename("competition_coverage").reset_index()
    )
    bat_summary = bat_summary.merge(bat_competitions, on=bat_groups, how="left")
    bowl_summary = bowl_summary.merge(bowl_competitions, on=bowl_groups, how="left")
    return {
        "batters": bat_summary,
        "bowlers": bowl_summary,
        "batter_matches": bat_match,
        "bowler_matches": bowl_match,
    }


def rank_players(
    metrics,
    role,
    min_matches=3,
    min_pressure_opportunities=12,
    weights=(0.60, 0.20, 0.20),
):
    """Rank eligible players; weights are performance, consistency, reliability."""
    performance_weight, consistency_weight, reliability_weight = weights
    if not np.isclose(sum(weights), 1.0) or any(weight < 0 for weight in weights):
        raise ValueError("SPI weights must be non-negative and sum to 1.")
    if role == "batter":
        frame = metrics["batters"].copy()
        player_id, name = "striker_id", "striker_name"
        performance = "pressure_strike_rate"
        baseline = "normal_strike_rate"
        difference = "competition_adjusted_difference"
    elif role == "bowler":
        frame = metrics["bowlers"].copy()
        player_id, name = "bowler_id", "bowler_name"
        performance = "pressure_economy"
        baseline = "normal_economy"
        difference = "competition_adjusted_difference"
    else:
        raise ValueError("role must be 'batter' or 'bowler'")

    frame = frame.loc[
        frame[player_id].notna()
        & frame["pressure_matches"].ge(min_matches)
        & frame["pressure_opportunities"].ge(min_pressure_opportunities)
        & frame[performance].notna()
        & frame[baseline].notna()
        & frame[difference].notna()
    ].copy()
    if frame.empty:
        return frame.assign(rank=pd.Series(dtype="int64"))
    sample_weight = frame["pressure_opportunities"] / (
        frame["pressure_opportunities"] + PRESSURE_PRIOR_OPPORTUNITIES
    )
    frame["reliability"] = (100.0 * sample_weight).clip(0, 100)
    frame["adjusted_difference"] = frame[difference] * sample_weight
    robust_scale = frame["adjusted_difference"].abs().median()
    if not np.isfinite(robust_scale) or robust_scale <= 1e-9:
        robust_scale = 1.0
    frame["performance_component"] = 50 + 50 * np.tanh(
        frame["adjusted_difference"] / (2 * robust_scale)
    )
    frame["performance"] = frame[performance]
    frame["normal_performance"] = frame[baseline]
    frame["spi"] = np.clip(
        performance_weight * frame["performance_component"]
        + consistency_weight * frame["consistency"].fillna(50)
        + reliability_weight * frame["reliability"],
        0,
        100,
    )
    uncertainty_scale = 1.0 / np.sqrt(frame["pressure_opportunities"].clip(lower=1))
    frame["uncertainty_indicator"] = uncertainty_scale
    frame = frame.sort_values(
        ["spi", "reliability", "pressure_opportunities", name, player_id],
        ascending=[False, False, False, True, True],
        kind="stable",
    )
    frame.insert(0, "rank", np.arange(1, len(frame) + 1))
    frame["rank"] = frame["rank"].astype(int)
    frame["player_id"] = frame[player_id].astype("int64")
    frame["player_name"] = frame[name].astype(str)
    return frame
