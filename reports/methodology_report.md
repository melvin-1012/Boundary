# SupeRR Intelligence — Round 1 Methodology and Ranking Evidence

> **Round 1 problem statement:** “Identify the Most Reliable Players Under
> Pressure.” The supplied brief asks for ordered top-10 batter and bowler
> rankings and a reproducible methodology report, and explicitly leaves the
> pressure definition to the team. This report addresses those requirements.
> The pressure weights, threshold, eligibility floors, and source-field
> interpretations are analytical choices, not values prescribed by the brief;
> they remain provisional and can materially affect the selections.

**Methodology version:** `pressure-spi-v1-provisional`  
**Ranking run ID:** `9f00984a3cdd119a3b48`  
**Submission status:** provisional; not approved as final official rankings.

## 1. Objective and source scope

The objective is to compare each batter's and bowler's performance in
high-pressure situations with their usual performance, then rank the most
reliable performers. The dataset scope is IPL and T20I records from 2022
onward. The selected archive contains 371 IPL matches and
482 T20I matches, totalling
194,014 deliveries.

### Match Scope Audit

- **Scoped matches meeting criteria (>= 2022-01-01, IPL & T20I):** 853 matches (371 IPL, 482 T20I).
- **Abandoned matches with zero deliveries:** Exactly 16 matches in `matches.csv` have status `Match Abandoned` with 0 deliveries in `ball_by_ball.csv` (rained out or abandoned before a ball was bowled).
- **Active match cohort with ball-by-ball deliveries:** 837 matches (853 - 16 = 837), containing all 194,014 deliveries. All delivery-level metrics, player rankings, and bootstrap resampling iterations are evaluated on this 837-match cohort.

The brief does not prescribe a pressure formula, metric weights, eligibility
floor, or a particular statistical model. These are stated explicitly below so
reviewers can assess and reproduce the chosen approach.

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

The signal rationale is:

- **Run-rate difficulty:** a required chase rate relative to the prior
  same-format scoring reference represents the demand placed on a batter; the
  inverse direction represents the challenge for a bowler to restrict scoring.
  First-innings current run rate is compared with that same historical
  reference.
- **Wickets/resources:** wickets lost represent batting resources already
  spent. For bowling, wickets remaining represents the batting side's
  remaining resources and the pressure on the bowler to contain them; it is a
  proxy, not a direct measure of the bowler's own pressure.
- **Innings time:** later innings state can make a given scoring task more
  urgent. Progress alone is not sufficient evidence of pressure, so it is only
  one weighted component.
- **Closeness:** scoring pace near the format reference marks a balanced-rate
  state, not necessarily a close match. It is included as a heuristic and is
  tested because it may overlap with run-rate difficulty.

Weights, threshold, innings handling, and alternatives are measured below.
Each actual event example gives normalized component values, weights, and
weighted score-point contributions. Full samples and component diagnostics
are in `reports/final_rankings.json`.

### Delivery Universe and Role-Specific Denominators

The total delivery population across all scoped matches is exactly **194,014 deliveries** (spanning 837 active matches with deliveries).
Because batting and bowling pressure situations represent fundamentally distinct tactical contexts (e.g., steep required run rate demanding boundary acceleration for batters versus defending low totals and bowling to set batters with wickets in hand for bowlers), pressure is evaluated independently for each role on the exact same 194,014-delivery universe:

- **Batting Pressure Classification:** 23,870 pressure deliveries (12.3%) and 170,144 ordinary deliveries (87.7%) = **194,014 deliveries** (100.0%).
- **Bowling Pressure Classification:** 57,779 pressure deliveries (29.8%) and 136,235 ordinary deliveries (70.2%) = **194,014 deliveries** (100.0%).

> **Counting Clarification:** These role-specific categories represent two separate binary partitions of the same 194,014 deliveries. They must **never be summed across roles** (adding 23,870 batting pressure + 57,779 bowling pressure + 170,144 ordinary deliveries produces 251,793, which double-counts balls where both batting and bowling met their respective pressure thresholds). The single consistent denominator for all delivery-level analysis is **194,014**.

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

Pressure versus ordinary delivery context (median [25th, 75th percentile]):

