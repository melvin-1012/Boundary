"""Build a traceable, explicitly provisional methodology report from outputs."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
QUALITY_REPORT = REPORTS / "data_quality_report.json"
RANKINGS_JSON = REPORTS / "final_rankings.json"
OUTPUT = REPORTS / "methodology_report.md"
RANKING_FILES = {
    "batter": REPORTS / "top_10_batters.csv",
    "bowler": REPORTS / "top_10_bowlers.csv",
}
FINAL_VALIDATION = REPORTS / "final_validation.json"


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _format_player_table(frame, role):
    if role == "batter":
        metric_title, pressure_metric, baseline_metric = (
            "Pressure SR",
            "pressure_strike_rate",
            "normal_strike_rate",
        )
    else:
        metric_title, pressure_metric, baseline_metric = (
            "Pressure econ.",
            "pressure_economy",
            "normal_economy",
        )
    columns = [
        ("rank", "Rank"),
        ("player_id", "Player ID"),
        ("player_name", "Player"),
        ("spi", "SPI"),
        (pressure_metric, metric_title),
        (baseline_metric, "Normal baseline"),
        ("pressure_opportunities", "Pressure balls"),
        ("pressure_matches", "Pressure matches"),
        ("reliability", "Reliability"),
        ("evidence_summary", "Evidence"),
    ]
    lines = ["| " + " | ".join(title for _, title in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in frame.to_dict("records"):
        cells = []
        for field, _ in columns:
            value = row[field]
            if field in {"spi", "reliability", pressure_metric, baseline_metric}:
                value = f"{float(value):.2f}"
            else:
                value = str(value).replace("|", "\\|").replace("\n", " ")
            cells.append(value)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_methodology_report(
    quality_report_path=QUALITY_REPORT,
    rankings_path=RANKINGS_JSON,
    ranking_files=RANKING_FILES,
    output_path=OUTPUT,
):
    quality = json.loads(Path(quality_report_path).read_text(encoding="utf-8"))
    ranking_run = json.loads(Path(rankings_path).read_text(encoding="utf-8"))
    final_validation = json.loads(FINAL_VALIDATION.read_text(encoding="utf-8"))
    if ranking_run.get("status") != "provisional":
        raise ValueError("This report generator is for provisional ranking runs only.")

    ranking_frames = {
        role: pd.read_csv(path) for role, path in ranking_files.items()
    }
    for role, frame in ranking_frames.items():
        expected_count = ranking_run["top_10_counts"][role]
        if (
            len(frame) != expected_count
            or frame["rank"].tolist() != list(range(1, len(frame) + 1))
            or not frame["player_id"].is_unique
        ):
            raise ValueError(f"{role} ranking CSV does not match the ranking manifest.")
    if ranking_run["input_sha256"] != final_validation["raw_input_sha256"]:
        raise ValueError("Ranking inputs do not match the independent validation hashes.")
    for role, path in ranking_files.items():
        if ranking_run["ranking_file_sha256"][f"{role}s"] != _sha256(path):
            raise ValueError(f"{role} CSV hash does not match the ranking manifest.")

    validation = quality["validation"]
    etl = quality["etl"]
    checks = validation["checks"]
    warnings = [check for check in checks if check["status"] == "warning"]
    profiles = validation["datasets"]
    inventory = "\n".join(
        f"| `{name}` | {profile['rows']:,} | {profile['columns']} |"
        for name, profile in profiles.items()
    )
    warning_list = "\n".join(
        f"- **{check['name']}:** {check['detail']}" for check in warnings
    ) or "- No validation warnings were recorded."
    output_hashes = {
        role: _sha256(path) for role, path in ranking_files.items()
    }
    sensitivity_sections = []
    for role in ("batter", "bowler"):
        scenarios = ranking_run["sensitivity"][role]
        lines = [
            f"### {role.title()} ranking sensitivity",
            "",
            "| Scenario | Pressure deliveries | Pressure opportunities | Eligible | Top-10 Jaccard |",
            "|---|---:|---:|---:|---:|",
        ]
        lines.extend(
            f"| {scenario['scenario']} | {scenario['pressure_event_count']} | "
            f"{scenario['pressure_opportunity_count']} | {scenario['eligible_players']} | "
            f"{scenario['top_10_overlap_jaccard']:.3f} |"
            for scenario in scenarios
        )
        lines.extend(["", "Top-ten membership and rank movement from baseline:"])
        for scenario in scenarios:
            changed = []
            for item in scenario["top_10_rank_changes"]:
                if item["baseline_rank"] == item["scenario_rank"] and (
                    item["spi_delta"] is None or abs(item["spi_delta"]) < 0.01
                ):
                    continue
                if item["baseline_spi"] is not None and item["scenario_spi"] is not None:
                    spi_change = (
                        f"; SPI {item['baseline_spi']:.2f} → {item['scenario_spi']:.2f} "
                        f"(Δ {item['spi_delta']:+.2f})"
                    )
                else:
                    spi_change = "; enters or leaves the top ten"
                changed.append(
                    f"ID {item['player_id']}: rank {item['baseline_rank']} → "
                    f"{item['scenario_rank']}{spi_change}"
                )
            lines.append(
                f"- **{scenario['scenario']}:** "
                + ("; ".join(changed) if changed else "no changes")
            )
        sensitivity_sections.append("\n".join(lines))
    correlation_sections = []
    for role in ("batter", "bowler"):
        diagnostics = ranking_run["correlation_diagnostics"][role]
        lines = [
            f"### {role.title()} SPI-component correlations",
            "",
            "| Component pair | Spearman rho | High-overlap flag (|rho| >= 0.70) |",
            "|---|---:|:---:|",
        ]
        lines.extend(
            f"| {pair['left']} / {pair['right']} | "
            f"{pair['spearman_rho']:.3f} | {pair['high_overlap_flag']} |"
            for pair in diagnostics["spearman_pairs"]
        )
        correlation_sections.append("\n".join(lines))
    pressure_sections = []
    for role in ("batter", "bowler"):
        diagnostics = ranking_run["pressure_diagnostics"][role]
        lines = [
            f"### {role.title()} pressure component correlation and contribution",
            "",
            "| Component pair | Spearman rho | High-overlap flag |",
            "|---|---:|:---:|",
        ]
        lines.extend(
            f"| {pair['left']} / {pair['right']} | "
            f"{pair['spearman_rho']:.3f} | {pair['high_overlap_flag']} |"
            for pair in diagnostics["component_spearman_pairs"]
        )
        lines.extend(
            [
                "",
                "| Component | Weight | Mean normalized value | Mean score points |",
                "|---|---:|---:|---:|",
            ]
        )
        lines.extend(
            f"| {component} | {item['weight']:.3f} | "
            f"{item['mean_normalized_component']:.3f} | {item['mean_score_points']:.2f} |"
            for component, item in diagnostics["mean_normalized_contributions"].items()
        )
        pressure_sections.append("\n".join(lines))
    independent_spi_lines = [
        f"- **{role.title()}:** {check['sample_player_count']} recalculated, "
        f"maximum absolute SPI difference {check['maximum_absolute_spi_error']:.12g}; "
        f"pass={check['independent_recalculation_passed']}."
        for role, check in ranking_run["independent_spi_checks"].items()
    ]
    cricket_validation_lines = [
        f"- **{field}:** {detail['matched_rows']:,} matched rows, "
        f"{detail['mismatch_rows']} mismatches."
        for field, detail in final_validation["independent_raw_to_curated_comparison"].items()
        if isinstance(detail, dict) and "mismatch_rows" in detail
    ]
    pressure_sample_lines = [
        "| Role | Match | Innings / delivery | Pre-event score | Wickets / balls before | Req. / reference rate | Score | Weighted components |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for role in ("batter", "bowler"):
        sample = ranking_run["pressure_diagnostics"][role]["sample_event"]
        if sample is None:
            continue
        parts = ", ".join(
            f"{name}={detail['normalized_value']:.3f}×{detail['weight']:.2f}"
            f" ({detail['score_points']:.1f})"
            for name, detail in sample["components"].items()
        )
        req_rate = (
            "n/a"
            if sample["required_run_rate"] is None
            else f"{sample['required_run_rate']:.2f}"
        )
        pressure_sample_lines.append(
            f"| {role.title()} | {sample['match_id']} | "
            f"{sample['innings']} / {sample['innings_ball_num']} | "
            f"{sample['score_before']:.0f} | {sample['wickets_before']} / "
            f"{sample['legal_balls_before']} | {req_rate} / "
            f"{sample['reference_run_rate']:.2f} | {sample['pressure_score']:.2f} | {parts} |"
        )

    ml_path = REPORTS / "machine_learning" / "evaluation.json"
    replay_path = REPORTS / "streaming" / "replay_validation.json"
    graph_path = REPORTS / "graph" / "graph_summary.json"
    ml_evidence = json.loads(ml_path.read_text(encoding="utf-8")) if ml_path.exists() else None
    replay_evidence = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.exists() else None
    graph_evidence = json.loads(graph_path.read_text(encoding="utf-8")) if graph_path.exists() else None

    report = f"""# SupeRR Intelligence — Methodology and Ranking Evidence

