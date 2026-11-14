"""Match-level 1,000-iteration bootstrap uncertainty analysis for pressure rankings."""

import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
REPORTS = ROOT / "reports"


def run_bootstrap(n_iterations=1000, seed=42):
    np.random.seed(seed)
    bat_match = pd.read_parquet(CURATED / "batter_match_metrics.parquet")
    bowl_match = pd.read_parquet(CURATED / "bowler_match_metrics.parquet")

    # The cohort of scoped matches with deliveries (837 matches)
    match_ids = bat_match["match_id"].unique()

    top_bat_ids = [4708, 8, 1077, 8301, 20702, 6651, 6460, 4773, 7897, 152]
    bat_names = bat_match.set_index("striker_id")["striker_name"].to_dict()

    top_bowl_ids = [25138, 56817, 3077, 25132, 32862, 23, 4716, 48616, 2490, 8530]
    bowl_names = bowl_match.set_index("bowler_id")["bowler_name"].to_dict()

    # Storage for Batters
    bat_ranks = {pid: [] for pid in top_bat_ids}
    bat_eligible_count = {pid: 0 for pid in top_bat_ids}
    bat_top10_count = {pid: 0 for pid in top_bat_ids}

    for i in range(n_iterations):
        # Match-level cluster sampling with replacement
        sampled = np.random.choice(match_ids, size=len(match_ids), replace=True)
        sample_df = pd.DataFrame({"match_id": sampled})
        b_merged = sample_df.merge(bat_match, on="match_id", how="inner")

        # Distinct matches preserved by nunique on original match_id
        agg = b_merged.groupby("striker_id", as_index=False).agg(
            p_runs=("pressure_runs", "sum"),
            p_balls=("pressure_balls", "sum"),
            tot_runs=("batter_runs", "sum"),
            tot_balls=("balls_faced", "sum"),
            matches=("match_id", "nunique"),
        )

        # Eligibility recalculated per iteration
        elig = agg[(agg["p_balls"] >= 12) & (agg["matches"] >= 3)].copy()
        if elig.empty:
            continue

        p_sr = 100.0 * elig["p_runs"] / np.maximum(elig["p_balls"], 1)
        norm_balls = np.maximum(elig["tot_balls"] - elig["p_balls"], 1)
        norm_runs = np.maximum(elig["tot_runs"] - elig["p_runs"], 0)
        norm_sr = 100.0 * norm_runs / norm_balls
        diff = p_sr - norm_sr

        s = np.median(np.abs(diff))
        if s == 0 or np.isnan(s):
            s = 1.0
        perf = 50.0 + 50.0 * np.tanh(diff / (2.0 * s))
        rel = 100.0 * elig["p_balls"] / (elig["p_balls"] + 30.0)

        elig["spi"] = 0.65 * perf + 0.35 * rel
        elig["rank"] = elig["spi"].rank(ascending=False, method="min")

        rank_dict = elig.set_index("striker_id")["rank"].to_dict()
        for pid in top_bat_ids:
            if pid in rank_dict:
                r = rank_dict[pid]
                bat_eligible_count[pid] += 1
                bat_ranks[pid].append(r)
                if r <= 10:
                    bat_top10_count[pid] += 1

    batter_summary = {}
    for pid in top_bat_ids:
        elig_pct = 100.0 * bat_eligible_count[pid] / n_iterations
        top10_pct = 100.0 * bat_top10_count[pid] / n_iterations
        ranks = bat_ranks[pid]
        med = float(np.median(ranks)) if ranks else None
        p10 = float(np.percentile(ranks, 10)) if ranks else None
        p90 = float(np.percentile(ranks, 90)) if ranks else None
        batter_summary[str(pid)] = {
            "player_id": pid,
            "player_name": bat_names.get(pid, str(pid)),
            "eligibility_probability_pct": elig_pct,
            "top10_inclusion_probability_pct": top10_pct,
            "conditional_rank_median": med,
            "conditional_rank_p10": p10,
            "conditional_rank_p90": p90,
        }

    # Storage for Bowlers
    bowl_ranks = {pid: [] for pid in top_bowl_ids}
    bowl_eligible_count = {pid: 0 for pid in top_bowl_ids}
    bowl_top10_count = {pid: 0 for pid in top_bowl_ids}

    for i in range(n_iterations):
        sampled = np.random.choice(match_ids, size=len(match_ids), replace=True)
        sample_df = pd.DataFrame({"match_id": sampled})
        b_merged = sample_df.merge(bowl_match, on="match_id", how="inner")

        agg = b_merged.groupby("bowler_id", as_index=False).agg(
            p_runs=("pressure_runs", "sum"),
            p_balls=("pressure_balls", "sum"),
            tot_runs=("runs_conceded", "sum"),
            tot_balls=("legal_balls", "sum"),
            matches=("match_id", "nunique"),
        )

        elig = agg[(agg["p_balls"] >= 12) & (agg["matches"] >= 3)].copy()
        if elig.empty:
            continue

        p_econ = 6.0 * elig["p_runs"] / np.maximum(elig["p_balls"], 1)
        norm_balls = np.maximum(elig["tot_balls"] - elig["p_balls"], 1)
        norm_runs = np.maximum(elig["tot_runs"] - elig["p_runs"], 0)
        norm_econ = 6.0 * norm_runs / norm_balls
        diff = norm_econ - p_econ

        s = np.median(np.abs(diff))
        if s == 0 or np.isnan(s):
            s = 1.0
        perf = 50.0 + 50.0 * np.tanh(diff / (2.0 * s))
        rel = 100.0 * elig["p_balls"] / (elig["p_balls"] + 30.0)

        elig["spi"] = 0.65 * perf + 0.35 * rel
        elig["rank"] = elig["spi"].rank(ascending=False, method="min")

        rank_dict = elig.set_index("bowler_id")["rank"].to_dict()
        for pid in top_bowl_ids:
            if pid in rank_dict:
                r = rank_dict[pid]
                bowl_eligible_count[pid] += 1
                bowl_ranks[pid].append(r)
                if r <= 10:
                    bowl_top10_count[pid] += 1

    bowler_summary = {}
    for pid in top_bowl_ids:
        elig_pct = 100.0 * bowl_eligible_count[pid] / n_iterations
        top10_pct = 100.0 * bowl_top10_count[pid] / n_iterations
        ranks = bowl_ranks[pid]
        med = float(np.median(ranks)) if ranks else None
        p10 = float(np.percentile(ranks, 10)) if ranks else None
        p90 = float(np.percentile(ranks, 90)) if ranks else None
        bowler_summary[str(pid)] = {
            "player_id": pid,
            "player_name": bowl_names.get(pid, str(pid)),
            "eligibility_probability_pct": elig_pct,
            "top10_inclusion_probability_pct": top10_pct,
            "conditional_rank_median": med,
            "conditional_rank_p10": p10,
            "conditional_rank_p90": p90,
        }

    output = {
        "status": "completed",
        "n_iterations": n_iterations,
        "seed": seed,
        "scoped_matches_with_deliveries": len(match_ids),
        "sampling_unit": "match_id (cluster bootstrap with replacement)",
        "distinct_matches_rule": "nunique(match_id) in resample",
        "eligibility_recalculation": "Recalculated every iteration (p_balls >= 12 and matches >= 3)",
        "ineligible_handling": "Excluded from conditional rank distributions; tracked in eligibility_probability_pct",
        "batters": batter_summary,
        "bowlers": bowler_summary,
    }

    out_path = REPORTS / "bootstrap_validation.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    res = run_bootstrap(n_iterations=1000, seed=42)
    print(f"Completed {res['n_iterations']} bootstrap iterations successfully.")

