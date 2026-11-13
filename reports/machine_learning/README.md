# Exploratory Cricket Machine Learning

> These analyses are separate from SPI and are not used in the player rankings.

Classification objective: Predict whether the current delivery is a four or six.

Features: innings, score_before, wickets_before, legal_balls_before, balls_remaining, wickets_remaining, innings_progress, current_run_rate, required_run_rate, reference_run_rate.

Validation: {'method': 'GroupShuffleSplit by match_id', 'test_fraction': 0.25, 'random_state': 42, 'train_matches': 627, 'test_matches': 210, 'train_rows': 145280, 'test_rows': 48734, 'match_overlap': 0}.

| Model | Accuracy | Balanced accuracy | Precision | Recall | F1 | ROC AUC |
|---|---:|---:|---:|---:|---:|---:|
| decision_tree | 0.5628 | 0.5573 | 0.2143 | 0.5486 | 0.3082 | 0.5782 |
| random_forest | 0.6068 | 0.5596 | 0.2223 | 0.4865 | 0.3051 | 0.5863 |

## Player clustering

### Batters

- Features: pressure_strike_rate, pressure_boundary_percentage, pressure_dot_ball_percentage, consistency, pressure_opportunities
- Selected K: 2 (best silhouette 0.3156 across K=2–6)
- Cluster sizes: `{'0': 270, '1': 199}`
- Interpretation: Clusters group standardized observed pressure metrics; cluster IDs are arbitrary and do not imply player quality or causal style.

### Bowlers

- Features: pressure_economy, pressure_wickets, pressure_dots, pressure_boundaries, pressure_opportunities, consistency
- Selected K: 2 (best silhouette 0.4832 across K=2–6)
- Cluster sizes: `{'0': 326, '1': 86}`
- Interpretation: Clusters group standardized observed pressure metrics; cluster IDs are arbitrary and do not imply player quality or causal style.

## Limitations

- This is an exploratory delivery-event classifier, not a player-selection model.
- A match-held-out random split prevents same-match leakage but is not a chronological future-season test.
- The supplied archive is observational; feature importance is association, not causal impact.
- A majority-class baseline is reported because boundary events are a minority class.
- K-means is exploratory, sensitive to scaling and selected K; clusters are not rankings.
- Historical dataset coverage and source-field ambiguities limit external validity.

Run with `.venv/bin/python -m machine_learning.run_models` from the project root.
