# SupeRR Intelligence — Methodology and Ranking Evidence

> **PROVISIONAL — NOT AN OFFICIAL FINAL SUBMISSION.** The official Rajasthan
> Royals Round 1 Problem Statement and `MASTER_SPECIFICATION.md` are not in the
> workspace, so official rules cannot be confirmed. This run applies the
> current request's IPL and T20I archive from 2022-01-01. Pressure weights,
> threshold, eligibility floors, and source-field interpretations remain
> provisional and materially affect the selections.

**Methodology version:** `pressure-spi-v1-provisional`  
**Ranking run ID:** `9f00984a3cdd119a3b48`  
**Submission status:** provisional; not approved as final official rankings.

## 1. Objective and source scope

The requested objective is to identify pressure-performing batters and
bowlers from the supplied historical IPL and T20I archive dated on or after
2022-01-01. The official brief is unavailable, so this is the scope stated in
the current request, not a verified quotation of official rules. The selected
scope contains 371 IPL matches and
482 T20I matches, totalling
194,014 deliveries.

## 2. Dataset inventory and validation

| Source file | Rows | Columns |
|---|---:|---:|
| `ball_by_ball.csv` | 200,999 | 33 |
| `matches.csv` | 883 | 22 |
| `competitions.csv` | 141 | 4 |
| `teams.csv` | 353 | 3 |
| `playing_eleven.csv` | 28,381 | 9 |
| `competition_team_player_mapping.csv` | 6,413 | 6 |

Validation completed with **38 passing
checks, 5 warnings, and
0 failures**.

- **playing_eleven.csv: candidate key:** Null-key rows: 0; duplicate-key rows: 75.
- **matches with ball-by-ball coverage:** Matches without deliveries: 16.
- **ball-count interpretation:** 8429 rows have over_ball_num > 6; over_ball_num is not a legal-ball counter.
- **boundary flags versus batter runs:** is_four/runs mismatches: 20; is_six/runs mismatches: 3. Do not replace supplied event flags without investigating their semantics.
- **runs field on non-batter extras:** Byes/legbyes/penalty rows with non-zero source runs: 1; the source runs field is retained and these rows need semantic review.

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

### Batter pressure component correlation and contribution

| Component pair | Spearman rho | High-overlap flag |
|---|---:|:---:|
| run_rate / wickets | 0.371 | False |
| run_rate / time | 0.178 | False |
| run_rate / closeness | -0.087 | False |
| wickets / time | 0.768 | True |
| wickets / closeness | 0.107 | False |
| time / closeness | 0.211 | False |

| Component | Weight | Mean normalized value | Mean score points |
|---|---:|---:|---:|
| run_rate | 0.350 | 0.111 | 3.89 |
| wickets | 0.250 | 0.268 | 6.69 |
| time | 0.200 | 0.472 | 9.45 |
| closeness | 0.200 | 0.557 | 11.14 |
### Bowler pressure component correlation and contribution

| Component pair | Spearman rho | High-overlap flag |
|---|---:|:---:|
| run_rate / wickets | 0.150 | False |
| run_rate / time | 0.049 | False |
| run_rate / closeness | 0.104 | False |
| wickets / time | -0.768 | True |
| wickets / closeness | -0.107 | False |
| time / closeness | 0.211 | False |

| Component | Weight | Mean normalized value | Mean score points |
|---|---:|---:|---:|
| run_rate | 0.300 | 0.055 | 1.64 |
| wickets | 0.250 | 0.732 | 18.31 |
| time | 0.200 | 0.472 | 9.45 |
| closeness | 0.250 | 0.557 | 13.92 |

### Actual pressure-event calculations

| Role | Match | Innings / delivery | Pre-event score | Wickets / balls before | Req. / reference rate | Score | Weighted components |
|---|---:|---:|---:|---:|---:|---:|---|
| Batter | 29924 | 2 / 125 | 150 | 9 / 117 | 22.00 / 8.58 | 81.18 | run_rate=1.000×0.35 (35.0), wickets=0.900×0.25 (22.5), time=0.975×0.20 (19.5), closeness=0.209×0.20 (4.2) |
| Bowler | 37943 | 1 / 133 | 282 | 1 / 120 | n/a / 8.50 | 75.20 | run_rate=0.659×0.30 (19.8), wickets=0.900×0.25 (22.5), time=1.000×0.20 (20.0), closeness=0.517×0.25 (12.9) |

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
The current run contains 272 eligible
batters and 336 eligible bowlers.
Exports include `top_10_batters.csv`, `top_10_bowlers.csv`, full ranking CSVs,
and supporting player-metric tables in `reports/`.

### Top 10 batters