> **PROVISIONAL — NOT AN OFFICIAL FINAL SUBMISSION.** The official Rajasthan
> Royals Round 1 Problem Statement and `MASTER_SPECIFICATION.md` are not in the
> workspace, so official rules cannot be confirmed. This run applies the
> current request's IPL and T20I archive from 2022-01-01. Pressure weights,
> threshold, eligibility floors, and source-field interpretations remain
> provisional and materially affect the selections.

**Methodology version:** `{ranking_run['methodology_version']}`  
**Ranking run ID:** `{ranking_run['ranking_run_id']}`  
**Submission status:** provisional; not approved as final official rankings.

## 1. Objective and source scope

The requested objective is to identify pressure-performing batters and
bowlers from the supplied historical IPL and T20I archive dated on or after
2022-01-01. The official brief is unavailable, so this is the scope stated in
the current request, not a verified quotation of official rules. The selected
scope contains {final_validation['scope']['ipl_matches']} IPL matches and
{final_validation['scope']['t20i_matches']} T20I matches, totalling
{final_validation['scope']['selected_deliveries']:,} deliveries.

## 2. Dataset inventory and validation

| Source file | Rows | Columns |
|---|---:|---:|
{inventory}

Validation completed with **{validation['summary']['passed_checks']} passing
checks, {validation['summary']['warnings']} warnings, and
{validation['summary']['failures']} failures**.