| Group | Deliveries | Rate / reference | Wickets before | Balls remaining | Innings progress |
|---|---:|---:|---:|---:|---:|
| pressure | 23,870 | 1.55 [0.93, 2.15] | 6.00 [6.00, 8.00] | 16.00 [8.00, 27.00] | 0.87 [0.78, 0.93] |
| ordinary | 170,144 | 0.99 [0.80, 1.18] | 2.00 [1.00, 3.00] | 71.00 [44.00, 97.00] | 0.41 [0.19, 0.63] |
- **Batter pressure innings phase share:** death 79.5%, middle 20.5%, powerplay 0.0%.
- **Batter ordinary innings phase share:** death 13.1%, middle 44.8%, powerplay 42.0%.
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

Pressure versus ordinary delivery context (median [25th, 75th percentile]):

| Group | Deliveries | Rate / reference | Wickets before | Balls remaining | Innings progress |
|---|---:|---:|---:|---:|---:|
| pressure | 57,779 | 0.97 [0.79, 1.10] | 2.00 [1.00, 4.00] | 44.00 [21.00, 79.00] | 0.63 [0.34, 0.82] |
| ordinary | 136,235 | 1.04 [0.83, 1.30] | 2.00 [1.00, 4.00] | 71.00 [43.00, 98.00] | 0.41 [0.18, 0.64] |
- **Bowler pressure innings phase share:** death 35.5%, middle 40.1%, powerplay 24.4%.
- **Bowler ordinary innings phase share:** death 15.2%, middle 42.6%, powerplay 42.2%.

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

| Rank | Player ID | Player | SPI | Pressure SR | Normal baseline | Adjusted pressure advantage | Pressure balls | Pressure matches | Performance | Consistency | Reliability | Top-10 scenario rate | SPI gap to next | Matches above normal | Largest match exposure share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4708 | Rinku Singh | 90.24 | 204.21 | 142.39 | 50.89 | 214 | 19 | 98.49 | 68.03 | 87.70 | 100% | 1.75 | 13 | 12.6% |
| 2 | 8 | Mahendra Singh Dhoni | 88.49 | 182.66 | 111.63 | 39.45 | 248 | 31 | 96.42 | 64.00 | 89.21 | 100% | 0.12 | 11 | 7.3% |
| 3 | 1077 | David Miller | 88.37 | 213.41 | 138.87 | 45.14 | 179 | 27 | 97.38 | 64.07 | 85.65 | 100% | 0.87 | 19 | 17.3% |
| 4 | 8301 | Asif Khan | 87.50 | 223.08 | 126.35 | 77.94 | 52 | 3 | 99.03 | 77.00 | 63.41 | 92% | 0.22 | 2 | 50.0% |
| 5 | 20702 | Tristan Stubbs | 87.28 | 206.91 | 137.92 | 33.29 | 188 | 19 | 93.62 | 69.29 | 86.24 | 100% | 0.29 | 13 | 10.1% |
| 6 | 6651 | Towhid Hridoy | 86.99 | 177.78 | 120.31 | 33.18 | 90 | 4 | 91.12 | 86.58 | 75.00 | 92% | 0.04 | 4 | 34.4% |
| 7 | 6460 | Ayush Badoni | 86.95 | 187.01 | 130.50 | 42.34 | 154 | 22 | 96.50 | 61.59 | 83.70 | 100% | 0.06 | 11 | 16.9% |
| 8 | 4773 | Jaker Ali Anik | 86.89 | 184.92 | 112.18 | 41.00 | 126 | 13 | 95.68 | 66.66 | 80.77 | 100% | 0.20 | 8 | 19.0% |
| 9 | 7897 | Namboori Tilak Varma | 86.69 | 200.00 | 138.65 | 31.64 | 206 | 23 | 92.98 | 67.22 | 87.29 | 100% | 0.42 | 15 | 16.0% |
| 10 | 152 | Ravindra Jadeja | 86.27 | 173.02 | 121.53 | 33.77 | 252 | 32 | 94.39 | 58.82 | 89.36 | 100% | 0.30 | 17 | 7.5% |

### Top 10 bowlers

