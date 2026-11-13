# SupeRR Intelligence — presentation outline

## Slide 1 — The question

How can match context reveal when a delivery is demanding, and how can player
contributions in those situations be compared transparently?

## Slide 2 — The data foundation

Show the six supplied sources, exact-metadata scope selection, source-quality
checks, and raw-file immutability. Mention that source-field discrepancies are
retained and disclosed.

## Slide 3 — From ball to match state

Explain pre-delivery score, wickets, legal balls, target, required run rate,
and phase. Show the data-flow and pressure flow diagrams in
[`architecture.md`](./architecture.md).

## Slide 4 — Pressure and player metrics

Describe separate batter/bowler pressure components and why the score is a
heuristic rather than a win probability. Demonstrate pressure strike rate,
economy, match consistency, and sample exposure.

## Slide 5 — SPI and evidence

Present the reproducible provisional 60/20/20 formula, candidate counts,
sensitivity to thresholds/weights, and the evidence-backed top-ten exports.
Emphasize that the official problem statement and domain approval are
outstanding.

## Slide 6 — Big-data and analytical demonstrations

Distinguish local MapReduce and `local[2]` Spark from a distributed cluster.
Summarize the match-held-out ML experiment, deterministic replay parity, and
player-match PageRank as supplementary analysis.

## Slide 7 — Product

Demonstrate the selectable IPL/Rajasthan Royals themes, filters, pressure
timeline/events, exported rankings, player insights, methodology, and fixtures
in the existing Streamlit application.

## Slide 8 — Limitations and next steps

Request the official requirements and expert validation; identify unavailable
Hadoop/HDFS, Kafka, Cassandra, and HBase services; state that rankings are
provisional and not selection advice.

## Suggested demo sequence

1. Run ETL and verify its quality report.
2. Show one match’s state/pressure timeline and event explanations.
3. Show top-ten evidence and download the generated CSVs.
4. Switch themes and visit the dashboard’s analytical views.
5. Show local replay mismatch counts and explain infrastructure limitations.

This outline is a prepared presentation script, not a rendered slide deck or
recorded video.