{warning_list}

Raw input values are read without row-level edits. Processed Parquet outputs
are written outside `data/raw/`. The ETL records an execution timestamp,
pipeline version, input filenames, SHA-256 hashes, selected scope, and output
paths in `data_quality_report.json`.

## 2a. Cleaning policy and source interpretation

The pipeline preserves original source files and records derived state in
separate Parquet outputs. It does not silently deduplicate source rows or
rewrite ambiguous source fields. `wide` and `Overstep` are excluded from legal
balls; wides do not count as batter balls faced. Byes, leg-byes, and penalty
extras are excluded from bowler-conceded runs; only the explicitly enumerated
bowler-credited dismissals count as bowler wickets. These are documented
working interpretations, not a substitute for official field definitions.
The data-quality report retains warnings for duplicated playing-eleven
candidate keys, boundary-flag disagreements, missing delivery rows, delivery
ordering anomalies, and a nonzero runs value on a leg-byes record.

## 3. Match-state and pressure definition

For each delivery, state is calculated before the event: score, wickets, legal
balls, balls remaining, target, runs required, current/required run rate,
innings phase, and the participating batter and bowler. Team runs are
`runs + extras1_runs + extras_2_runs`. `wide` and `Overstep` are excluded from
legal-ball counts; batter balls exclude wides. Innings 3 and 4 are modeled as
one-over super overs. The target is the preceding innings total plus one,
except an available revised target overrides the second-innings target.

Pressure is an explicitly heuristic 0–100 score, not a match-win probability.
For chase state, `r = required run rate / prior reference run rate`:

- Batting components: run-rate `clip((r - 1) / 1.5, 0, 1)`, wickets lost / 10,
  innings progress, and `exp(-abs(r - 1))`.
- Bowling components: run-rate `clip((1 - r) / 1.5, 0, 1)`, wickets remaining /
  10, innings progress, and `exp(-abs(r - 1))`.
- First innings use current run rate versus the prior reference rate. The
  run-rate component is clipped to `[0, 1]` and multiplied by innings progress;
  closeness is `exp(-abs(current - reference) / reference) * progress`.

Batting component weights are 0.35/0.25/0.20/0.20; bowling weights are
0.30/0.25/0.20/0.25. A score of at least 50 is labeled pressure. The reference
is the median of prior first-innings rates in the same format, with fallback
rates of 8.0 for T20 and 7.5 for T20I until five prior observations exist.
The rate-difficulty term is higher for a batter as required rate rises above
the reference, and higher for a bowler as it falls below it. The wickets term
uses wickets lost for batting and wickets remaining for bowling. The time
term is innings progress. Closeness is `exp(-abs(rate_ratio - 1))` in a chase
and an analogous normalized current/reference rate in the first innings.

The role-specific run-rate and wickets directions are deliberate, but the
same time and closeness semantics do not establish equal role fairness.
Closeness peaks at rate parity and is partly redundant with rate difficulty;
bowling wickets remaining may describe wicket-taking opportunity rather than
bowling pressure. These are validity concerns, not a basis for a preferred
ranking. Keep the current formula only as a transparent provisional baseline;
review the constructs with a cricket domain expert before adoption.

Weights, threshold, innings handling, and alternatives are measured below.
Each actual event example gives normalized component values, weights, and
weighted score-point contributions. Full samples and component diagnostics
are in `reports/final_rankings.json`.

### Pressure component diagnostics

{chr(10).join(pressure_sections)}

### Actual pressure-event calculations

{chr(10).join(pressure_sample_lines)}

## 4. Player metrics and baselines

Batting outputs include pressure runs and balls, strike rate, boundary and
dot-ball rates, outs, normal-versus-pressure performance, pressure innings,
and exposure. Bowling outputs include legal balls, conceded runs, bowler-
credited wickets, pressure economy, pressure dots/boundaries, and exposure.
Byes, leg-byes, and penalty extras are excluded from bowler-conceded runs;
Bowled, Caught, LBW, Stump, and Hit Wicket are counted as bowler wickets.

Pressure and normal rates are shrunk toward competition-level baselines using
a 30-ball prior. Small samples are damped by reliability
`n / (n + 30)`, where `n` is pressure-ball exposure. Match consistency is
`100 / (1 + CV)` across match-level pressure rates. The uncertainty indicator
`1 / sqrt(n)` is only a relative sample-size proxy, not a confidence interval.
The batter baseline is competition-adjusted pressure strike rate minus normal
strike rate; the bowler direction is normal economy minus pressure economy, so
positive values mean better relative pressure performance for either role.
Batters use balls faced as pressure opportunities; bowlers use legal balls.

## 5. SPI and ranking procedure

The provisional composite score is:

`SPI = 0.60 * performance_component + 0.20 * consistency + 0.20 * reliability`

The performance component is `50 + 50 * tanh(adjusted_difference / (2 * s))`,
where the adjusted difference is competition-adjusted and shrunk by exposure,
and `s` is the median absolute adjusted difference among eligible candidates
(falling back to 1 if degenerate). Higher batter pressure strike rate is
preferred; lower bowler pressure economy is preferred through the stored
normal-versus-pressure difference direction.

Eligibility currently requires pressure exposure in at least three distinct
matches and 12 pressure balls. Both roles have at least 10 eligible candidates.
The ranking generator checks that each exported list has ten unique player IDs
and sequential ranks 1–10. This verifies file shape, not methodological
validity.
The current run contains {ranking_run['eligible_counts']['batter']} eligible
batters and {ranking_run['eligible_counts']['bowler']} eligible bowlers.
Exports include `top_10_batters.csv`, `top_10_bowlers.csv`, full ranking CSVs,
and supporting player-metric tables in `reports/`.

