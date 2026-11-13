# Pressure Methodology — Exploratory Implementation

**Status: implemented, but provisional.** The current code provides a
traceable heuristic for development and sensitivity analysis. The supplied
master specification requires the final pressure rules and scoring choices
to be justified and reviewed; these values must not be presented as
scientifically established or as an official final ranking methodology.

## State reconstruction

Deliveries are ordered by `(match_id, innings, innings_ball_num)`. For each
delivery the curated output stores the state immediately before that event:
score, wickets, legal balls, balls remaining, current run rate, target, runs
required, required run rate, innings phase, batter, non-striker, bowler,
competition, and match result.

- Team runs use `runs + extras1_runs + extras_2_runs`.
- A wide and `Overstep` do not increment the legal-ball count. Batter balls
  faced exclude wides but include `Overstep`.
- Normal innings limits use match revised-overs fields when present, otherwise
  20 overs. Innings 3 and 4 are treated as one-over super overs.
- Chases in innings 2 and 4 use the previous innings' observed total plus one;
  `revised_target` overrides the second-innings target when present.
- Current scoring references use the median of up to the five or more prior
  first-innings rates within match format. The first five available matches
  use explicit fallback rates of 8.0 for T20 and 7.5 for T20I. No current-match
  or future-match result is used as a pressure feature.

## Pressure components

Each component is clipped to `[0, 1]`; elapsed time and wickets are normalized
to their innings limits. The implemented score is

`P = 100 * (wR + wW + wT + wC)`.

The current batting weights are `(R=.35, W=.25, T=.20, C=.20)` and bowling
weights are `(R=.30, W=.25, T=.20, C=.25)`. They sum to one but remain
heuristic pending review.

For a chase, `r = required_run_rate / reference_run_rate`:

- Batting `R = clip((r - 1) / 1.5, 0, 1)`.
- Batting `W = wickets_lost / 10`.
- Batting `T = innings_progress`.
- Batting `C = exp(-abs(r - 1))`.
- Bowling `R = clip((1 - r) / 1.5, 0, 1)`.
- Bowling `W = wickets_remaining / 10`.
- Bowling `T = innings_progress`.
- Bowling `C = exp(-abs(r - 1))`.

For first innings (including the first innings of a super over), `q` is current
run rate and `b` is the format-specific historical reference:

- Batting `R = clip((b - q) / b, 0, 1) * innings_progress`.
- Batting `W = wickets_lost / 10`.
- Batting `T = innings_progress`.
- Bowling `R = clip((q - b) / b, 0, 1) * innings_progress`.
- Bowling `W = wickets_remaining / 10`.
- Both sides use `C = exp(-abs(q - b) / b) * innings_progress`.

An event is flagged as pressure when its score is at least 50. That cutpoint,
the component weights, format fallback rates, and the sample policy are
explicitly provisional. Sensitivity scenarios are generated alongside
rankings; a large rank change is evidence of model fragility, not a basis for
choosing whichever list is preferred.

## Player performance and rankings

Batters use source `runs`, faced balls, source boundary flags, and dismissal
events. Bowlers use legal balls, runs conceded after excluding byes/leg-byes/
penalties, and only the recorded Bowled/Caught/LBW/Stump/Hit Wicket dismissal
types as bowler wickets. The field meaning of `other` extras and one
non-zero-runs leg-bye event remain unresolved.

Normal-versus-pressure differences are shrunk toward competition-level
pressure/normal run rates using a 30-ball prior. Reliability is
`n / (n + 30)`. Match-to-match consistency uses `100 / (1 + CV)` of
match-level pressure rates. The SPI currently combines normalized,
shrunk performance (60%), consistency (20%), and reliability (20%). The
performance component uses a robust median-absolute-difference scale and a
bounded tanh transform. The uncertainty column is `1/sqrt(n)`, a relative
sample-size proxy, **not** a confidence interval.

Eligibility currently requires pressure exposure in at least three distinct
matches and at least 12 pressure balls. These operational floors are not
official criteria. The generator compares 2/6 and 5/24 alternatives and
alternative model thresholds and weights.

## Limitations

- No official pressure labels or match win probabilities are supplied.
- The score is a context heuristic, not a trained or validated probability.
- The one-over super-over assumption is based on observed innings 3/4 and
  requires source-level confirmation.
- `runs`, `other` extras, revised-overs, and boundary flags need authoritative
  source definitions.
- The format baseline falls back to fixed values before enough prior innings
  exist.
- The top-ten results remain provisional until the pressure definition,
  component weights, pressure cutpoint, and eligibility rule are reviewed.

## Final validation increment (2026-11-13)

The official Round 1 brief and `MASTER_SPECIFICATION.md` were not available in
the workspace. The current request's scope is 2022 onward, exact-metadata IPL
seasons plus T20I-format competitions; the generated source manifest covers
853 matches (371 IPL, 482 T20I) and 194,014 deliveries. The calculations below
do not establish official scope approval.

The raw-to-curated audit independently rebuilt batter runs, team runs, legal
balls, bowler-conceded runs, bowler-credit wickets, boundary flags, and chase
targets from the raw rows. All checked values match across 194,014 rows with
zero orphans; all six raw SHA-256 values match ETL provenance. This is not an
independent source-scorecard oracle. Scoped data has 20 four-flag and 3
six-flag disagreements against `runs == 4/6`, 2 rows with extras but no extras
type, and 260 `other` extras rows. No source row was changed.

Measured pressure sensitivity against threshold 50:

| Role | Threshold | Pressure deliveries | Eligible players | Top-10 Jaccard vs 50 |
|---|---:|---:|---:|---:|
| Batter | 40 | 55,326 | 314 | 0.176 |
| Batter | 50 | 23,870 | 272 | 1.000 |
| Batter | 60 | 9,360 | 186 | 0.176 |
| Bowler | 40 | 124,766 | 410 | 0.053 |
| Bowler | 50 | 57,779 | 336 | 1.000 |
| Bowler | 60 | 4,646 | 109 | 0.053 |

Removing the "closeness" term changes top-ten overlap to 0.429 for batters
and 0.000 for bowlers. Wickets/time pressure components have absolute
Spearman rho 0.768 for both roles. The closeness term peaks at rate parity and
overlaps the rate-difficulty term; bowling wickets remaining may signify
wicket-taking opportunity rather than pressure. Keep the existing formula
only as a provisional, transparent baseline pending expert review; do not
select a replacement because it favors any player.

The SPI formula remains 60/20/20 for this run, not as an approved methodology.
Exposure appears in both performance shrinkage and reliability, which may
double-count sample size. Reliability-removal and alternative component
weight scenarios are retained in `reports/final_rankings.json`. Independently
recomputed exported SPI values have maximum error 0.0 for each role.

See `reports/final_validation.json` for raw examples and complete checks,
`reports/final_rankings.json` for run hashes/sensitivity, and
`reports/methodology_report.md` for ranking evidence. The official brief and
domain approval remain blockers.
