# Round 1 Submission Readiness

## Required deliverables

The supplied Round 1 brief requires:

1. A distinct, ordered top-10 batter list and top-10 bowler list, selected on
   Unstop.
2. A methodology report explaining the pressure definition, performance
   measures and baselines, fair comparisons, supporting evidence, reliability,
   limitations, and enough detail to reproduce the approach.

The brief explicitly leaves pressure definition to the team. It does not
require a particular dashboard, machine-learning model, distributed service,
or external domain approval.

## Current project outputs

- `reports/top_10_batters.csv` and `reports/top_10_bowlers.csv` contain ten
  unique player IDs each, sequential ranks 1–10, and names to reconcile with
  the Unstop dropdown choices.
- `reports/methodology_report.md` explains the selected pressure model,
  role-specific metrics, baselines, eligibility, SPI, pressure-versus-ordinary
  context distributions, sensitivity, limitations, and reproduction commands.
- `reports/top_10_match_evidence.csv` provides match-level pressure and
  ordinary performance for top-ten players.
- `reports/final_rankings.json` contains run provenance, top-ten validation,
  sensitivity scenarios, and the pressure-context diagnostics.
- Raw-to-curated validation and source hashes are in
  `reports/final_validation.json`.

The ranking method remains provisional because its weights, threshold,
eligibility policy, and some source-field interpretations are analyst choices.
The Round 1 brief permits the team to define pressure; this project does not
claim that its chosen score is an objectively validated pressure probability.
Sensitivity results are included so the impact of those choices is visible.

## Before selecting the Unstop rankings

1. Compare each exported player name with the available Unstop choice and
   select the same ten players in the same order. Do not rely on reputation or
   abbreviated names; use player IDs in the CSVs to distinguish names where
   needed.
2. Confirm that the report's batter and bowler lists exactly match the
   selections.
3. Review the report's data caveats and sensitivity findings. Do not describe
   scenario inclusion rates or uncertainty proxies as probabilities or
   confidence intervals.
4. Regenerate rankings, validation, and report together after any methodology
   or data change.

Core regeneration sequence from the project root:

```bash
.venv/bin/python -m ingestion.run_etl
.venv/bin/python -m analytics.build_rankings
.venv/bin/python -m analytics.final_validation
.venv/bin/python -m analytics.build_methodology_report
```

Screenshots, a video, live Hadoop/Kafka/database services, and extra dashboard
pages are not listed as required deliverables in the supplied Round 1 brief.