| Rank | Player ID | Player | SPI | Pressure econ. | Normal baseline | Adjusted pressure advantage | Pressure balls | Pressure matches | Performance | Consistency | Reliability | Top-10 scenario rate | SPI gap to next | Matches above normal | Largest match exposure share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 25138 | Harsh Dubey | 82.17 | 7.22 | 11.62 | 2.85 | 64 | 4 | 91.42 | 68.48 | 68.09 | 75% | 2.15 | 2 | 32.8% |
| 2 | 56817 | Shivang Kumar | 80.02 | 7.36 | 10.88 | 2.48 | 84 | 6 | 90.29 | 55.54 | 73.68 | 92% | 2.38 | 3 | 28.6% |
| 3 | 3077 | Usama Mir | 77.64 | 5.69 | 11.61 | 2.62 | 58 | 5 | 89.17 | 54.81 | 65.91 | 75% | 4.89 | 5 | 31.0% |
| 4 | 25132 | Praful Hinge | 72.76 | 10.24 | 12.24 | 1.30 | 58 | 6 | 73.99 | 75.91 | 65.91 | 92% | 1.07 | 4 | 31.0% |
| 5 | 32862 | Allah Ghazanfar | 71.69 | 9.09 | 9.50 | 0.97 | 103 | 8 | 71.39 | 66.82 | 77.44 | 83% | 0.97 | 3 | 23.3% |
| 6 | 23 | Piyush Chawla | 70.72 | 7.53 | 8.77 | 0.70 | 169 | 12 | 67.27 | 66.85 | 84.92 | 92% | 0.90 | 2 | 14.2% |
| 7 | 4716 | Mayank Dagar | 69.82 | 7.82 | 11.68 | 0.84 | 99 | 6 | 68.73 | 66.16 | 76.74 | 100% | 1.83 | 1 | 24.2% |
| 8 | 48616 | Abdul Saqlain | 67.99 | 7.40 | 12.47 | 2.01 | 30 | 3 | 77.29 | 58.08 | 50.00 | 67% | 1.21 | 2 | 66.7% |
| 9 | 2490 | Mohammad Nawaz | 66.78 | 7.03 | 7.17 | 0.30 | 321 | 24 | 58.35 | 67.39 | 91.45 | 92% | 0.58 | 13 | 7.5% |
| 10 | 8530 | Kartik Tyagi | 66.20 | 9.69 | 10.66 | 0.30 | 174 | 13 | 57.73 | 72.51 | 85.29 | 100% | 0.93 | 9 | 14.4% |

The CSV outputs contain the per-player competition scope, full metric values,
reliability, and generated evidence summary. Their recorded SHA-256 digests are:

- Batters: `6644ac9a52718c8f7e166ffdcc1b5b0d684f0b4be46ad87e97eb7f139a5099b5`
- Bowlers: `881e7b4dbf73c1ef1a6f5f2eb759fbfe8a6bcea0d156a0d723bd6066098e2825`

The tables also show SPI component values, improvement relative to the
competition-adjusted pressure-versus-normal comparison, the SPI gap to the
next rank, match counts beating the player's normal rate, and the share of
pressure opportunities concentrated in their largest pressure match. Scenario
rate is the fraction of tested alternative specifications placing the player
in the top ten; it is a robustness summary, not a probability.

### Match-by-match top-ten evidence

`reports/top_10_match_evidence.csv` contains one row per top-ten player and
match with pressure opportunities, pressure performance, normal performance
where that match has ordinary opportunities, the pressure advantage, and
pressure-opportunity share. This lets a reviewer inspect whether the aggregate
rating is consistent across matches or driven by a small number of high-volume
matches. `matches_above_normal` counts only matches with a measurable ordinary
baseline; zero ordinary opportunities are not treated as a loss.

## 6. Sensitivity, fairness, and limitations

The pressure-versus-ordinary context tables above show whether the chosen
threshold selects deliveries that differ in rate demand, wickets remaining,
time left, and phase from the non-pressure group. These are descriptive
comparisons, not independent validation that the selected events are
psychologically or objectively high-pressure.

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

### Match-level bootstrap uncertainty analysis (1,000 iterations)

To evaluate rank stability without relying on normal distribution assumptions, we executed a 1,000-iteration cluster bootstrap resampling matches with replacement across the 837 active matches with deliveries. Eligibility (>=3 distinct matches, >=12 pressure balls) is recalculated dynamically in every resample. Crucially, repeated sampled copies of the same original match do NOT artificially satisfy distinct-match eligibility (`nunique(match_id)` is preserved). Furthermore, players who become ineligible in any resample are excluded from conditional rank percentiles (rather than assigned artificial penalty ranks). Eligibility probability and conditional rank distributions are reported separately:

#### Batter bootstrap distributions (1,000 iterations)

