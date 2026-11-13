# Data Dictionary

The generated column-level dictionary is
[`data/metadata/data_dictionary.csv`](../data/metadata/data_dictionary.csv).
It records each CSV column's inferred pandas dtype, null count, distinct
non-null count, whether it participates in a candidate key, and up to three
observed values. It is generated from the current source files; it does not
assert that every inferred dtype or field meaning is authoritative.

Regenerate it together with the processed data using:

```bash
.venv/bin/python -m ingestion.run_etl
```

## Source tables

| Dataset | Candidate key | Contents |
|---|---|---|
| `competitions.csv` | `comp_id` | Competition name, match format, and season |
| `matches.csv` | `match_id` | Competition, teams, date, result, venue, and match context |
| `teams.csv` | `(comp_id, team_id)` | Competition-scoped team names |
| `playing_eleven.csv` | Candidate only: `(match_id, team_id, player_id)` | Match squad/lineup observations; repeated keys are retained |
| `competition_team_player_mapping.csv` | `(comp_id, team_id, player_id)` | Competition-scoped player/team name mapping |
| `ball_by_ball.csv` | `(match_id, innings, innings_ball_num)` | Delivery, player, scoring, extras, and dismissal observations |

## Important field interpretations in the derived data

- `runs` is retained as the source-provided batter-runs measure. One row is
  tagged as leg-byes while containing nonzero `runs`; this remains an unresolved
  source inconsistency and is not silently rewritten.
- `team_runs = runs + extras1_runs + extras_2_runs`.
- `is_legal_ball` excludes source extras types `wide` and `Overstep`.
- `is_batter_ball_faced` excludes wides; no-balls remain faced-ball events.
- `bowler_conceded_runs` excludes `byes`, `legbyes`, and `Penalty` extras.
  The meaning of `other` extras has not been established and remains included.
- Bowler-credited wickets use observed `Bowled`, `Caught`, `LBW`, `Stump`, and
  `Hit Wicket` dismissal labels. Other labels are not credited.
- Boundary metrics use the source `is_four` and `is_six` flags. They are not
  reconstructed from `runs`, because the fields disagree on 23 rows.

These are explicit, provisional calculation rules, not claims that the source
provider's field definitions have been independently confirmed.

