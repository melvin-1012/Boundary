"""Generate provisional evidence-backed SPI ranking outputs and sensitivity checks."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analytics.cricket_metrics import (
    PRESSURE_WEIGHTS,
    apply_pressure_model,
    calculate_player_metrics,
    rank_players,
)


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
REPORTS = ROOT / "reports"
DEFAULT_WEIGHTS = (0.60, 0.20, 0.20)
DEFAULT_MIN_MATCHES = 3
DEFAULT_MIN_OPPORTUNITIES = 12
METHODOLOGY_VERSION = "pressure-spi-v1-provisional"


def _top_ids(frame):
    return list(frame.head(10)["player_id"].astype(int))


def _overlap(left, right):
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a | b else 1.0


def _correlation_diagnostics(frame):
    features = ["performance_component", "consistency", "reliability"]
    if len(frame) < 3:
        return {"eligible_players": int(len(frame)), "spearman_pairs": []}
    matrix = frame[features].corr(method="spearman")
    pairs = []
    for index, left in enumerate(features):
        for right in features[index + 1 :]:
            coefficient = matrix.loc[left, right]
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "spearman_rho": None if pd.isna(coefficient) else float(coefficient),
                    "high_overlap_flag": bool(
                        pd.notna(coefficient) and abs(coefficient) >= 0.7
                    ),
                }
            )
    return {"eligible_players": int(len(frame)), "spearman_pairs": pairs}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pressure_diagnostics(deliveries, role):
    pressure_side = "batting" if role == "batter" else "bowling"
    pressure_column = f"is_{pressure_side}_pressure"
    opportunity_column = (
        "pressure_batter_ball" if role == "batter" else "pressure_bowler_ball"
    )
    components = ["run_rate", "wickets", "time", "closeness"]
    values = deliveries[
        [f"{pressure_side}_{name}_component" for name in components]
    ].rename(columns=lambda name: name.removeprefix(f"{pressure_side}_").removesuffix("_component"))
    correlations = values.corr(method="spearman")
    pairs = []
    for index, left in enumerate(components):
        for right in components[index + 1 :]:
            coefficient = correlations.loc[left, right]
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "spearman_rho": None if pd.isna(coefficient) else float(coefficient),
                    "high_overlap_flag": bool(
                        pd.notna(coefficient) and abs(coefficient) >= 0.70
                    ),
                }
            )
    weights = PRESSURE_WEIGHTS[pressure_side]
    mean_components = values.mean()
    contributions = {
        component: {
            "weight": weights[component],
            "mean_normalized_component": float(mean_components[component]),
            "mean_score_points": float(
                100 * weights[component] * mean_components[component]
            ),
        }
        for component in components
    }
    valid = deliveries[pressure_column].notna()
    scored_deliveries = deliveries.loc[valid].copy()
    pressure_flags = scored_deliveries[pressure_column].astype(bool)
    rate = scored_deliveries["required_run_rate"].where(
        scored_deliveries["target"].notna(),
        scored_deliveries["current_run_rate"],
    )
    scored_deliveries["rate_vs_reference"] = (
        rate / scored_deliveries["reference_run_rate"]
    )
    comparison_features = [
        "rate_vs_reference",
        "wickets_before",
        "balls_remaining",
        "innings_progress",
    ]
    pressure_vs_ordinary = {}
    for label, selection in (
        ("pressure", pressure_flags),
        ("ordinary", ~pressure_flags),
    ):
        selected = scored_deliveries.loc[selection]
        pressure_vs_ordinary[label] = {
            "delivery_count": int(len(selected)),
            "feature_distributions": {
                feature: {
                    "median": (
                        float(selected[feature].median())
                        if selected[feature].notna().any()
                        else None
                    ),
                    "q25": (
                        float(selected[feature].quantile(0.25))
                        if selected[feature].notna().any()
                        else None
                    ),
                    "q75": (
                        float(selected[feature].quantile(0.75))
                        if selected[feature].notna().any()
                        else None
                    ),
                }
                for feature in comparison_features
            },
            "innings_phase_share": {
                str(phase): float(share)
                for phase, share in (
                    selected["innings_phase"]
                    .value_counts(normalize=True, dropna=False)
                    .items()
                )
            },
        }
    scored = deliveries.loc[valid].sort_values(
        f"{pressure_side}_pressure", ascending=False, kind="stable"
    )
    sample_event = None
    if not scored.empty:
        row = scored.iloc[0]
        sample_event = {
            "match_id": int(row["match_id"]),
            "innings": int(row["innings"]),
            "innings_ball_num": int(row["innings_ball_num"]),
            "score_before": float(row["score_before"]),
            "wickets_before": int(row["wickets_before"]),
            "legal_balls_before": int(row["legal_balls_before"]),
            "balls_remaining": float(row["balls_remaining"]),
            "target": None if pd.isna(row["target"]) else float(row["target"]),
            "required_run_rate": (
                None
                if pd.isna(row["required_run_rate"])
                else float(row["required_run_rate"])
            ),
            "reference_run_rate": float(row["reference_run_rate"]),
            "pressure_score": float(row[f"{pressure_side}_pressure"]),
            "components": {
                component: {
                    "normalized_value": float(row[f"{pressure_side}_{component}_component"]),
                    "weight": weights[component],
                    "score_points": float(
                        100 * weights[component] * row[f"{pressure_side}_{component}_component"]
                    ),
                }
                for component in components
            },
        }
    return {
        "weights": weights,
        "pressure_delivery_count": int(
            (deliveries[pressure_column] & valid).sum()
        ),
        "pressure_opportunity_count": int(
            deliveries.loc[valid, opportunity_column].sum()
        ),
        "scored_delivery_count": int(valid.sum()),
        "pressure_vs_ordinary": pressure_vs_ordinary,
        "mean_normalized_contributions": contributions,
        "component_spearman_pairs": pairs,
        "sample_event": sample_event,
    }


def _independent_spi_check(metrics, role, ranked, weights):
    if role == "batter":
        source = metrics["batters"].copy()
        player_id, name = "striker_id", "striker_name"
        performance, baseline = "pressure_strike_rate", "normal_strike_rate"
    else:
        source = metrics["bowlers"].copy()
        player_id, name = "bowler_id", "bowler_name"
        performance, baseline = "pressure_economy", "normal_economy"
    eligible = source.loc[
        source[player_id].notna()
        & source["pressure_matches"].ge(DEFAULT_MIN_MATCHES)
        & source["pressure_opportunities"].ge(DEFAULT_MIN_OPPORTUNITIES)
        & source[performance].notna()
        & source[baseline].notna()
        & source["competition_adjusted_difference"].notna()
    ].copy()
    exposure = eligible["pressure_opportunities"].astype(float)
    sample_weight = exposure / (exposure + 30.0)
    adjusted = eligible["competition_adjusted_difference"] * sample_weight
    scale = adjusted.abs().median()
    if pd.isna(scale) or scale <= 1e-9:
        scale = 1.0
    performance_component = 50 + 50 * (adjusted / (2 * scale)).map(math.tanh)
    reliability = 100.0 * sample_weight
    consistency = eligible["consistency"].fillna(50)
    independently_computed = (
        weights[0] * performance_component
        + weights[1] * consistency
        + weights[2] * reliability
    ).clip(0, 100)
    expected = pd.DataFrame(
        {
            "player_id": eligible[player_id].astype("int64"),
            "player_name": eligible[name].astype(str),
            "performance_component": performance_component,
            "consistency": consistency,
            "reliability": reliability,
            "spi_independent": independently_computed,
        }
    )
    sample = ranked.head(10)[
        ["player_id", "player_name", "performance_component", "consistency", "reliability", "spi"]
    ].merge(expected, on=["player_id", "player_name"], validate="one_to_one")
    sample["spi_absolute_error"] = (sample["spi"] - sample["spi_independent"]).abs()
    return {
        "formula": "weighted performance_component + consistency + reliability",
        "sample_player_count": int(len(sample)),
        "maximum_absolute_spi_error": (
            float(sample["spi_absolute_error"].max()) if not sample.empty else 0.0
        ),
        "independent_recalculation_passed": bool(
            sample.empty or sample["spi_absolute_error"].le(1e-10).all()
        ),
        "sample": sample[
            [
                "player_id",
                "player_name",
                "spi",
                "spi_independent",
                "spi_absolute_error",
            ]
        ].to_dict("records"),
    }


def _competition_evidence(delivery_path, rankings, role):
    pressure_column = (
        "is_batting_pressure" if role == "batter" else "is_bowling_pressure"
    )
    deliveries = pd.read_parquet(delivery_path, columns=[
        "comp_name",
        "striker_id" if role == "batter" else "bowler_id",
        pressure_column,
    ])
    deliveries = deliveries.loc[deliveries[pressure_column]]
    id_column = "striker_id" if role == "batter" else "bowler_id"
    coverage = (
        deliveries.groupby(id_column)["comp_name"]
        .agg(lambda values: sorted(set(values.dropna().astype(str))))
    )
    rankings["competition_scope"] = rankings["player_id"].map(
        lambda player_id: ", ".join(coverage.get(int(player_id), []))
    )
    rankings["evidence_summary"] = rankings.apply(
        lambda row: (
            f"Pressure performance {row['performance']:.2f} versus normal "
            f"{row['normal_performance']:.2f}; competition-adjusted change "
            f"{row['competition_adjusted_difference']:+.2f}; "
            f"{int(row['pressure_opportunities'])} pressure opportunities "
            f"across {int(row['pressure_matches'])} pressure matches."
        ),
        axis=1,
    )
    return rankings


def _top_ten_match_evidence(metrics, top_frames, reports_dir):
    match_frames = {
        "batter": metrics["batter_matches"],
        "bowler": metrics["bowler_matches"],
    }
    columns = {
        "batter": {
            "id": "striker_id",
            "name": "striker_name",
            "performance": "pressure_strike_rate",
            "baseline": "normal_strike_rate",
            "exposure": "pressure_balls",
            "all_exposure": "balls_faced",
            "pressure_numerator": "pressure_runs",
            "all_numerator": "batter_runs",
            "multiplier": 100.0,
            "advantage": "pressure_minus_normal",
        },
        "bowler": {
            "id": "bowler_id",
            "name": "bowler_name",
            "performance": "pressure_economy",
            "baseline": "normal_economy",
            "exposure": "pressure_balls",
            "all_exposure": "legal_balls",
            "pressure_numerator": "pressure_runs",
            "all_numerator": "runs_conceded",
            "multiplier": 6.0,
            "advantage": "normal_minus_pressure",
        },
    }
    evidence_frames = []
    summary_frames = {}
    for role, top in top_frames.items():
        spec = columns[role]
        top_players = top[["rank", "player_id", "player_name"]].rename(
            columns={"player_id": spec["id"], "player_name": spec["name"]}
        )
        matches = match_frames[role].merge(
            top_players,
            on=[spec["id"], spec["name"]],
            how="inner",
            validate="many_to_one",
        )
        matches = matches.loc[matches[spec["exposure"]].gt(0)].copy()
        matches["normal_exposure"] = (
            matches[spec["all_exposure"]] - matches[spec["exposure"]]
        ).clip(lower=0)
        matches["normal_numerator"] = (
            matches[spec["all_numerator"]] - matches[spec["pressure_numerator"]]
        )
        matches["pressure_performance"] = (
            spec["multiplier"]
            * matches[spec["pressure_numerator"]]
            / matches[spec["exposure"]]
        )
        matches["normal_performance"] = (
            spec["multiplier"]
            * matches["normal_numerator"]
            / matches["normal_exposure"].replace(0, pd.NA)
        )
        matches[spec["advantage"]] = (
            matches["pressure_performance"] - matches["normal_performance"]
            if role == "batter"
            else matches["normal_performance"] - matches["pressure_performance"]
        )
        total_exposure = matches.groupby(spec["id"])[spec["exposure"]].transform("sum")
        matches["pressure_opportunity_share"] = matches[spec["exposure"]] / total_exposure
        summary = (
            matches.groupby([spec["id"], spec["name"]], as_index=False)
            .agg(
                pressure_matches_with_comparison=(spec["advantage"], "count"),
                matches_above_normal=(spec["advantage"], lambda values: int(values.gt(0).sum())),
                max_single_match_opportunity_share=("pressure_opportunity_share", "max"),
                best_pressure_match_id=(
                    "pressure_performance",
                    lambda values: int(matches.loc[values.idxmax(), "match_id"]),
                ),
                worst_pressure_match_id=(
                    "pressure_performance",
                    lambda values: int(matches.loc[values.idxmin(), "match_id"]),
                ),
            )
            .rename(columns={spec["id"]: "player_id", spec["name"]: "player_name"})
        )
        summary_frames[role] = summary
        matches["role"] = role
        matches = matches.rename(
            columns={
                spec["id"]: "player_id",
                spec["name"]: "player_name",
                spec["exposure"]: "pressure_opportunities",
                spec["advantage"]: "pressure_advantage",
            }
        )
        evidence_frames.append(
            matches[
                [
                    "role",
                    "rank",
                    "player_id",
                    "player_name",
                    "match_id",
                    "comp_name",
                    "pressure_opportunities",
                    "pressure_performance",
                    "normal_exposure",
                    "normal_performance",
                    "pressure_advantage",
                    "pressure_opportunity_share",
                ]
            ]
        )
    evidence = pd.concat(evidence_frames, ignore_index=True)
    evidence = evidence.sort_values(
        ["role", "rank", "match_id"], kind="stable"
    )
    evidence.to_csv(reports_dir / "top_10_match_evidence.csv", index=False)
    return summary_frames


def _add_scenario_robustness(ranked, scenarios):
    scenario_ranks = {}
    for scenario in scenarios:
        for item in scenario["top_10_rank_changes"]:
            if item["scenario_rank"] is not None:
                scenario_ranks.setdefault(item["player_id"], []).append(
                    int(item["scenario_rank"])
                )
    scenario_count = len(scenarios)
    ranked["top_10_scenario_count"] = ranked["player_id"].map(
        lambda player_id: len(scenario_ranks.get(int(player_id), []))
    )
    ranked["tested_scenario_count"] = scenario_count
    ranked["top_10_scenario_rate"] = (
        ranked["top_10_scenario_count"] / scenario_count if scenario_count else 0.0
    )
    ranked["scenario_rank_min"] = ranked["player_id"].map(
        lambda player_id: min(scenario_ranks.get(int(player_id), []), default=pd.NA)
    )
    ranked["scenario_rank_max"] = ranked["player_id"].map(
        lambda player_id: max(scenario_ranks.get(int(player_id), []), default=pd.NA)
    )
    return ranked


def _sensitivity(metrics, role, baseline, pressure_deliveries):
    baseline_ids = _top_ids(baseline)
    baseline_ranks = baseline.set_index("player_id")["rank"].to_dict()
    baseline_spi = baseline.set_index("player_id")["spi"].to_dict()
    scenarios = []
    pressure_side = "batting" if role == "batter" else "bowling"

    def add_scenario(label, candidate, **details):
        candidate_ids = _top_ids(candidate)
        candidate_ranks = candidate.set_index("player_id")["rank"].to_dict()
        candidate_spi = candidate.set_index("player_id")["spi"].to_dict()
        pressure_events = int(
            pressure_deliveries[f"is_{pressure_side}_pressure"].fillna(False).sum()
        )
        pressure_opportunities = int(
            pressure_deliveries[
                "pressure_batter_ball" if role == "batter" else "pressure_bowler_ball"
            ].sum()
        )
        scenarios.append(
            {
                "scenario": label,
                "eligible_players": int(len(candidate)),
                "top_10_overlap_jaccard": _overlap(baseline_ids, candidate_ids),
                "top_10_player_ids": candidate_ids,
                "top_10_rank_changes": [
                    {
                        "player_id": int(player_id),
                        "baseline_rank": baseline_ranks.get(player_id),
                        "scenario_rank": candidate_ranks.get(player_id),
                        "baseline_spi": (
                            float(baseline_spi[player_id])
                            if player_id in baseline_spi
                            else None
                        ),
                        "scenario_spi": (
                            float(candidate_spi[player_id])
                            if player_id in candidate_spi
                            else None
                        ),
                        "spi_delta": (
                            float(candidate_spi[player_id] - baseline_spi[player_id])
                            if player_id in baseline_spi and player_id in candidate_spi
                            else None
                        ),
                        "rank_delta": (
                            int(baseline_ranks[player_id] - candidate_ranks[player_id])
                            if player_id in baseline_ranks and player_id in candidate_ranks
                            else None
                        ),
                    }
                    for player_id in sorted(set(baseline_ids) | set(candidate_ids))
                ],
                "pressure_event_count": pressure_events,
                "pressure_opportunity_count": pressure_opportunities,
                **details,
            }
        )

    for label, weights in [
        ("performance_heavy", (0.70, 0.15, 0.15)),
        ("balanced", (0.50, 0.25, 0.25)),
        ("consistency_heavy", (0.40, 0.40, 0.20)),
        ("reliability_heavy", (0.40, 0.20, 0.40)),
        ("reliability_removed", (0.75, 0.25, 0.0)),
    ]:
        candidate = rank_players(
            metrics,
            role,
            min_matches=DEFAULT_MIN_MATCHES,
            min_pressure_opportunities=DEFAULT_MIN_OPPORTUNITIES,
            weights=weights,
        )
        add_scenario(
            label,
            candidate,
            weights={
                "performance": weights[0],
                "consistency": weights[1],
                "reliability": weights[2],
            },
        )
    for label, min_matches, min_opportunities in [
        ("lower_exposure", 2, 6),
        ("higher_exposure", 5, 24),
    ]:
        candidate = rank_players(
            metrics,
            role,
            min_matches=min_matches,
            min_pressure_opportunities=min_opportunities,
            weights=DEFAULT_WEIGHTS,
        )
        add_scenario(
            label,
            candidate,
            min_matches=min_matches,
            min_pressure_opportunities=min_opportunities,
        )
    for threshold in (40.0, 60.0):
        classified = apply_pressure_model(
            pressure_deliveries, threshold=threshold
        )
        threshold_metrics = calculate_player_metrics(classified)
        candidate = rank_players(
            threshold_metrics,
            role,
            min_matches=DEFAULT_MIN_MATCHES,
            min_pressure_opportunities=DEFAULT_MIN_OPPORTUNITIES,
            weights=DEFAULT_WEIGHTS,
        )
        add_scenario(
            f"pressure_threshold_{int(threshold)}",
            candidate,
            pressure_threshold=threshold,
            pressure_event_count=int(
                (
                    classified[f"is_{pressure_side}_pressure"]
                    & classified[f"{pressure_side}_pressure"].notna()
                ).sum()
            ),
            pressure_opportunity_count=int(
                classified[
                    "pressure_batter_ball" if role == "batter" else "pressure_bowler_ball"
                ].sum()
            ),
        )
    balanced_pressure_weights = {
        role_name: {component: 0.25 for component in weights}
        for role_name, weights in PRESSURE_WEIGHTS.items()
    }
    balanced_state = apply_pressure_model(
        pressure_deliveries, weights=balanced_pressure_weights
    )
    balanced_metrics = calculate_player_metrics(balanced_state)
    candidate = rank_players(
        balanced_metrics,
        role,
        min_matches=DEFAULT_MIN_MATCHES,
        min_pressure_opportunities=DEFAULT_MIN_OPPORTUNITIES,
        weights=DEFAULT_WEIGHTS,
    )
    add_scenario(
        "equal_pressure_component_weights",
        candidate,
        pressure_weights=balanced_pressure_weights,
    )
    no_closeness_pressure_weights = {}
    for role_name, component_weights in PRESSURE_WEIGHTS.items():
        retained = {
            component: weight
            for component, weight in component_weights.items()
            if component != "closeness"
        }
        total = sum(retained.values())
        no_closeness_pressure_weights[role_name] = {
            **{component: weight / total for component, weight in retained.items()},
            "closeness": 0.0,
        }
    no_closeness_state = apply_pressure_model(
        pressure_deliveries, weights=no_closeness_pressure_weights
    )
    no_closeness_metrics = calculate_player_metrics(no_closeness_state)
    candidate = rank_players(
        no_closeness_metrics,
        role,
        min_matches=DEFAULT_MIN_MATCHES,
        min_pressure_opportunities=DEFAULT_MIN_OPPORTUNITIES,
        weights=DEFAULT_WEIGHTS,
    )
    add_scenario(
        "closeness_removed",
        candidate,
        pressure_weights=no_closeness_pressure_weights,
        pressure_event_count=int(no_closeness_state[f"is_{pressure_side}_pressure"].sum()),
        pressure_opportunity_count=int(
            no_closeness_state[
                "pressure_batter_ball" if role == "batter" else "pressure_bowler_ball"
            ].sum()
        ),
    )
    no_wickets_pressure_weights = {}
    for role_name, component_weights in PRESSURE_WEIGHTS.items():
        retained = {
            component: weight
            for component, weight in component_weights.items()
            if component != "wickets"
        }
        total = sum(retained.values())
        no_wickets_pressure_weights[role_name] = {
            **{component: weight / total for component, weight in retained.items()},
            "wickets": 0.0,
        }
    no_wickets_state = apply_pressure_model(
        pressure_deliveries, weights=no_wickets_pressure_weights
    )
    no_wickets_metrics = calculate_player_metrics(no_wickets_state)
    candidate = rank_players(
        no_wickets_metrics,
        role,
        min_matches=DEFAULT_MIN_MATCHES,
        min_pressure_opportunities=DEFAULT_MIN_OPPORTUNITIES,
        weights=DEFAULT_WEIGHTS,
    )
    add_scenario(
        "wickets_component_removed",
        candidate,
        pressure_weights=no_wickets_pressure_weights,
        pressure_event_count=int(
            no_wickets_state[f"is_{pressure_side}_pressure"].sum()
        ),
        pressure_opportunity_count=int(
            no_wickets_state[
                "pressure_batter_ball" if role == "batter" else "pressure_bowler_ball"
            ].sum()
        ),
    )
    return scenarios


def generate_rankings(
    curated_dir=CURATED,
    reports_dir=REPORTS,
    min_matches=DEFAULT_MIN_MATCHES,
    min_opportunities=DEFAULT_MIN_OPPORTUNITIES,
):
    curated_dir, reports_dir = Path(curated_dir), Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "batters": pd.read_parquet(curated_dir / "batter_metrics.parquet"),
        "bowlers": pd.read_parquet(curated_dir / "bowler_metrics.parquet"),
    }
    metrics["batters"].to_csv(reports_dir / "all_batter_metrics.csv", index=False)
    metrics["bowlers"].to_csv(reports_dir / "all_bowler_metrics.csv", index=False)
    all_deliveries = curated_dir / "pressure_deliveries.parquet"
    pressure_deliveries = pd.read_parquet(all_deliveries)
    defaults = {"batter": None, "bowler": None}
    top_frames = {"batter": None, "bowler": None}
    ranking_validation = {}
    for role, legacy_filename, full_filename, top_filename in [
        (
            "batter",
            "final_top10_batters.csv",
            "full_batter_ranking.csv",
            "top_10_batters.csv",
        ),
        (
            "bowler",
            "final_top10_bowlers.csv",
            "full_bowler_ranking.csv",
            "top_10_bowlers.csv",
        ),
    ]:
        ranked = rank_players(
            metrics,
            role,
            min_matches=min_matches,
            min_pressure_opportunities=min_opportunities,
            weights=DEFAULT_WEIGHTS,
        )
        defaults[role] = ranked
        ranked = _competition_evidence(all_deliveries, ranked, role)
        ranked["spi_gap_to_next"] = ranked["spi"] - ranked["spi"].shift(-1)
        ranked.to_csv(reports_dir / full_filename, index=False)
        selected = ranked.head(10).copy()
        exactly_ten = len(selected) == 10
        unique_players = selected["player_id"].is_unique if not selected.empty else True
        sequential_ranks = (
            selected["rank"].tolist() == list(range(1, len(selected) + 1))
        )
        ranking_validation[role] = {
            "eligible_players": int(len(ranked)),
            "selected_players": int(len(selected)),
            "exactly_ten": exactly_ten,
            "unique_player_ids": bool(unique_players),
            "ranks_are_sequential": bool(sequential_ranks),
            "ten_players_available": len(ranked) >= 10,
        }
        if len(ranked) >= 10 and not (
            exactly_ten and unique_players and sequential_ranks
        ):
            raise AssertionError(f"Invalid {role} top-ten ranking output.")
        selected.to_csv(reports_dir / top_filename, index=False)
        selected.to_csv(reports_dir / legacy_filename, index=False)
        top_frames[role] = selected

    sensitivity = {
        role: _sensitivity(metrics, role, frame, pressure_deliveries)
        for role, frame in defaults.items()
    }
    match_evidence_summaries = _top_ten_match_evidence(
        calculate_player_metrics(pressure_deliveries), top_frames, reports_dir
    )
    for role, full_filename, top_filename, legacy_filename in [
        ("batter", "full_batter_ranking.csv", "top_10_batters.csv", "final_top10_batters.csv"),
        ("bowler", "full_bowler_ranking.csv", "top_10_bowlers.csv", "final_top10_bowlers.csv"),
    ]:
        ranked = pd.read_csv(reports_dir / full_filename)
        ranked = _add_scenario_robustness(ranked, sensitivity[role])
        ranked.to_csv(reports_dir / full_filename, index=False)
        selected = ranked.head(10).merge(
            match_evidence_summaries[role],
            on=["player_id", "player_name"],
            how="left",
            validate="one_to_one",
        )
        selected.to_csv(reports_dir / top_filename, index=False)
        selected.to_csv(reports_dir / legacy_filename, index=False)
    input_hashes = {
        path.name: _sha256(path)
        for path in sorted((ROOT / "data" / "raw").glob("*.csv"))
    }
    run_identity = {
        "methodology_version": METHODOLOGY_VERSION,
        "input_sha256": input_hashes,
        "eligibility": {
            "min_matches": min_matches,
            "min_pressure_opportunities": min_opportunities,
        },
        "spi_weights": DEFAULT_WEIGHTS,
        "pressure_weights": PRESSURE_WEIGHTS,
        "pressure_threshold": 50.0,
    }
    ranking_run_id = hashlib.sha256(
        json.dumps(run_identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]
    ranking_json = {
        "status": "provisional",
        "methodology_version": METHODOLOGY_VERSION,
        "ranking_run_id": ranking_run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": input_hashes,
        "ranking_file_sha256": {
            "batters": _sha256(reports_dir / "top_10_batters.csv"),
            "bowlers": _sha256(reports_dir / "top_10_bowlers.csv"),
        },
        "methodology_note": (
            "Exploratory rankings based on a transparent, unvalidated pressure "
            "heuristic. Do not treat as official/final until the pressure model, "
            "weights, eligibility, and source-field semantics are reviewed."
        ),
        "source_outputs": {
            "batters": "reports/top_10_batters.csv",
            "bowlers": "reports/top_10_bowlers.csv",
            "top_10_match_evidence": "reports/top_10_match_evidence.csv",
            "full_batters": "reports/full_batter_ranking.csv",
            "full_bowlers": "reports/full_bowler_ranking.csv",
            "batter_metrics": "reports/all_batter_metrics.csv",
            "bowler_metrics": "reports/all_bowler_metrics.csv",
        },
        "eligibility": {
            "min_matches": min_matches,
            "min_pressure_opportunities": min_opportunities,
            "rationale": "At least three distinct matches containing pressure exposure and twelve pressure balls (two overs) are provisional minimum exposure guards; thresholds are sensitivity-tested.",
        },
        "weights": {
            "performance": DEFAULT_WEIGHTS[0],
            "consistency": DEFAULT_WEIGHTS[1],
            "reliability": DEFAULT_WEIGHTS[2],
        },
        "eligible_counts": {
            role: int(len(frame)) for role, frame in defaults.items()
        },
        "top_10_counts": {
            role: int(min(len(frame), 10)) for role, frame in defaults.items()
        },
        "ranking_validation": ranking_validation,
        "sensitivity": sensitivity,
        "scenario_robustness_note": (
            "Top-ten scenario rate is the fraction of tested alternative "
            "specifications in which a player appears in the top ten; it is "
            "not a probability or confidence interval."
        ),
        "correlation_diagnostics": {
            role: _correlation_diagnostics(frame) for role, frame in defaults.items()
        },
        "pressure_diagnostics": {
            role: _pressure_diagnostics(pressure_deliveries, role)
            for role in ("batter", "bowler")
        },
        "independent_spi_checks": {
            role: _independent_spi_check(
                metrics, role, defaults[role], DEFAULT_WEIGHTS
            )
            for role in ("batter", "bowler")
        },
    }
    (reports_dir / "final_rankings.json").write_text(
        json.dumps(ranking_json, indent=2, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )
    return ranking_json


def main():
    result = generate_rankings()
    for role, count in result["top_10_counts"].items():
        print(f"{role}: {count} ranked players; {result['eligible_counts'][role]} eligible")
    print("Ranking status:", result["status"])


if __name__ == "__main__":
    main()