| Rank | Player ID | Player | SPI | Pressure SR | Normal baseline | Pressure balls | Pressure matches | Reliability | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4708 | Rinku Singh | 90.24 | 204.21 | 142.39 | 214 | 19 | 87.70 | Pressure performance 204.21 versus normal 142.39; competition-adjusted change +50.89; 214 pressure opportunities across 83 matches. |
| 2 | 8 | Mahendra Singh Dhoni | 88.49 | 182.66 | 111.63 | 248 | 31 | 89.21 | Pressure performance 182.66 versus normal 111.63; competition-adjusted change +39.45; 248 pressure opportunities across 48 matches. |
| 3 | 1077 | David Miller | 88.37 | 213.41 | 138.87 | 179 | 27 | 85.65 | Pressure performance 213.41 versus normal 138.87; competition-adjusted change +45.14; 179 pressure opportunities across 81 matches. |
| 4 | 8301 | Asif Khan | 87.50 | 223.08 | 126.35 | 52 | 3 | 63.41 | Pressure performance 223.08 versus normal 126.35; competition-adjusted change +77.94; 52 pressure opportunities across 13 matches. |
| 5 | 20702 | Tristan Stubbs | 87.28 | 206.91 | 137.92 | 188 | 19 | 86.24 | Pressure performance 206.91 versus normal 137.92; competition-adjusted change +33.29; 188 pressure opportunities across 69 matches. |
| 6 | 6651 | Towhid Hridoy | 86.99 | 177.78 | 120.31 | 90 | 4 | 75.00 | Pressure performance 177.78 versus normal 120.31; competition-adjusted change +33.18; 90 pressure opportunities across 50 matches. |
| 7 | 6460 | Ayush Badoni | 86.95 | 187.01 | 130.50 | 154 | 22 | 83.70 | Pressure performance 187.01 versus normal 130.50; competition-adjusted change +42.34; 154 pressure opportunities across 56 matches. |
| 8 | 4773 | Jaker Ali Anik | 86.89 | 184.92 | 112.18 | 126 | 13 | 80.77 | Pressure performance 184.92 versus normal 112.18; competition-adjusted change +41.00; 126 pressure opportunities across 34 matches. |
| 9 | 7897 | Namboori Tilak Varma | 86.69 | 200.00 | 138.65 | 206 | 23 | 87.29 | Pressure performance 200.00 versus normal 138.65; competition-adjusted change +31.64; 206 pressure opportunities across 123 matches. |
| 10 | 152 | Ravindra Jadeja | 86.27 | 173.02 | 121.53 | 252 | 32 | 89.36 | Pressure performance 173.02 versus normal 121.53; competition-adjusted change +33.77; 252 pressure opportunities across 65 matches. |

### Top 10 bowlers

| Rank | Player ID | Player | SPI | Pressure econ. | Normal baseline | Pressure balls | Pressure matches | Reliability | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 25138 | Harsh Dubey | 82.17 | 7.22 | 11.62 | 64 | 4 | 68.09 | Pressure performance 7.22 versus normal 11.62; competition-adjusted change +2.85; 64 pressure opportunities across 11 matches. |
| 2 | 56817 | Shivang Kumar | 80.02 | 7.36 | 10.88 | 84 | 6 | 73.68 | Pressure performance 7.36 versus normal 10.88; competition-adjusted change +2.48; 84 pressure opportunities across 13 matches. |
| 3 | 3077 | Usama Mir | 77.64 | 5.69 | 11.61 | 58 | 5 | 65.91 | Pressure performance 5.69 versus normal 11.61; competition-adjusted change +2.62; 58 pressure opportunities across 5 matches. |
| 4 | 25132 | Praful Hinge | 72.76 | 10.24 | 12.24 | 58 | 6 | 65.91 | Pressure performance 10.24 versus normal 12.24; competition-adjusted change +1.30; 58 pressure opportunities across 7 matches. |
| 5 | 32862 | Allah Ghazanfar | 71.69 | 9.09 | 9.50 | 103 | 8 | 77.44 | Pressure performance 9.09 versus normal 9.50; competition-adjusted change +0.97; 103 pressure opportunities across 15 matches. |
| 6 | 23 | Piyush Chawla | 70.72 | 7.53 | 8.77 | 169 | 12 | 84.92 | Pressure performance 7.53 versus normal 8.77; competition-adjusted change +0.70; 169 pressure opportunities across 27 matches. |
| 7 | 4716 | Mayank Dagar | 69.82 | 7.82 | 11.68 | 99 | 6 | 76.74 | Pressure performance 7.82 versus normal 11.68; competition-adjusted change +0.84; 99 pressure opportunities across 8 matches. |
| 8 | 48616 | Abdul Saqlain | 67.99 | 7.40 | 12.47 | 30 | 3 | 50.00 | Pressure performance 7.40 versus normal 12.47; competition-adjusted change +2.01; 30 pressure opportunities across 3 matches. |
| 9 | 2490 | Mohammad Nawaz | 66.78 | 7.03 | 7.17 | 321 | 24 | 91.45 | Pressure performance 7.03 versus normal 7.17; competition-adjusted change +0.30; 321 pressure opportunities across 52 matches. |
| 10 | 8530 | Kartik Tyagi | 66.20 | 9.69 | 10.66 | 174 | 13 | 85.29 | Pressure performance 9.69 versus normal 10.66; competition-adjusted change +0.30; 174 pressure opportunities across 19 matches. |

The CSV outputs contain the per-player competition scope, full metric values,
reliability, and generated evidence summary. Their recorded SHA-256 digests are:

- Batters: `6992f80d3d2737c95b26a405c8f70e9717d6cd9925da74ea8e15354ba8b1c630`
- Bowlers: `bf7a3dd80dca6ede5a71a094b606923842893971b4ec68885b1347a187c7ad14`

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

### Batter ranking sensitivity

| Scenario | Pressure deliveries | Pressure opportunities | Eligible | Top-10 Jaccard |
|---|---:|---:|---:|---:|
| performance_heavy | 23870 | 22645 | 272 | 0.818 |
| balanced | 23870 | 22645 | 272 | 0.818 |
| consistency_heavy | 23870 | 22645 | 272 | 0.667 |
| reliability_heavy | 23870 | 22645 | 272 | 0.429 |
| reliability_removed | 23870 | 22645 | 272 | 0.429 |
| lower_exposure | 23870 | 22645 | 346 | 1.000 |
| higher_exposure | 23870 | 22645 | 192 | 0.667 |
| pressure_threshold_40 | 55326 | 52647 | 314 | 0.176 |
| pressure_threshold_60 | 9360 | 8842 | 186 | 0.176 |
| equal_pressure_component_weights | 23870 | 22645 | 310 | 0.333 |
| closeness_removed | 16915 | 16063 | 237 | 0.429 |

