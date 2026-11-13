# Project Audit

## Scope and evidence

This update reviewed the existing source modules, generated data, reports, and
dashboard before implementing Tasks 11–20 from the supplied task specification.
The repository does not contain `MASTER_SPECIFICATION.md`; earlier project
status documents cite the previously supplied 818-line snapshot. The official
Rajasthan Royals problem statement is not available, so official rules and
scope cannot be asserted.

## Verified foundations from Tasks 1–10

- Six-source read-only ETL and validation; curated match state, pressure
  deliveries, and player metrics are present.
- Existing local MapReduce and Spark pipelines and prior parity reports are
  retained; they are simulations/local runtime, not Hadoop/HDFS or a cluster.
- Pressure modeling, player metrics, provisional SPI, top-ten generation, and
  a prior evidence report existed before this increment.
- Raw inputs are preserved; an automated SHA-256 comparison now checks all six
  CSVs against the ETL lineage manifest.

## Tasks 11–20 implementation evidence

- SPI/ranking generation now exports exact top-ten files, full ranked lists,
  all batter/bowler metric CSVs, competition evidence, sensitivity, and
  component-correlation diagnostics. Methodology remains provisional.
- Decision Tree and Random Forest boundary models use a match-grouped holdout;
  K-means clustering exports metrics, cluster profiles, and HTML plots.
- Cassandra CQL and HBase shell design examples document access patterns and
  CAP/schema concepts. No database server or driver is installed or claimed.
- Historical streaming simulation processed 194,014 events in 1,660 innings
  with zero ordering, state, and pressure mismatches against batch-enriched
  records. No Kafka producer/consumer service was run.
- A player-match graph based on observed deliveries produced 1,728 nodes,
  36,318 directed edges, PageRank results, and an HTML visualization.
- The Streamlit app retains its original four views and adds Pressure
  Analytics, Player Insights, Methodology, Final Methodology & Validation,
  and AI Cricket Analyst views. Filters, exported ranking views, and both
  themes were checked in AppTest and the live browser.
- The AI analyst has local supported-intent calculations and an optional
  provider-backed tool loop. It discovers 20 datasets and exposes guarded,
  bounded SELECT queries plus existing role metrics; live LLM behavior has
  not been tested because credentials are unavailable.
- The expanded methodology report, README, architecture diagrams, submission
  assessment, and presentation outline were generated.

## Test evidence

- `.venv/bin/python -m unittest discover -s tests -v`: **51 tests passed**,
  including analyst-tool tests and dashboard AppTest.
- Project-wide Python compilation: **passed**.
- AppTest rendered all nine views, switched themes, and returned a real
  historical-player answer without app exceptions.
- Live browser on port 8502 rendered the AI tab and verified a Rinku Singh
  result with 14 match-level evidence rows. This checks local analytics, not
  the external LLM. Port 8501 was already occupied by the existing server and
  was not interrupted.
- Ranking exports have exactly ten unique player IDs and sequential ranks for
  each role. A test independently recomputes one top batter’s pressure strike
  rate and one top bowler’s pressure economy from delivery rows.
- Prior ETL evidence: 38 checks passed, five warnings, no validation failures.

## Remaining blockers

- The official problem statement and domain approval for pressure/SPI
  assumptions are missing. Top-ten lists are not final official selections.
- Hadoop/HDFS, Kafka, Cassandra, and HBase live demonstrations remain
  unavailable; the current local replay and schema documents must not be
  represented as those services.
- The project specification does not identify 14 dashboard page names; this
  dashboard implements nine integrated views rather than inventing pages.
- Dashboard screenshots and the optional video have not been saved as project
  deliverables.

Detailed line-item statuses and executed commands are in
[`MASTER_IMPLEMENTATION_STATUS.md`](./MASTER_IMPLEMENTATION_STATUS.md) and
[`PROJECT_PROGRESS.md`](./PROJECT_PROGRESS.md). Ranking evidence is in
[`../reports/methodology_report.md`](../reports/methodology_report.md).

