
# SupeRR Intelligence — Project Progress

## Latest increment: AI Cricket Analyst

**Status:** Implemented and locally tested, but **not an officially validated
final submission**. The official Rajasthan Royals Round 1 Problem Statement
and `MASTER_SPECIFICATION.md` are not in the repository/workspace. The latest
increment adds the tested AI Cricket Analyst tab and safe read-only analytics.
The existing pressure/SPI methodology remains provisional and needs domain
approval.

### Prior methodology validation run

- Selected scope: 853 matches (371 IPL, 482 T20I), 194,014 deliveries.
- All six raw input SHA-256 values match the ETL lineage manifest.
- Raw-to-curated independent arithmetic checks: zero mismatches across
  batter runs, team runs, legal-ball flags, bowler-conceded runs, bowler
  wickets, boundary flags, and reconstructed targets; no orphan rows.
- Source warnings remain: 20 four-flag and 3 six-flag disagreements in scope;
  2 rows have extra runs but no extra type; 260 `other` extras remain
  ambiguous. Not-out counts are approximate because the source has no
  authoritative innings scorecard. No raw file was modified.
- Ranking run ID: `9f00984a3cdd119a3b48`; methodology:
  `pressure-spi-v1-provisional`.
- Eligible players: 272 batters, 336 bowlers. Both CSVs contain exactly 10
  unique player IDs ranked 1–10. Independent SPI recalculation from the
  underlying metric tables has maximum absolute error 0.0 for each role.
- Threshold sensitivity is high: top-ten Jaccard overlap between threshold 50
  and thresholds 40 / 60 is 0.176 for batters and 0.053 for bowlers. The
  closeness-removed alternative overlaps 0.429 for batters and 0.000 for
  bowlers. Treat the results as provisional, not approved selections.
- Pressure component correlation flags a wickets/time association with
  `|Spearman rho| = 0.768` for both roles. SPI reliability and performance
  both depend on exposure; 60/20/20 is therefore not assumed to be justified.

### Files and outputs

- `analytics/final_validation.py` and `reports/final_validation.json`:
  independent raw-data arithmetic, source-hash provenance, and limitations.
- `analytics/build_rankings.py` and `reports/final_rankings.json`:
  deterministic run identity, ranking hashes, pressure/SPI sensitivities,
  correlations, actual sample-event contributions, and independent SPI checks.
- `analytics/build_methodology_report.py` and
  `reports/methodology_report.md`: regenerable report tied to the same run and
  exact top-ten CSV files.
- `dashboard/app.py`: eighth `Final Methodology & Validation` tab with scope,
  actual pressure contribution examples, sensitivity, source warnings,
  exact ranking CSVs/downloads, evidence, hashes, and readiness checklist.
- `tests/test_final_validation.py`, `tests/test_cricket_analytics.py`, and
  `tests/test_dashboard_app.py`: independent checks and coverage for the new
  output/tab.

### Commands executed

```text
.venv/bin/python -m analytics.build_rankings
.venv/bin/python -m analytics.final_validation
.venv/bin/python -m analytics.build_methodology_report
.venv/bin/python -m py_compile dashboard/app.py analytics/build_rankings.py analytics/build_methodology_report.py analytics/final_validation.py
```

The final-methodology increment passed 20 tests. Browser checks rendered the
app and its tabs, but the final validation tab itself could not be selected
because it was beyond the horizontally scrollable tab bar in the available
viewport. This is a known verification gap.

### Open decisions / limitations

1. Provide the official problem statement and authoritative competition scope.
2. Obtain cricket-domain review of pressure indicators, event cutpoint,
   innings/revised-target and super-over conventions, and eligibility.
3. Review potential double-counting in the 60/20/20 SPI and its exposure
   adjustment; do not promote the current list as final.
4. Clarify `other` extras, two extra-run rows with no extras type, boundary
   flag disagreements, and official batting opportunity/not-out semantics.
5. Local arithmetic validation cannot replace an independent scorecard oracle.

## AI Cricket Analyst increment

- The existing `analytics/cricket_analyst.py` local parser and evidence
  calculations remain available. Provider-backed dynamic analysis is
  implemented in `analytics/analyst_tools.py` and uses structured,
  allowlisted tool calls for catalog discovery, schema inspection, entity
  lookup, existing batter/bowler metrics, and bounded read-only SQL.
- The tool loop supports up to eight rounds and twelve total calls, includes
  recent conversation context, and returns inspectable tool results. SQLite
  queries are constrained to registered dataframes, known columns, approved
  functions, a 3-second timeout, and a 500-row result limit. Source data is
  never modified.
- The ninth dashboard view selects dynamic tool calling when a compatible
  provider is configured and retains the local supported-intent path otherwise.
  The UI displays tool activity/results and continues to show application-
  calculated metrics separately from model prose.
- No live LLM credentials were configured. Mocked tests cover multi-step tool
  dispatch, follow-up context, provider request serialization, query
  restrictions, and prevention of model-written numeric summaries. Existing
  AppTest and prior browser checks validate the dashboard/local analysis path,
  not live provider behavior.
- The complete suite now passes **51 tests**; project-wide Python compilation
  passes. The local archive smoke test discovered 20 datasets and validated
  player/match lookup, filtered IPL metrics, bounded SELECT access, and
  natural-language ranking questions. Details are in
  `docs/AI_ANALYST_TEST_REPORT.md`.
- Supported local intents, provider configuration, bounds, and limitations
  are documented in `docs/AI_CRICKET_ANALYST.md`.