Top-ten membership and rank movement from baseline:
- **performance_heavy:** ID 8: rank 2 → 3; SPI 88.49 → 90.47 (Δ +1.98); ID 152: rank 10 → 8; SPI 86.27 → 88.30 (Δ +2.03); ID 1077: rank 3 → 2; SPI 88.37 → 90.63 (Δ +2.25); ID 4708: rank 1 → 1; SPI 90.24 → 92.30 (Δ +2.06); ID 4773: rank 8 → 6; SPI 86.89 → 89.09 (Δ +2.20); ID 6460: rank 7 → 5; SPI 86.95 → 89.34 (Δ +2.39); ID 6651: rank 6 → 11; SPI 86.99 → 88.02 (Δ +1.03); ID 7897: rank 9 → 9; SPI 86.69 → 88.27 (Δ +1.57); ID 8301: rank 4 → 4; SPI 87.50 → 90.38 (Δ +2.88); ID 20702: rank 5 → 7; SPI 87.28 → 88.87 (Δ +1.59); ID 45749: rank 16 → 10; SPI 85.59 → 88.12 (Δ +2.53)
- **balanced:** ID 8: rank 2 → 2; SPI 88.49 → 86.51 (Δ -1.98); ID 152: rank 10 → 11; SPI 86.27 → 84.24 (Δ -2.03); ID 1077: rank 3 → 3; SPI 88.37 → 86.12 (Δ -2.25); ID 4708: rank 1 → 1; SPI 90.24 → 88.18 (Δ -2.06); ID 4773: rank 8 → 7; SPI 86.89 → 84.70 (Δ -2.20); ID 6396: rank 13 → 10; SPI 85.81 → 84.46 (Δ -1.35); ID 6460: rank 7 → 9; SPI 86.95 → 84.57 (Δ -2.39); ID 6651: rank 6 → 4; SPI 86.99 → 85.96 (Δ -1.03); ID 7897: rank 9 → 6; SPI 86.69 → 85.12 (Δ -1.57); ID 8301: rank 4 → 8; SPI 87.50 → 84.62 (Δ -2.88); ID 20702: rank 5 → 5; SPI 87.28 → 85.69 (Δ -1.59)
- **consistency_heavy:** ID 8: rank 2 → 6; SPI 88.49 → 82.01 (Δ -6.48); ID 152: rank 10 → 20; SPI 86.27 → 79.16 (Δ -7.11); ID 1077: rank 3 → 7; SPI 88.37 → 81.71 (Δ -6.66); ID 4708: rank 1 → 3; SPI 90.24 → 84.15 (Δ -6.09); ID 4773: rank 8 → 10; SPI 86.89 → 81.09 (Δ -5.81); ID 6460: rank 7 → 16; SPI 86.95 → 79.97 (Δ -6.98); ID 6651: rank 6 → 1; SPI 86.99 → 86.08 (Δ -0.91); ID 7897: rank 9 → 9; SPI 86.69 → 81.54 (Δ -5.15); ID 8301: rank 4 → 4; SPI 87.50 → 83.09 (Δ -4.41); ID 20702: rank 5 → 5; SPI 87.28 → 82.41 (Δ -4.87); ID 22187: rank 14 → 2; SPI 85.71 → 84.92 (Δ -0.79); ID 45749: rank 16 → 8; SPI 85.59 → 81.60 (Δ -4.00)
- **reliability_heavy:** ID 8: rank 2 → 2; SPI 88.49 → 87.05 (Δ -1.44); ID 152: rank 10 → 8; SPI 86.27 → 85.27 (Δ -1.01); ID 1077: rank 3 → 3; SPI 88.37 → 86.03 (Δ -2.35); ID 4708: rank 1 → 1; SPI 90.24 → 88.08 (Δ -2.16); ID 4722: rank 12 → 5; SPI 85.96 → 85.75 (Δ -0.21); ID 4773: rank 8 → 14; SPI 86.89 → 83.91 (Δ -2.98); ID 4986: rank 18 → 9; SPI 84.46 → 84.54 (Δ +0.08); ID 6396: rank 13 → 7; SPI 85.81 → 85.53 (Δ -0.28); ID 6460: rank 7 → 11; SPI 86.95 → 84.39 (Δ -2.56); ID 6651: rank 6 → 15; SPI 86.99 → 83.77 (Δ -3.22); ID 6726: rank 20 → 10; SPI 84.00 → 84.45 (Δ +0.45); ID 7897: rank 9 → 6; SPI 86.69 → 85.55 (Δ -1.14); ID 8301: rank 4 → 25; SPI 87.50 → 80.38 (Δ -7.12); ID 20702: rank 5 → 4; SPI 87.28 → 85.80 (Δ -1.48)
- **reliability_removed:** ID 8: rank 2 → 10; SPI 88.49 → 88.31 (Δ -0.18); ID 152: rank 10 → 22; SPI 86.27 → 85.50 (Δ -0.77); ID 1077: rank 3 → 7; SPI 88.37 → 89.06 (Δ +0.68); ID 3024: rank 32 → 8; SPI 81.79 → 88.96 (Δ +7.17); ID 4708: rank 1 → 3; SPI 90.24 → 90.87 (Δ +0.63); ID 4773: rank 8 → 9; SPI 86.89 → 88.43 (Δ +1.53); ID 6460: rank 7 → 13; SPI 86.95 → 87.77 (Δ +0.81); ID 6651: rank 6 → 5; SPI 86.99 → 89.99 (Δ +3.00); ID 7897: rank 9 → 15; SPI 86.69 → 86.54 (Δ -0.15); ID 8301: rank 4 → 1; SPI 87.50 → 93.52 (Δ +6.02); ID 20702: rank 5 → 14; SPI 87.28 → 87.54 (Δ +0.26); ID 20894: rank 17 → 6; SPI 84.68 → 89.78 (Δ +5.10); ID 22187: rank 14 → 2; SPI 85.71 → 93.33 (Δ +7.62); ID 45749: rank 16 → 4; SPI 85.59 → 90.71 (Δ +5.12)
- **lower_exposure:** ID 8: rank 2 → 2; SPI 88.49 → 89.29 (Δ +0.80); ID 152: rank 10 → 10; SPI 86.27 → 87.36 (Δ +1.08); ID 1077: rank 3 → 3; SPI 88.37 → 89.00 (Δ +0.63); ID 4708: rank 1 → 1; SPI 90.24 → 90.65 (Δ +0.41); ID 4773: rank 8 → 7; SPI 86.89 → 87.80 (Δ +0.91); ID 6460: rank 7 → 9; SPI 86.95 → 87.74 (Δ +0.78); ID 6651: rank 6 → 5; SPI 86.99 → 88.41 (Δ +1.42); ID 7897: rank 9 → 6; SPI 86.69 → 87.94 (Δ +1.25); ID 8301: rank 4 → 8; SPI 87.50 → 87.78 (Δ +0.28); ID 20702: rank 5 → 4; SPI 87.28 → 88.46 (Δ +1.18)
- **higher_exposure:** ID 8: rank 2 → 3; SPI 88.49 → 87.65 (Δ -0.84); ID 152: rank 10 → 8; SPI 86.27 → 85.20 (Δ -1.07); ID 1077: rank 3 → 2; SPI 88.37 → 87.68 (Δ -0.69); ID 4708: rank 1 → 1; SPI 90.24 → 89.75 (Δ -0.49); ID 4722: rank 12 → 10; SPI 85.96 → 84.82 (Δ -1.14); ID 4773: rank 8 → 6; SPI 86.89 → 85.96 (Δ -0.93); ID 6460: rank 7 → 5; SPI 86.95 → 86.13 (Δ -0.83); ID 6651: rank 6 → None; enters or leaves the top ten; ID 7897: rank 9 → 7; SPI 86.69 → 85.50 (Δ -1.19); ID 8101: rank 11 → 9; SPI 85.98 → 84.84 (Δ -1.14); ID 8301: rank 4 → None; enters or leaves the top ten; ID 20702: rank 5 → 4; SPI 87.28 → 86.14 (Δ -1.14)
- **pressure_threshold_40:** ID 8: rank 2 → 69; SPI 88.49 → 80.35 (Δ -8.15); ID 143: rank 15 → 2; SPI 85.68 → 90.30 (Δ +4.62); ID 152: rank 10 → 126; SPI 86.27 → 73.93 (Δ -12.34); ID 332: rank 67 → 7; SPI 76.51 → 88.87 (Δ +12.37); ID 1077: rank 3 → 5; SPI 88.37 → 89.12 (Δ +0.74); ID 2436: rank 29 → 10; SPI 82.28 → 88.03 (Δ +5.75); ID 2463: rank 103 → 9; SPI 71.62 → 88.20 (Δ +16.58); ID 2756: rank 88 → 6; SPI 73.39 → 88.96 (Δ +15.58); ID 2984: rank 27 → 1; SPI 83.13 → 90.64 (Δ +7.51); ID 4708: rank 1 → 15; SPI 90.24 → 87.22 (Δ -3.02); ID 4773: rank 8 → 26; SPI 86.89 → 85.67 (Δ -1.22); ID 6460: rank 7 → 4; SPI 86.95 → 89.28 (Δ +2.33); ID 6651: rank 6 → 53; SPI 86.99 → 81.90 (Δ -5.09); ID 7260: rank 30 → 3; SPI 82.20 → 90.04 (Δ +7.83); ID 7897: rank 9 → 8; SPI 86.69 → 88.80 (Δ +2.11); ID 8301: rank 4 → 21; SPI 87.50 → 86.73 (Δ -0.77); ID 20702: rank 5 → 24; SPI 87.28 → 85.91 (Δ -1.37)
- **pressure_threshold_60:** ID 8: rank 2 → 1; SPI 88.49 → 88.69 (Δ +0.19); ID 152: rank 10 → 14; SPI 86.27 → 83.56 (Δ -2.71); ID 1077: rank 3 → 28; SPI 88.37 → 79.19 (Δ -9.18); ID 2436: rank 29 → 6; SPI 82.28 → 86.02 (Δ +3.75); ID 2984: rank 27 → 4; SPI 83.13 → 86.40 (Δ +3.26); ID 3605: rank 33 → 5; SPI 81.61 → 86.25 (Δ +4.64); ID 4101: rank 107 → 7; SPI 70.98 → 85.49 (Δ +14.51); ID 4708: rank 1 → 2; SPI 90.24 → 87.99 (Δ -2.25); ID 4722: rank 12 → 10; SPI 85.96 → 84.66 (Δ -1.30); ID 4773: rank 8 → 48; SPI 86.89 → 71.29 (Δ -15.61); ID 4986: rank 18 → 9; SPI 84.46 → 84.74 (Δ +0.28); ID 6460: rank 7 → 29; SPI 86.95 → 78.14 (Δ -8.82); ID 6651: rank 6 → 3; SPI 86.99 → 86.45 (Δ -0.54); ID 6726: rank 20 → 8; SPI 84.00 → 85.05 (Δ +1.05); ID 7897: rank 9 → 167; SPI 86.69 → 34.59 (Δ -52.10); ID 8301: rank 4 → 87; SPI 87.50 → 58.47 (Δ -29.03); ID 20702: rank 5 → 130; SPI 87.28 → 46.22 (Δ -41.06)
- **equal_pressure_component_weights:** ID 8: rank 2 → 18; SPI 88.49 → 86.55 (Δ -1.94); ID 143: rank 15 → 5; SPI 85.68 → 88.66 (Δ +2.99); ID 152: rank 10 → 42; SPI 86.27 → 83.43 (Δ -2.85); ID 1077: rank 3 → 2; SPI 88.37 → 89.35 (Δ +0.98); ID 2436: rank 29 → 6; SPI 82.28 → 88.36 (Δ +6.08); ID 3125: rank 63 → 10; SPI 76.93 → 87.55 (Δ +10.62); ID 3926: rank 38 → 7; SPI 80.38 → 87.66 (Δ +7.27); ID 4708: rank 1 → 3; SPI 90.24 → 89.29 (Δ -0.95); ID 4773: rank 8 → 11; SPI 86.89 → 87.54 (Δ +0.64); ID 6460: rank 7 → 9; SPI 86.95 → 87.64 (Δ +0.69); ID 6651: rank 6 → 86; SPI 86.99 → 77.10 (Δ -9.89); ID 7897: rank 9 → 8; SPI 86.69 → 87.65 (Δ +0.96); ID 8101: rank 11 → 1; SPI 85.98 → 89.45 (Δ +3.47); ID 8301: rank 4 → 56; SPI 87.50 → 80.76 (Δ -6.74); ID 20702: rank 5 → 4; SPI 87.28 → 88.86 (Δ +1.58)
- **closeness_removed:** ID 8: rank 2 → 3; SPI 88.49 → 89.24 (Δ +0.75); ID 152: rank 10 → 5; SPI 86.27 → 88.58 (Δ +2.31); ID 796: rank 26 → 10; SPI 83.35 → 85.79 (Δ +2.44); ID 1077: rank 3 → 6; SPI 88.37 → 87.91 (Δ -0.46); ID 4708: rank 1 → 1; SPI 90.24 → 90.46 (Δ +0.22); ID 4773: rank 8 → 11; SPI 86.89 → 85.43 (Δ -1.46); ID 6396: rank 13 → 7; SPI 85.81 → 87.91 (Δ +2.09); ID 6460: rank 7 → 15; SPI 86.95 → 84.36 (Δ -2.59); ID 6651: rank 6 → 4; SPI 86.99 → 89.10 (Δ +2.11); ID 6726: rank 20 → 9; SPI 84.00 → 86.46 (Δ +2.46); ID 7897: rank 9 → 32; SPI 86.69 → 81.92 (Δ -4.77); ID 8101: rank 11 → 8; SPI 85.98 → 87.43 (Δ +1.46); ID 8301: rank 4 → 21; SPI 87.50 → 83.61 (Δ -3.89); ID 20702: rank 5 → 2; SPI 87.28 → 89.25 (Δ +1.97)
### Bowler ranking sensitivity

