# SupeRR Intelligence

Cricket pressure analytics over the supplied ball-by-ball archive. The project
contains source-data validation and ETL, match-state reconstruction, provisional
pressure/SPI rankings, local Hadoop-compatible and Spark demonstrations,
exploratory ML, historical event replay, graph/PageRank analysis, and a
Streamlit dashboard.

> **Scope and status:** rankings, pressure weights, and exposure eligibility
> remain provisional. The official Rajasthan Royals hackathon statement was
> not supplied. Kafka, Hadoop/HDFS, Cassandra, and HBase services are not
> deployed here; local replay and schema demonstrations are labeled as such.

## Environment

- Python 3.12
- Install the pinned Python dependencies in [`requirements.txt`](./requirements.txt)
- No additional services are required for the local data, ML, graph, replay, or
  dashboard workflows.
- The project does not modify the source files in `data/raw/`.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run the pipeline

Run from the project root:

```bash
.venv/bin/python -m ingestion.run_etl
.venv/bin/python -m analytics.build_rankings
.venv/bin/python -m machine_learning.run_models
.venv/bin/python -m streaming.replay
.venv/bin/python -m graph_analytics.run_graph
.venv/bin/python -m analytics.build_methodology_report
```

Optional local big-data demonstrations:

```bash
.venv/bin/python -m hadoop.run_mapreduce
.venv/bin/python -m spark.run_spark
```

`hadoop.run_mapreduce` uses local Python subprocesses and does not upload data
to HDFS. `spark.run_spark` uses `local[2]` and is not a multi-node cluster
deployment. The replay is a historical simulation, not Kafka.

## Start the dashboard

```bash
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

The app includes Match centre, Pressure Analytics, Batting room, Bowling lab,
Player Insights, Methodology, and Fixtures views. Its sidebar competition,
season, and team filters scope match and pressure/player exploration. Exported
top-ten tables intentionally remain tied to the same provisional generated
ranking files rather than being recalculated differently in the UI. IPL and
Rajasthan Royals themes are selectable.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m py_compile analytics/*.py dashboard/*.py graph_analytics/*.py ingestion/*.py machine_learning/*.py streaming/*.py tests/*.py
```

The automated suite covers data and cricket calculations, raw-source hash
immutability, rank-file consistency and independent player examples, grouped
ML evaluation, graph construction, incremental replay, and Streamlit
render/theme switching.

## Outputs and documentation

- Processed and curated data: `data/processed/`, `data/curated/`
- Top-ten and full rankings: `reports/top_10_*.csv`,
  `reports/full_*_ranking.csv`
- Supporting metrics: `reports/all_*_metrics.csv`
- Quality, replay, ML, graph, MapReduce, and Spark evidence: `reports/`
- Formula and ranking evidence: [`reports/methodology_report.md`](./reports/methodology_report.md)
- Current status and blockers: [`docs/MASTER_IMPLEMENTATION_STATUS.md`](./docs/MASTER_IMPLEMENTATION_STATUS.md)
- Audit and incremental work log: [`docs/PROJECT_AUDIT.md`](./docs/PROJECT_AUDIT.md),
  [`docs/PROJECT_PROGRESS.md`](./docs/PROJECT_PROGRESS.md)
- Architecture and data-flow diagrams: [`docs/architecture.md`](./docs/architecture.md)
- NoSQL design-only demonstration: [`databases/README.md`](./databases/README.md)
- Submission readiness: [`docs/SUBMISSION_READINESS.md`](./docs/SUBMISSION_READINESS.md)
- Presentation outline: [`docs/final_presentation.md`](./docs/final_presentation.md)