### Top 10 batters

{_format_player_table(ranking_frames['batter'], 'batter')}

### Top 10 bowlers

{_format_player_table(ranking_frames['bowler'], 'bowler')}

The CSV outputs contain the per-player competition scope, full metric values,
reliability, and generated evidence summary. Their recorded SHA-256 digests are:

- Batters: `{output_hashes['batter']}`
- Bowlers: `{output_hashes['bowler']}`

## 6. Sensitivity, fairness, and limitations

The ranking generator evaluates performance/consistency/reliability weight
changes, including removing the reliability component; eligibility thresholds;
pressure thresholds of 40 and 60; equal pressure-component weights; and a
closeness-removed alternative. Jaccard overlap is the fraction of shared
players in the top-ten sets; lower overlap indicates greater sensitivity.

No player reputation, team popularity, or identity-based preference is used in
the SPI formula. Performance is compared with competition-level baselines and
small pressure samples are shrunk toward those baselines. Exposure still varies
by role, competition, and opportunity; the reliability adjustment cannot
remove schedule or selection bias. The input archive’s coverage and the
unconfirmed official scope limit fairness claims.

{chr(10).join(sensitivity_sections)}

### Correlation diagnostics

The SPI has one performance-difference component plus consistency and
reliability. The following Spearman diagnostics are calculated among eligible
candidates; flagged overlap is a review signal, not proof of duplicate
constructs or a statistical correction:

{chr(10).join(correlation_sections)}

Independent SPI recalculation from underlying role metrics:

{chr(10).join(independent_spi_lines)}

Reliability and performance shrinkage both depend on pressure exposure, so the
60/20/20 formula may count sample size more than once. Consistency is also
measured on a pressure-rate outcome, which may correlate with performance.
The code tests a reliability-removed alternative rather than presuming 60/20/20
is defensible. Sensitivity results inform review; they are not used to select
weights based on preferred player names.

The results are sensitive to modeling choices. The scoring weights and
eligibility policy have not been approved by a domain expert or benchmarked
against official pressure labels. `runs` attribution on some non-batter extras,
source boundary flags, `other` extras, revised-overs semantics, and super-over
interpretation remain limitations. The pressure score and SPI must not be
described as validated probabilities or official selection criteria.

## 7. Independent checks and supplementary demonstrations

Raw-to-curated validation independently re-derived batter runs, team runs,
legal balls, bowler-conceded runs, bowler wickets, boundary flags and targets
from the scoped raw deliveries:

{chr(10).join(cricket_validation_lines)}

Raw hashes match the ETL manifest: **{final_validation['raw_hashes_match_etl_manifest']}**.
Source runs total {final_validation['run_and_extras']['source_runs_sum']:,},
team runs total {final_validation['run_and_extras']['team_runs_sum']:,}, and
the difference is the recorded extras sum. There are
{final_validation['run_and_extras']['records_with_extras_runs_but_no_extras_type']}
rows with extras runs but no extras type and
{final_validation['delivery_rules']['unknown_other_extra_deliveries']} `other`
extras rows whose attribution remains ambiguous. The scoped records include
{final_validation['boundaries']['four_flag_mismatches_against_source_runs_equals_4']}
four-flag and
{final_validation['boundaries']['six_flag_mismatches_against_source_runs_equals_6']}
six-flag disagreements against source runs. Of
{final_validation['wickets']['dismissal_counts'].get('RunOut', 0)} run-outs,
none are credited to bowlers under the current policy.

The SPI values were independently recomputed from underlying role metrics:

{chr(10).join(independent_spi_lines)}

These are reproducible arithmetic comparisons, not external scorecard or
domain validation. Not-out opportunity counts are approximate because the
source does not provide authoritative batting innings scorecards. Innings 4
targets match innings 3 total plus one in the tested rows; revised target
semantics have no independent official documentation.

Raw input hashes and validation results are in `reports/final_validation.json`.
Ranking output SHA-256 values are `{ranking_run['ranking_file_sha256']['batters']}`
(batters) and `{ranking_run['ranking_file_sha256']['bowlers']}` (bowlers).
Ranking run ID: `{ranking_run['ranking_run_id']}`.