| Scenario | Pressure deliveries | Pressure opportunities | Eligible | Top-10 Jaccard |
|---|---:|---:|---:|---:|
| performance_heavy | 57779 | 55179 | 336 | 0.818 |
| balanced | 57779 | 55179 | 336 | 0.818 |
| consistency_heavy | 57779 | 55179 | 336 | 0.818 |
| reliability_heavy | 57779 | 55179 | 336 | 0.818 |
| reliability_removed | 57779 | 55179 | 336 | 0.667 |
| lower_exposure | 57779 | 55179 | 402 | 1.000 |
| higher_exposure | 57779 | 55179 | 266 | 0.667 |
| pressure_threshold_40 | 124766 | 119346 | 410 | 0.053 |
| pressure_threshold_60 | 4646 | 4392 | 109 | 0.053 |
| equal_pressure_component_weights | 57779 | 55179 | 366 | 0.429 |
| closeness_removed | 17896 | 16994 | 227 | 0.000 |

Top-ten membership and rank movement from baseline:
- **performance_heavy:** ID 23: rank 6 → 7; SPI 70.72 → 69.86 (Δ -0.86); ID 286: rank 11 → 9; SPI 65.28 → 64.92 (Δ -0.36); ID 2490: rank 9 → 10; SPI 66.78 → 64.67 (Δ -2.11); ID 3077: rank 3 → 3; SPI 77.64 → 80.53 (Δ +2.88); ID 4716: rank 7 → 8; SPI 69.82 → 69.55 (Δ -0.27); ID 8530: rank 10 → 13; SPI 66.20 → 64.09 (Δ -2.12); ID 25132: rank 4 → 4; SPI 72.76 → 73.06 (Δ +0.31); ID 25138: rank 1 → 1; SPI 82.17 → 84.48 (Δ +2.31); ID 32862: rank 5 → 5; SPI 71.69 → 71.61 (Δ -0.07); ID 48616: rank 8 → 6; SPI 67.99 → 70.32 (Δ +2.33); ID 56817: rank 2 → 2; SPI 80.02 → 82.59 (Δ +2.57)
- **balanced:** ID 23: rank 6 → 6; SPI 70.72 → 71.58 (Δ +0.86); ID 2490: rank 9 → 8; SPI 66.78 → 68.89 (Δ +2.11); ID 3077: rank 3 → 3; SPI 77.64 → 74.76 (Δ -2.88); ID 3653: rank 15 → 10; SPI 64.00 → 67.03 (Δ +3.04); ID 4716: rank 7 → 7; SPI 69.82 → 70.09 (Δ +0.27); ID 8530: rank 10 → 9; SPI 66.20 → 68.32 (Δ +2.12); ID 25132: rank 4 → 4; SPI 72.76 → 72.45 (Δ -0.31); ID 25138: rank 1 → 1; SPI 82.17 → 79.85 (Δ -2.31); ID 32862: rank 5 → 5; SPI 71.69 → 71.76 (Δ +0.07); ID 48616: rank 8 → 11; SPI 67.99 → 65.67 (Δ -2.33); ID 56817: rank 2 → 2; SPI 80.02 → 77.45 (Δ -2.57)
- **consistency_heavy:** ID 23: rank 6 → 6; SPI 70.72 → 70.63 (Δ -0.09); ID 286: rank 11 → 10; SPI 65.28 → 68.18 (Δ +2.90); ID 2490: rank 9 → 9; SPI 66.78 → 68.59 (Δ +1.81); ID 3077: rank 3 → 4; SPI 77.64 → 70.77 (Δ -6.87); ID 4716: rank 7 → 7; SPI 69.82 → 69.30 (Δ -0.51); ID 8530: rank 10 → 8; SPI 66.20 → 69.16 (Δ +2.96); ID 25132: rank 4 → 2; SPI 72.76 → 73.14 (Δ +0.38); ID 25138: rank 1 → 1; SPI 82.17 → 77.58 (Δ -4.59); ID 32862: rank 5 → 5; SPI 71.69 → 70.77 (Δ -0.91); ID 48616: rank 8 → 22; SPI 67.99 → 64.15 (Δ -3.84); ID 56817: rank 2 → 3; SPI 80.02 → 73.07 (Δ -6.95)
- **reliability_heavy:** ID 23: rank 6 → 3; SPI 70.72 → 74.25 (Δ +3.53); ID 2490: rank 9 → 4; SPI 66.78 → 73.40 (Δ +6.62); ID 3077: rank 3 → 5; SPI 77.64 → 72.99 (Δ -4.65); ID 3653: rank 15 → 7; SPI 64.00 → 72.64 (Δ +8.64); ID 4716: rank 7 → 9; SPI 69.82 → 71.42 (Δ +1.60); ID 8530: rank 10 → 8; SPI 66.20 → 71.71 (Δ +5.51); ID 25132: rank 4 → 10; SPI 72.76 → 71.14 (Δ -1.62); ID 25138: rank 1 → 1; SPI 82.17 → 77.50 (Δ -4.67); ID 32862: rank 5 → 6; SPI 71.69 → 72.90 (Δ +1.21); ID 48616: rank 8 → 47; SPI 67.99 → 62.53 (Δ -5.46); ID 56817: rank 2 → 2; SPI 80.02 → 76.70 (Δ -3.32)
- **reliability_removed:** ID 23: rank 6 → 9; SPI 70.72 → 67.17 (Δ -3.55); ID 286: rank 11 → 8; SPI 65.28 → 67.46 (Δ +2.19); ID 2490: rank 9 → 18; SPI 66.78 → 60.61 (Δ -6.17); ID 3077: rank 3 → 3; SPI 77.64 → 80.58 (Δ +2.93); ID 4716: rank 7 → 7; SPI 69.82 → 68.09 (Δ -1.73); ID 8530: rank 10 → 16; SPI 66.20 → 61.43 (Δ -4.77); ID 25132: rank 4 → 4; SPI 72.76 → 74.47 (Δ +1.71); ID 25138: rank 1 → 1; SPI 82.17 → 85.69 (Δ +3.52); ID 32862: rank 5 → 6; SPI 71.69 → 70.25 (Δ -1.44); ID 36553: rank 13 → 10; SPI 64.67 → 66.86 (Δ +2.20); ID 48616: rank 8 → 5; SPI 67.99 → 72.49 (Δ +4.50); ID 56817: rank 2 → 2; SPI 80.02 → 81.61 (Δ +1.58)
- **lower_exposure:** ID 23: rank 6 → 6; SPI 70.72 → 71.37 (Δ +0.65); ID 2490: rank 9 → 9; SPI 66.78 → 67.12 (Δ +0.34); ID 3077: rank 3 → 3; SPI 77.64 → 78.44 (Δ +0.80); ID 4716: rank 7 → 7; SPI 69.82 → 70.51 (Δ +0.69); ID 8530: rank 10 → 10; SPI 66.20 → 66.52 (Δ +0.31); ID 25132: rank 4 → 4; SPI 72.76 → 73.58 (Δ +0.82); ID 25138: rank 1 → 1; SPI 82.17 → 82.89 (Δ +0.72); ID 32862: rank 5 → 5; SPI 71.69 → 72.45 (Δ +0.76); ID 48616: rank 8 → 8; SPI 67.99 → 68.86 (Δ +0.87); ID 56817: rank 2 → 2; SPI 80.02 → 80.78 (Δ +0.76)
- **higher_exposure:** ID 23: rank 6 → 5; SPI 70.72 → 69.77 (Δ -0.95); ID 2490: rank 9 → 7; SPI 66.78 → 66.29 (Δ -0.48); ID 3077: rank 3 → 2; SPI 77.64 → 76.34 (Δ -1.30); ID 3653: rank 15 → 10; SPI 64.00 → 63.89 (Δ -0.11); ID 4716: rank 7 → 6; SPI 69.82 → 68.81 (Δ -1.01); ID 6683: rank 12 → 9; SPI 64.95 → 64.24 (Δ -0.72); ID 8530: rank 10 → 8; SPI 66.20 → 65.75 (Δ -0.45); ID 25132: rank 4 → 3; SPI 72.76 → 71.54 (Δ -1.22); ID 25138: rank 1 → None; enters or leaves the top ten; ID 32862: rank 5 → 4; SPI 71.69 → 70.56 (Δ -1.12); ID 48616: rank 8 → None; enters or leaves the top ten; ID 56817: rank 2 → 1; SPI 80.02 → 78.76 (Δ -1.26)
- **pressure_threshold_40:** ID 23: rank 6 → 190; SPI 70.72 → 47.89 (Δ -22.83); ID 158: rank None → 10; enters or leaves the top ten; ID 829: rank 78 → 7; SPI 51.69 → 72.30 (Δ +20.62); ID 2490: rank 9 → 24; SPI 66.78 → 65.52 (Δ -1.26); ID 2985: rank 32 → 3; SPI 58.18 → 78.16 (Δ +19.98); ID 3056: rank 225 → 9; SPI 40.93 → 71.43 (Δ +30.50); ID 3077: rank 3 → 81; SPI 77.64 → 55.83 (Δ -21.81); ID 3775: rank None → 5; enters or leaves the top ten; ID 4276: rank 14 → 1; SPI 64.38 → 83.51 (Δ +19.13); ID 4438: rank None → 8; enters or leaves the top ten; ID 4499: rank 177 → 2; SPI 44.08 → 78.83 (Δ +34.75); ID 4716: rank 7 → 69; SPI 69.82 → 57.39 (Δ -12.43); ID 4838: rank None → 6; enters or leaves the top ten; ID 8530: rank 10 → 50; SPI 66.20 → 60.77 (Δ -5.43); ID 25132: rank 4 → 168; SPI 72.76 → 48.99 (Δ -23.77); ID 25138: rank 1 → 12; SPI 82.17 → 70.65 (Δ -11.52); ID 32862: rank 5 → 22; SPI 71.69 → 66.19 (Δ -5.49); ID 48616: rank 8 → 17; SPI 67.99 → 67.16 (Δ -0.83); ID 56817: rank 2 → 4; SPI 80.02 → 77.55 (Δ -2.47)
- **pressure_threshold_60:** ID 23: rank 6 → None; enters or leaves the top ten; ID 786: rank 251 → 8; SPI 39.27 → 48.31 (Δ +9.04); ID 1107: rank 135 → 5; SPI 46.74 → 52.53 (Δ +5.79); ID 2304: rank 72 → 1; SPI 52.43 → 59.09 (Δ +6.65); ID 2490: rank 9 → None; enters or leaves the top ten; ID 2526: rank 227 → 6; SPI 40.68 → 51.11 (Δ +10.43); ID 3077: rank 3 → None; enters or leaves the top ten; ID 4229: rank 47 → 2; SPI 56.00 → 56.73 (Δ +0.73); ID 4716: rank 7 → 45; SPI 69.82 → 40.22 (Δ -29.60); ID 8049: rank 237 → 3; SPI 40.41 → 56.30 (Δ +15.89); ID 8530: rank 10 → 9; SPI 66.20 → 47.90 (Δ -18.31); ID 25132: rank 4 → None; enters or leaves the top ten; ID 25138: rank 1 → None; enters or leaves the top ten; ID 26663: rank 182 → 4; SPI 43.70 → 55.99 (Δ +12.29); ID 32862: rank 5 → None; enters or leaves the top ten; ID 35318: rank 148 → 10; SPI 46.10 → 47.78 (Δ +1.69); ID 48616: rank 8 → None; enters or leaves the top ten; ID 56817: rank 2 → None; enters or leaves the top ten; ID 58246: rank 94 → 7; SPI 50.50 → 49.92 (Δ -0.59)
- **equal_pressure_component_weights:** ID 23: rank 6 → 12; SPI 70.72 → 64.61 (Δ -6.11); ID 2490: rank 9 → 28; SPI 66.78 → 59.13 (Δ -7.65); ID 3077: rank 3 → 1; SPI 77.64 → 80.59 (Δ +2.94); ID 3623: rank 100 → 7; SPI 49.68 → 68.58 (Δ +18.90); ID 4716: rank 7 → 32; SPI 69.82 → 57.97 (Δ -11.85); ID 8530: rank 10 → 8; SPI 66.20 → 67.84 (Δ +1.64); ID 25048: rank 116 → 10; SPI 48.09 → 66.43 (Δ +18.34); ID 25132: rank 4 → 5; SPI 72.76 → 69.10 (Δ -3.66); ID 25138: rank 1 → 3; SPI 82.17 → 77.32 (Δ -4.85); ID 32862: rank 5 → 70; SPI 71.69 → 53.23 (Δ -18.46); ID 36553: rank 13 → 6; SPI 64.67 → 68.99 (Δ +4.32); ID 41503: rank 81 → 4; SPI 51.31 → 69.75 (Δ +18.44); ID 48616: rank 8 → 9; SPI 67.99 → 67.20 (Δ -0.79); ID 56817: rank 2 → 2; SPI 80.02 → 78.94 (Δ -1.08)
- **closeness_removed:** ID 23: rank 6 → 24; SPI 70.72 → 52.70 (Δ -18.02); ID 1107: rank 135 → 4; SPI 46.74 → 61.80 (Δ +15.06); ID 2399: rank 74 → 7; SPI 52.35 → 58.24 (Δ +5.89); ID 2490: rank 9 → 39; SPI 66.78 → 49.50 (Δ -17.28); ID 3077: rank 3 → None; enters or leaves the top ten; ID 3686: rank 29 → 9; SPI 58.68 → 57.87 (Δ -0.81); ID 4229: rank 47 → 8; SPI 56.00 → 57.97 (Δ +1.97); ID 4460: rank 147 → 1; SPI 46.13 → 71.57 (Δ +25.43); ID 4716: rank 7 → 56; SPI 69.82 → 47.02 (Δ -22.80); ID 4823: rank 95 → 10; SPI 50.33 → 57.75 (Δ +7.41); ID 6676: rank 114 → 2; SPI 48.34 → 67.35 (Δ +19.00); ID 8530: rank 10 → 90; SPI 66.20 → 44.30 (Δ -21.90); ID 17424: rank 102 → 3; SPI 49.45 → 62.95 (Δ +13.50); ID 21784: rank 273 → 6; SPI 37.94 → 58.54 (Δ +20.60); ID 25048: rank 116 → 5; SPI 48.09 → 58.65 (Δ +10.56); ID 25132: rank 4 → 63; SPI 72.76 → 46.20 (Δ -26.56); ID 25138: rank 1 → 82; SPI 82.17 → 44.79 (Δ -37.38); ID 32862: rank 5 → None; enters or leaves the top ten; ID 48616: rank 8 → None; enters or leaves the top ten; ID 56817: rank 2 → 27; SPI 80.02 → 52.08 (Δ -27.94)