## Final methodology and validation increment

The current user request specifies historical IPL and T20I records from
2022-01-01. The official Round 1 Problem Statement and `MASTER_SPECIFICATION.md`
were searched for but are absent; this report therefore does not claim that
the current scope or methodology is officially approved.

- New `analytics/final_validation.py` independently recalculates scoped raw
  delivery totals, batter/team runs, legal balls, bowler-conceded runs,
  bowler wickets, boundaries, and delivery targets, then compares them to
  curated Parquet. Across 194,014 deliveries there are zero mismatches in the
  checked fields, zero orphan rows, and raw input hashes match the ETL
  manifest. This is arithmetic reconciliation against the same source, not an
  external scorecard oracle.
- Scope is 853 matches: 371 IPL and 482 T20I. Four flags disagree with
  `runs == 4` on 20 records and six flags disagree with `runs == 6` on 3.
  Two records have extra runs but no extras type; 260 `other` extras rows are
  unresolved. Source records remain unchanged.
- New sensitivity evidence tests event thresholds 40/50/60, a model with the
  closeness component removed, equal pressure-component weights, eligibility
  alternatives, and multiple SPI weight sets including reliability removal.
  At thresholds 40/60, top-ten Jaccard overlap against threshold 50 is 0.176
  for batters and 0.053 for bowlers. Removing closeness yields 0.429 and 0.000.
- Pressure component correlation flags wickets/time overlap at absolute
  Spearman rho 0.768 for both roles. The current closeness term peaks at rate
  parity and overlaps rate difficulty; bowling wickets remaining may measure
  opportunity rather than pressure. These are concerns for domain review,
  not reasons to tune player outcomes.
- The SPI formula is independently recomputed from player metric rows for the
  exported top tens with maximum absolute error 0.0. Exposure is used both in
  performance shrinkage and reliability; 60/20/20 remains provisional.
- Ranking run ID is `9f00984a3cdd119a3b48` for methodology version
  `pressure-spi-v1-provisional`. Exact CSV hashes, input hashes, scenario ranks
  and score changes are recorded in `reports/final_rankings.json`.
- `dashboard/app.py` adds the eighth view, `Final Methodology & Validation`,
  including actual event contributions, sensitivity, raw/curated checks,
  exact ranking CSVs and downloads, evidence, hashes, and an explicitly
  provisional readiness checklist.

Generated evidence: `reports/final_validation.json` and the updated
`reports/methodology_report.md`. The official approval remains blocked.

## AI Cricket Analyst increment

- Added `analytics/cricket_analyst.py` and the ninth dashboard view in
  `dashboard/app.py`. It reuses the curated pressure-delivery data and
  `calculate_player_metrics()` / `rank_players()` rather than duplicating the
  project formulas.
- Supported paths include pressure rankings, player profiles and
  comparisons, season/format comparisons, role/phase/team filters,
  consistency, reliability, sample eligibility, SPI explanations, and
  match-level pressure context. Ambiguous roles and requests without
  sufficient scope receive clarification or an explicit insufficient result.
- Every player result includes matching identifiers and match evidence;
  pressure rates and normal baselines are independently recomputed from
  filtered deliveries. SQL and database commands are rejected, and no
  generated SQL is executed.
- The optional OpenAI-compatible provider can classify an allowlisted query
  and generate qualitative commentary. Provider-selected IDs and filters are
  checked against the archive; numeric commentary is rejected. No API key was
  configured, so external model behavior was not exercised.
- Validation: 14 analyst unit tests and 34 total tests passed. Streamlit
  AppTest passed for all nine tabs, theme switching, and a real player query.
  The live browser on port 8502 rendered the AI tab, retained its selection
  after submission, and showed the Rinku Singh answer and supporting
  evidence. The external LLM provider was not configured or tested.
- Setup and feature limits are documented in `docs/AI_CRICKET_ANALYST.md`.