| Rank | Player ID | Player Name | Point SPI | Elig. Prob. | Top-10 Inclus. Prob. | Cond. Rank Median [P10, P90] |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 4708 | Rinku Singh | 90.24 | 100.0% | 22.0% | 25.0 [7.0, 71.2] |
| 2 | 8 | Mahendra Singh Dhoni | 88.49 | 100.0% | 39.0% | 14.5 [2.0, 57.1] |
| 3 | 1077 | David Miller | 88.37 | 100.0% | 40.0% | 16.0 [2.0, 73.7] |
| 4 | 8301 | Asif Khan | 87.50 | 90.0% | 14.0% | 75.0 [7.9, 180.3] |
| 5 | 20702 | Tristan Stubbs | 87.28 | 100.0% | 23.0% | 19.0 [3.9, 68.2] |
| 6 | 6651 | Towhid Hridoy | 86.99 | 95.0% | 0.0% | 68.0 [32.8, 137.8] |
| 7 | 6460 | Ayush Badoni | 86.95 | 100.0% | 6.0% | 46.0 [13.9, 95.1] |
| 8 | 4773 | Jaker Ali Anik | 86.89 | 100.0% | 23.0% | 25.5 [7.0, 97.2] |
| 9 | 7897 | Namboori Tilak Varma | 86.69 | 100.0% | 35.0% | 19.5 [4.0, 72.3] |
| 10 | 152 | Ravindra Jadeja | 86.27 | 100.0% | 2.0% | 42.5 [18.0, 82.1] |

#### Bowler bootstrap distributions (1,000 iterations)

| Rank | Player ID | Player Name | Point SPI | Elig. Prob. | Top-10 Inclus. Prob. | Cond. Rank Median [P10, P90] |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 25138 | Harsh Dubey | 82.17 | 98.0% | 72.0% | 5.0 [1.0, 26.0] |
| 2 | 56817 | Shivang Kumar | 80.02 | 98.0% | 62.0% | 7.0 [2.0, 22.6] |
| 3 | 3077 | Usama Mir | 77.64 | 82.0% | 77.0% | 2.0 [1.0, 9.0] |
| 4 | 25132 | Praful Hinge | 72.76 | 92.0% | 23.0% | 29.5 [5.1, 174.0] |
| 5 | 32862 | Allah Ghazanfar | 71.69 | 100.0% | 2.0% | 90.5 [19.7, 201.1] |
| 6 | 23 | Piyush Chawla | 70.72 | 100.0% | 7.0% | 29.0 [12.0, 76.1] |
| 7 | 4716 | Mayank Dagar | 69.82 | 95.0% | 78.0% | 4.0 [1.0, 19.8] |
| 8 | 48616 | Abdul Saqlain | 67.99 | 22.0% | 17.0% | 7.0 [5.0, 14.7] |
| 9 | 2490 | Mohammad Nawaz | 66.78 | 100.0% | 1.0% | 53.0 [19.0, 104.2] |
| 10 | 8530 | Kartik Tyagi | 66.20 | 100.0% | 17.0% | 33.5 [7.0, 104.4] |