### Correlation diagnostics

The SPI has one performance-difference component plus consistency and
reliability. The following Spearman diagnostics are calculated among eligible
candidates; flagged overlap is a review signal, not proof of duplicate
constructs or a statistical correction:

### Batter SPI-component correlations

| Component pair | Spearman rho | High-overlap flag (|rho| >= 0.70) |
|---|---:|:---:|
| performance_component / consistency | 0.402 | False |
| performance_component / reliability | 0.348 | False |
| consistency / reliability | 0.184 | False |
### Bowler SPI-component correlations

| Component pair | Spearman rho | High-overlap flag (|rho| >= 0.70) |
|---|---:|:---:|
| performance_component / consistency | -0.107 | False |
| performance_component / reliability | -0.272 | False |
| consistency / reliability | -0.138 | False |

Independent SPI recalculation from underlying role metrics:

- **Batter:** 10 recalculated, maximum absolute SPI difference 0; pass=True.
- **Bowler:** 10 recalculated, maximum absolute SPI difference 0; pass=True.

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

- **batter_runs:** 194,014 matched rows, 0 mismatches.
- **bowler_conceded_runs:** 194,014 matched rows, 0 mismatches.
- **has_boundary_flag:** 194,014 matched rows, 0 mismatches.
- **is_bowler_wicket:** 194,014 matched rows, 0 mismatches.
- **is_legal_ball:** 194,014 matched rows, 0 mismatches.
- **target:** 194,014 matched rows, 0 mismatches.
- **team_runs:** 194,014 matched rows, 0 mismatches.