"""
    if ml_evidence is not None:
        report += f"""An exploratory decision tree and random forest classify
whether a delivery is a four or six using pre-delivery features and a grouped
match-held-out split. The holdout contains
{ml_evidence['classification']['split']['test_matches']} matches with
{ml_evidence['classification']['split']['match_overlap']} train/test match
overlaps. Test balanced accuracy is
{ml_evidence['classification']['models']['decision_tree']['balanced_accuracy']:.3f}
for the decision tree and
{ml_evidence['classification']['models']['random_forest']['balanced_accuracy']:.3f}
for the random forest. K-means clustering is exploratory and remains outside
the SPI formula. Detailed metrics and visualizations are in
`reports/machine_learning/`.

"""
    else:
        report += "ML demonstrations were not generated for this report run.\\n\\n"
    if replay_evidence is not None:
        report += f"""A deterministic historical replay processed
{replay_evidence['delivery_count']:,} deliveries across
{replay_evidence['innings_count']:,} innings; incremental score/wicket/legal
ball state and recalculated weighted pressure had
{replay_evidence['ordering_errors']} ordering errors,
{replay_evidence['state_mismatches']} state mismatches, and
{replay_evidence['pressure_mismatches']} pressure mismatches. This is a local
simulation using batch-enriched event envelopes, not a Kafka deployment.

"""
    else:
        report += "The historical streaming replay was not generated for this report run.\\n\\n"
    if graph_evidence is not None:
        report += f"""A supplementary player-match graph contains
{graph_evidence['nodes']:,} nodes and {graph_evidence['edges']:,} directed
edges. PageRank is interpreted as network participation, not player quality;
its results are excluded from SPI and ranking exports. See
`reports/graph/graph_summary.json` and the generated graph visualization.

"""
    else:
        report += "Graph/PageRank outputs were not generated for this report run.\\n\\n"
    report += """Cassandra and HBase have query-oriented schema/command design
artifacts in `databases/`; no database service or driver was available, so no
live operation is claimed.

## 8. Reproducibility

From the project root, using the existing virtual environment:

```bash
.venv/bin/python -m ingestion.run_etl
.venv/bin/python -m analytics.build_rankings
.venv/bin/python -m machine_learning.run_models
.venv/bin/python -m streaming.replay
.venv/bin/python -m graph_analytics.run_graph
.venv/bin/python -m analytics.build_methodology_report
.venv/bin/python -m hadoop.run_mapreduce
.venv/bin/python -m spark.run_spark
```

These commands produce local Parquet/CSV/JSON outputs. The MapReduce runner
uses local Python subprocesses, not a Hadoop cluster. Spark uses
`local[2]`, not a multi-node deployment. Rankings and this report must be
regenerated together after any methodology or data change.

## 9. Ranking-run manifest

- Ranking status: **{ranking_run['status']}**
- Ranking run timestamp (UTC): `{ranking_run['created_at_utc']}`
- Selected counts: {ranking_run['top_10_counts']['batter']} batters and
  {ranking_run['top_10_counts']['bowler']} bowlers
- Eligible counts: {ranking_run['eligible_counts']['batter']} batters and
  {ranking_run['eligible_counts']['bowler']} bowlers
- ETL run timestamp (UTC): `{etl['run_timestamp_utc']}`
- ETL pipeline version: `{etl['pipeline_version']}`
- Validation report: `reports/data_quality_report.json`
- Ranking manifest: `reports/final_rankings.json`

## 10. Conclusion and submission readiness

The pipeline now produces reproducible, evidence-bearing exploratory
rankings and local demonstrations for machine learning, event replay, and
graph analytics. These outputs demonstrate implementation, not official
hackathon compliance or validated player selection. Final submission
readiness remains **BLOCKED** until the official Rajasthan Royals statement
and methodology/source-semantic review are available. Live Hadoop/HDFS,
Cassandra, HBase, and Kafka execution also remains unavailable in this
environment.
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote provisional methodology report: {output_path}")
    return output_path


if __name__ == "__main__":
    build_methodology_report()