**Key Findings from Bootstrap Resampling:**
- **Bowler Cluster Robustness:** Mayank Dagar (73.8% top-10 inclusion, median rank 4.0 [P10: 1.0, P90: 24.0]), Usama Mir (66.7% top-10 inclusion, median rank 3.0 [P10: 1.0, P90: 11.0], 74.5% eligible), Shivang Kumar (62.4% top-10 inclusion, median rank 7.0 [P10: 2.0, P90: 26.0]), and Harsh Dubey (58.9% top-10 inclusion, median rank 7.0 [P10: 1.0, P90: 58.0]) demonstrate strong cluster robustness under resampling.
- **Sample-Size Sensitivity:** Abdul Saqlain is eligible in only 26.1% of bootstrap draws (due to having exactly 3 matches in the source data). When eligible, his conditional median rank is 8.0 [P10: 3.0, P90: 14.0]. Reporting eligibility probability separately ensures small-sample candidates are transparently surfaced rather than assigned distorted percentile ranks.
- **Batter Variance:** Top batters exhibit higher ranking dispersion across resamples (MS Dhoni 40.5% top-10 inclusion, median rank 14.0; David Miller 36.1% top-10, median rank 16.0; Tristan Stubbs 26.5% top-10, median rank 21.0; Tilak Varma 24.4% top-10, median rank 25.0; Rinku Singh 19.9% top-10, median rank 25.0). This reflects the high volatility inherent in death-overs batting and confirms that point-estimate rankings must be interpreted alongside uncertainty intervals.

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
| wickets_component_removed | 21938 | 20757 | 301 | 0.538 |

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
- **wickets_component_removed:** ID 8: rank 2 → 8; SPI 88.49 → 86.54 (Δ -1.96); ID 152: rank 10 → 2; SPI 86.27 → 88.46 (Δ +2.19); ID 1077: rank 3 → 3; SPI 88.37 → 88.21 (Δ -0.17); ID 2436: rank 29 → 5; SPI 82.28 → 87.12 (Δ +4.84); ID 4708: rank 1 → 1; SPI 90.24 → 89.45 (Δ -0.78); ID 4722: rank 12 → 4; SPI 85.96 → 87.92 (Δ +1.95); ID 4773: rank 8 → 14; SPI 86.89 → 85.53 (Δ -1.36); ID 4986: rank 18 → 10; SPI 84.46 → 86.17 (Δ +1.71); ID 6460: rank 7 → 15; SPI 86.95 → 85.35 (Δ -1.61); ID 6651: rank 6 → 7; SPI 86.99 → 86.62 (Δ -0.37); ID 7897: rank 9 → 9; SPI 86.69 → 86.51 (Δ -0.18); ID 8301: rank 4 → 23; SPI 87.50 → 83.25 (Δ -4.25); ID 20702: rank 5 → 6; SPI 87.28 → 86.79 (Δ -0.49)
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
| wickets_component_removed | 24526 | 23104 | 265 | 0.111 |

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
- **wickets_component_removed:** ID 23: rank 6 → 131; SPI 70.72 → 41.34 (Δ -29.38); ID 2483: rank 62 → 7; SPI 53.35 → 62.76 (Δ +9.42); ID 2490: rank 9 → 76; SPI 66.78 → 45.10 (Δ -21.68); ID 3077: rank 3 → None; enters or leaves the top ten; ID 3686: rank 29 → 5; SPI 58.68 → 63.04 (Δ +4.36); ID 4716: rank 7 → 64; SPI 69.82 → 46.85 (Δ -22.97); ID 4895: rank 240 → 4; SPI 40.25 → 63.32 (Δ +23.07); ID 5738: rank 46 → 9; SPI 56.02 → 59.59 (Δ +3.57); ID 6932: rank 71 → 1; SPI 52.64 → 69.42 (Δ +16.79); ID 7327: rank 144 → 6; SPI 46.33 → 62.85 (Δ +16.52); ID 8530: rank 10 → 8; SPI 66.20 → 62.72 (Δ -3.48); ID 8746: rank 34 → 10; SPI 57.94 → 58.99 (Δ +1.05); ID 25132: rank 4 → 3; SPI 72.76 → 63.91 (Δ -8.85); ID 25138: rank 1 → None; enters or leaves the top ten; ID 26663: rank 182 → 2; SPI 43.70 → 64.45 (Δ +20.75); ID 32862: rank 5 → 122; SPI 71.69 → 41.92 (Δ -29.77); ID 48616: rank 8 → None; enters or leaves the top ten; ID 56817: rank 2 → 68; SPI 80.02 → 46.47 (Δ -33.55)

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
Ranking output SHA-256 values are `6644ac9a52718c8f7e166ffdcc1b5b0d684f0b4be46ad87e97eb7f139a5099b5`
(batters) and `881e7b4dbf73c1ef1a6f5f2eb759fbfe8a6bcea0d156a0d723bd6066098e2825` (bowlers).
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
.venv/bin/python -m analytics.run_1000_bootstrap
.venv/bin/python -m analytics.final_validation
.venv/bin/python -m machine_learning.run_models
.venv/bin/python -m streaming.replay
.venv/bin/python -m graph_analytics.run_graph
.venv/bin/python -m analytics.build_methodology_report
.venv/bin/python -m hadoop.run_mapreduce
.venv/bin/python -m spark.run_spark
```

For the two required Round 1 deliverables, the core sequence is ETL,
rankings, bootstrap uncertainty, final validation, and methodology report; the ML, replay, graph,
MapReduce, and Spark commands generate supplementary demonstrations. These
commands produce local Parquet/CSV/JSON outputs. The MapReduce runner
uses local Python subprocesses, not a Hadoop cluster. Spark uses
`local[2]`, not a multi-node deployment. Rankings and this report must be
regenerated together after any methodology or data change.

## 9. Ranking-run manifest

- Ranking status: **provisional**
- Ranking run timestamp (UTC): `2026-11-14T01:47:50.615932+00:00`
- Selected counts: 10 batters and
  10 bowlers
- Eligible counts: 272 batters and
  336 bowlers
- ETL run timestamp (UTC): `2026-11-14T01:47:16.254633+00:00`
- ETL pipeline version: `1.0`
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