Raw hashes match the ETL manifest: **True**.
Source runs total 261,119,
team runs total 275,375, and
the difference is the recorded extras sum. There are
2
rows with extras runs but no extras type and
260 `other`
extras rows whose attribution remains ambiguous. The scoped records include
20
four-flag and
3
six-flag disagreements against source runs. Of
573 run-outs,
none are credited to bowlers under the current policy.

The SPI values were independently recomputed from underlying role metrics:

- **Batter:** 10 recalculated, maximum absolute SPI difference 0; pass=True.
- **Bowler:** 10 recalculated, maximum absolute SPI difference 0; pass=True.

These are reproducible arithmetic comparisons, not external scorecard or
domain validation. Not-out opportunity counts are approximate because the
source does not provide authoritative batting innings scorecards. Innings 4
targets match innings 3 total plus one in the tested rows; revised target
semantics have no independent official documentation.

Raw input hashes and validation results are in `reports/final_validation.json`.
Ranking output SHA-256 values are `6992f80d3d2737c95b26a405c8f70e9717d6cd9925da74ea8e15354ba8b1c630`
(batters) and `bf7a3dd80dca6ede5a71a094b606923842893971b4ec68885b1347a187c7ad14` (bowlers).
Ranking run ID: `9f00984a3cdd119a3b48`.

An exploratory decision tree and random forest classify
whether a delivery is a four or six using pre-delivery features and a grouped
match-held-out split. The holdout contains
210 matches with
0 train/test match
overlaps. Test balanced accuracy is
0.557
for the decision tree and
0.560
for the random forest. K-means clustering is exploratory and remains outside
the SPI formula. Detailed metrics and visualizations are in
`reports/machine_learning/`.

A deterministic historical replay processed
194,014 deliveries across
1,660 innings; incremental score/wicket/legal
ball state and recalculated weighted pressure had
0 ordering errors,
0 state mismatches, and
0 pressure mismatches. This is a local
simulation using batch-enriched event envelopes, not a Kafka deployment.

A supplementary player-match graph contains
1,728 nodes and 36,318 directed
edges. PageRank is interpreted as network participation, not player quality;
its results are excluded from SPI and ranking exports. See
`reports/graph/graph_summary.json` and the generated graph visualization.

Cassandra and HBase have query-oriented schema/command design
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
