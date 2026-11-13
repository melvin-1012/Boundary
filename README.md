# SupeRR Intelligence

SupeRR Intelligence is a historical cricket analytics project for exploring
ball-by-ball IPL and T20I data. It combines source-data validation, a
reproducible ETL pipeline, pressure and player-performance analysis, ranking
and methodology reports, and an interactive Streamlit dashboard.

The project also includes a **Cricket Analyst** chat interface, local
MapReduce- and Spark-style demonstrations, exploratory machine-learning
models, a historical event replay, player-match graph analytics, and
Cassandra/HBase design examples.

> **Important:** Pressure definitions, SPI weights, eligibility thresholds,
> and player rankings are exploratory and provisional. They are not official
> Rajasthan Royals selection criteria. The official hackathon brief and
> domain approval are not present in this workspace. Review
> [submission readiness](./docs/SUBMISSION_READINESS.md) and the
> [implementation status](./docs/MASTER_IMPLEMENTATION_STATUS.md) before
> using results as an official submission.

## Contents

- [Features](#features)
- [Quick start](#quick-start)
- [Dashboard](#dashboard)
- [Cricket Analyst](#cricket-analyst)
- [Data and processing](#data-and-processing)
- [Analytics and methodology](#analytics-and-methodology)
- [Generated outputs](#generated-outputs)
- [Additional demonstrations](#additional-demonstrations)
- [Installation and requirements](#installation-and-requirements)
- [Rebuild the project outputs](#rebuild-the-project-outputs)
- [Tests and quality checks](#tests-and-quality-checks)
- [Limitations and responsible interpretation](#limitations-and-responsible-interpretation)
- [Repository map](#repository-map)
- [Project documentation](#project-documentation)

## Features

- **Historical IPL/T20I archive:** six supplied source CSV datasets, including
  deliveries, matches, competitions, teams, lineups, and competition-scoped
  player/team mappings.
- **Read-only source validation:** profiles schemas, missing data, duplicate
  and candidate keys, foreign-key relationships, cricket-specific anomalies,
  and source-file hashes.
- **ETL and derived data:** scopes the supported competition archive,
  reconstructs pre-delivery match state, derives pressure indicators, and
  writes processed and curated Parquet datasets without changing `data/raw/`.
- **Batter and bowler analytics:** pressure and non-pressure performance,
  player-level rates, consistency, reliability, eligibility, SPI, ranking
  exports, sensitivity analysis, and source evidence.
- **Interactive dashboard:** nine integrated views, selectable IPL and
  Rajasthan Royals palettes, dark/light appearance, shared filters, charts,
  tables, and downloads.
- **Cricket Analyst:** supported local natural-language analysis with
  calculated results and evidence; optional provider-backed investigation
  through bounded, read-only tools.
- **Reproducible demonstrations:** local Hadoop Streaming-compatible
  MapReduce, single-machine PySpark, machine-learning experiments, historical
  replay, and player-match graph analysis.
- **Database design examples:** query-oriented Cassandra and HBase artifacts.
  They are not live database integrations.

## Quick start

If the checked-out project already contains the processed archive, start the
dashboard from the project root:

```bash
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501).

To create an environment and install dependencies first, follow
[Installation and requirements](#installation-and-requirements).

## Dashboard

The app is `dashboard/app.py`. It uses one shared dashboard and theme
configuration; changing palette or appearance does not create a separate
dashboard.

| View | What it contains |
|---|---|
| **Match centre** | Overview KPIs, scoring trends, results, and match/innings exploration. |
| **Pressure Analytics** | Pressure states, metrics, and delivery-level context. |
| **Batting room** | Batter rankings, batting performance, and boundary analysis. |
| **Bowling lab** | Bowler rankings and bowling performance. |
| **Player Insights** | Player-level metrics, comparisons, and evidence. |
| **Methodology** | Metric definitions, methodology notes, and report access. |
| **Fixtures** | Historical matches from the supplied archive. |
| **Final Methodology & Validation** | Validation, sensitivity, ranking exports, provenance, and readiness. |
| **Cricket Analyst** | Natural-language questions, calculated results, comparisons, and evidence. |

### Themes, appearance, and filters

- **Rajasthan Royals Theme** is the default palette. It uses navy/blue with
  strategically applied pink accents.
- **IPL Theme** uses navy/blue surfaces with gold accents.
- **Dark mode** is the default appearance; light mode switches text to dark
  while retaining the selected theme accents.
- Competition, season, and team controls in the sidebar scope applicable
  dashboard views. The Cricket Analyst explicitly uses the full archive by
  default unless a question narrows its scope.
- The project logo is [superr_intelligence_logo.png](./dashboard/assets/superr_intelligence_logo.png).

The main CSS/theme and chart styles are implemented in `dashboard/app.py`.
The hero is rendered separately, so its theme colors are passed into its
embedded scene. Plotly charts receive their theme colors and layout settings
explicitly. Decorative cricket animation respects reduced-motion settings.

## Cricket Analyst

The **Cricket Analyst** tab answers questions using the supplied historical
archive. It supports a local calculation path and an optional tool-calling
provider path.

### Local analysis

Without an external provider, the app uses the project's local question
parser and analytics functions. Supported paths include:

- Pressure rankings, pressure strike rate, and bowling economy.
- Batter/bowler profiles and same-role player comparisons.
- Pressure versus normal performance.
- Season and IPL/T20I comparisons and historical trends.
- Powerplay, middle-over, and death-over analysis.
- Consistency, reliability, sample size, eligibility, and SPI explanations.
- Mapped team analysis and match-ID pressure analysis.
- Natural-language ranking comparisons: ordinal ranks, top-N, top-versus-
  average, and gaps between the top two.

Ranking defaults are pressure SPI, all available historical seasons and
competitions, and separate batter and bowler results when role is omitted.
The app never combines batter and bowler scores into one ranking. It uses the
existing SPI formula and eligibility rules, and reports when a requested
scope does not contain enough eligible players. A score gap is descriptive;
the project does not define an inferential test for statistical significance.

Examples:

```text
Who is the best batter under pressure in IPL 2023?
Who is the second most reliable bowler?
Compare the top three pressure performers
How much better is the best batter than the average batter?
How much better is the best player under pressure from the second best player?
Show batter Rinku Singh's pressure performance in death overs
Compare IPL and T20I batter pressure performance
Show batting pressure for match 34429
```

The local parser has explicit supported intents; it is not an unrestricted
general-purpose model. It does not infer a player's nationality or venue
country from their name, competition, or team.

### Optional provider-backed investigation

When configured, an OpenAI-compatible provider can select from allowlisted
tools to discover datasets, inspect schemas, look up players/teams/matches,
call existing player metrics, and run bounded read-only SQL. The application
executes calculations; the model is not trusted to supply numerical results.
The loop is bounded to eight rounds and twelve tool calls. The provider has
only been verified with mock responses in this workspace; no live provider
credentials were configured.

Set the environment variables before starting Streamlit:

```bash
export SUPERR_LLM_API_KEY="your-provider-key"
export SUPERR_LLM_MODEL="your-model-name"
# Optional; defaults to https://api.openai.com/v1
export SUPERR_LLM_BASE_URL="https://api.openai.com/v1"
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

The API key is sent only in the HTTP authorization header and is not placed in
the prompt or displayed in the dashboard. The configured provider receives
the question and the bounded context/results required for analysis; use only
an endpoint trusted to process that information.

The general query tool accepts only a single `SELECT` or `WITH ... SELECT`.
It limits access to registered tables/columns and approved SQL functions,
allows at most eight tables and 100 parameters, limits SQL to 8,000
characters, enforces a three-second execution timeout, and caps returned rows
at 500. Mutations, comments, multiple statements, unregistered tables, and
unapproved functions are rejected. No arbitrary Python or shell execution is
available to the model.

See the [Cricket Analyst guide](./docs/AI_CRICKET_ANALYST.md),
[architecture audit](./docs/AI_ANALYST_ARCHITECTURE.md), and
[test report](./docs/AI_ANALYST_TEST_REPORT.md) for detailed behavior,
configuration, and verification limits.

## Data and processing

### Source data

The six read-only source datasets live under `data/raw/`:

| File | Primary contents |
|---|---|
| `ball_by_ball.csv` | Delivery sequence, players, runs, extras, boundaries, and dismissals. |
| `matches.csv` | Match, date, teams, venue, results, and match context. |
| `competitions.csv` | Competition name, format, and season. |
| `teams.csv` | Competition-scoped team names and identifiers. |
| `playing_eleven.csv` | Match and team lineup observations. |
| `competition_team_player_mapping.csv` | Competition-scoped player/team IDs and names. |

Candidate keys and relationships are documented in
[data_dictionary.md](./docs/data_dictionary.md) and
[dataset_relationships.md](./docs/dataset_relationships.md), and machine-readable
metadata is stored under `data/metadata/`.

### ETL flow

The ETL in `ingestion/run_etl.py`:

1. Reads and profiles the supplied source files.
2. Validates columns, types, key candidates, relationships, and cricket
   consistency checks.
3. Selects the documented IPL/T20I analysis scope.
4. Writes processed and curated Parquet datasets outside `data/raw/`.
5. Reconstructs pre-delivery state and derives pressure features.
6. Produces a data-quality report, metadata, and source-hash provenance.

The transformations retain source anomalies and report them rather than
silently rewriting input records. See the [data dictionary](./docs/data_dictionary.md)
for current field interpretations.

### Data directories

| Path | Contents |
|---|---|
| `data/raw/` | Supplied source CSVs; treated as immutable inputs. |
| `data/processed/` | Processed source-aligned Parquet datasets. |
| `data/curated/` | Derived pressure deliveries and player/match metric data. |
| `data/metadata/` | Generated dictionary, relationships, and analyst catalog. |
| `data/sample/` | Sample or demonstration data, if present. |

## Analytics and methodology

`analytics/cricket_metrics.py` contains match-state reconstruction,
role-specific pressure scoring, batter/bowler metrics, and player ranking.
`analytics/build_rankings.py` generates rank exports, provenance and
sensitivity outputs. `analytics/final_validation.py` independently rebuilds
selected metrics from raw records and checks generated outputs.

### Pressure model

Pressure is a weighted, role-specific 0–100 state heuristic using run-rate
difficulty, wickets, innings time, and match closeness. Chase and first-
innings situations use different normalizations; batting and bowling pressure
are separate. The current pressure-event threshold is 50. It is not a win
probability, and its weights and threshold remain provisional.

### Player scoring

Batters and bowlers have separate performance metrics. Existing SPI combines
a baseline-relative performance component, match-level consistency, and
sample-exposure reliability using **60/20/20** weights. Current ranking
eligibility requires at least three pressure matches and twelve role-specific
pressure opportunities. These formulas and thresholds have not been
independently approved as official selection criteria. The
[pressure methodology notes](./docs/pressure_methodology.md) describe
normalization, attribution, sensitivity, and unresolved source semantics.

### Source-data limitations

Examples of documented caveats include repeated lineup candidate keys,
source boundary flags that do not always agree with `runs == 4/6`, extras
semantics that need authoritative confirmation, a nonzero-runs leg-byes
record, and revised-target/super-over conventions that require review. The
project preserves these records and reports the limitations. Local arithmetic
validation is not an independent scorecard oracle.

## Generated outputs

The `reports/` directory contains generated analysis outputs. Important files
include:

| Path | Purpose |
|---|---|
| `reports/data_quality_report.json` | ETL validation results, source profiles, and warnings. |
| `reports/final_validation.json` | Independent source-to-curated validation and hashes. |
| `reports/final_rankings.json` | Ranking run, method version, sensitivity, and provenance. |
| `reports/top_10_batters.csv`, `reports/top_10_bowlers.csv` | Current top-ten exports. |
| `reports/final_top10_batters.csv`, `reports/final_top10_bowlers.csv` | Final-validation ranking snapshots. |
| `reports/full_batter_ranking.csv`, `reports/full_bowler_ranking.csv` | Full eligible ranking tables. |
| `reports/all_batter_metrics.csv`, `reports/all_bowler_metrics.csv` | Supporting role metrics. |
| `reports/methodology_report.md` | Generated methodology, validation, ranking, and limitation report. |
| `reports/mapreduce/`, `reports/spark/`, `reports/streaming/` | Local computation/replay outputs and validation. |
| `reports/machine_learning/` | Model metrics, cluster outputs, plots, and saved model files. |
| `reports/graph/` | Graph summary, PageRank output, and HTML visualization. |

Outputs are snapshots of a specific run. Regenerate related outputs together,
and consult the recorded hashes/run ID before comparing reports or dashboard
tables. Rankings remain provisional.

## Additional demonstrations

All commands below operate on historical project data and run locally unless
otherwise noted.

### Hadoop-compatible MapReduce

```bash
.venv/bin/python -m hadoop.run_mapreduce
```

Runs a local mapper/combiner/reducer pipeline and compares its result with a
pandas aggregation. It does **not** upload data to HDFS or prove a Hadoop
cluster is deployed.

### Spark

```bash
.venv/bin/python -m spark.run_spark
```

Runs the PySpark pipeline in local mode and checks output against the pandas
oracle. This is not a multi-node Spark deployment; a compatible Java runtime
is needed by PySpark.

### Historical event replay

```bash
.venv/bin/python -m streaming.replay
```

Replays the historical delivery sequence and validates incremental state
against the batch-enriched archive. It does not connect to Kafka or a
production streaming service.

### Machine learning

```bash
.venv/bin/python -m machine_learning.run_models
```

Runs exploratory boundary-classification models and player-metric clustering.
These outputs are demonstrations; they are not used in SPI or ranking
calculations.

### Player-match graph

```bash
.venv/bin/python -m graph_analytics.run_graph
```

Builds a graph from observed player-match participation and exports
PageRank/visualization results. Graph scores are supplementary and do not
enter SPI.

### Cassandra and HBase examples

`databases/cassandra_schema.cql` and `databases/hbase_demo.hbase` describe
query-oriented schemas and sample commands. They are design artifacts only:
this project does not provide or claim a running Cassandra or HBase service.
See [databases/README.md](./databases/README.md) for the sample access
patterns and caveats.

## Installation and requirements

- Python **3.12** is the project target.
- Python package versions are pinned in [requirements.txt](./requirements.txt).
- The standard ETL, analytics, Cricket Analyst local mode, and dashboard use
  local files; no external database or streaming broker is required.
- Optional Spark execution requires a Java runtime compatible with PySpark.
- No LLM package is required for provider support; the HTTP client uses the
  Python standard library.

Create and install a virtual environment from the project root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Use `.venv/bin/python` and `.venv/bin/streamlit` for the commands below. The
modules expect to run from the project root so their relative data and output
paths resolve correctly.

The pinned stack includes pandas/NumPy for data manipulation and calculations,
PyArrow for Parquet, Streamlit and Plotly for the dashboard, PySpark for the
local Spark example, scikit-learn/SciPy/joblib for machine learning, and
NetworkX for graph analysis. See [requirements.txt](./requirements.txt) for
the exact versions.

## Rebuild the project outputs

Run the core pipeline in order:

```bash
# Validate source inputs, rebuild processed/curated data and metadata.
.venv/bin/python -m ingestion.run_etl

# Rebuild batter/bowler metrics, rankings, sensitivity and provenance.
.venv/bin/python -m analytics.build_rankings

# Rebuild independent validation evidence and source hashes.
.venv/bin/python -m analytics.final_validation

# Rebuild the methodology report from the current generated outputs.
.venv/bin/python -m analytics.build_methodology_report
```

To regenerate the standalone analyst data catalog:

```bash
.venv/bin/python -m analytics.analyst_tools
```

To inspect source CSV shapes and generate metadata independently:

```bash
.venv/bin/python -m ingestion.explore_dataset
.venv/bin/python -m ingestion.data_dictionary
.venv/bin/python -m ingestion.dataset_relationships
```

The ETL and validation tools read `data/raw/`; do not edit the supplied raw
records to resolve a warning. Fixes to derived outputs should be made in the
processing code and documented with a reproducible validation.

## Tests and quality checks

Run the full test suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Compile the Python project:

```bash
.venv/bin/python -m py_compile \
  analytics/*.py dashboard/*.py graph_analytics/*.py ingestion/*.py \
  machine_learning/*.py streaming/*.py tests/*.py
```

The tests cover raw-data immutability, validation, derived cricket state,
metrics and ranking determinism, output hashes and shapes, the Cricket
Analyst's tools and natural-language examples, dashboard rendering/themes,
machine-learning outputs, graph calculations, and replay behavior. Passing
tests establish software behavior; they do not establish that the provisional
cricket methodology is officially approved.

## Limitations and responsible interpretation

- The official Rajasthan Royals problem statement was not available in this
  workspace; official scope and requirements are unverified.
- Pressure labels are heuristic. SPI, weights, opportunity thresholds,
  comparisons, and rankings remain provisional and need cricket-domain
  approval.
- IPL/T20I analysis is limited to the supplied historical archive; it is not
  a live feed or complete player-career record.
- Source anomalies are retained and reported. The methodology report lists
  unresolved extras, boundary, lineup, revised-target, and super-over
  questions.
- The optional LLM tool-call path was tested with mock responses, not a live
  model. Local Cricket Analyst calculations do not require a provider.
- MapReduce, Spark, streaming, Cassandra, and HBase examples must not be
  represented as deployed distributed services.

For current project blockers and readiness, see
[SUBMISSION_READINESS.md](./docs/SUBMISSION_READINESS.md),
[PROJECT_AUDIT.md](./docs/PROJECT_AUDIT.md), and
[MASTER_IMPLEMENTATION_STATUS.md](./docs/MASTER_IMPLEMENTATION_STATUS.md).

## Repository map

```text
analytics/       Pressure/player metrics, rankings, validation, analyst tools
dashboard/       Streamlit application and logo asset
data/raw/        Supplied source CSVs (read-only inputs)
data/processed/  Processed source-aligned Parquet
data/curated/    Curated pressure/player datasets
data/metadata/   Data dictionary, relationships, analyst catalog
databases/       Cassandra/HBase design examples
docs/            Architecture, methodology, audit, and operating guides
graph_analytics/ Player-match graph and PageRank demonstration
hadoop/          Local Hadoop Streaming-compatible MapReduce
ingestion/       Data exploration, validation, metadata, and ETL
machine_learning/Boundary models and player clustering
reports/         Generated rankings, validation, and experiment outputs
spark/           Local PySpark pipeline
streaming/       Historical event replay
tests/           Unit and dashboard integration tests
```

## Project documentation

- [Master implementation status](./docs/MASTER_IMPLEMENTATION_STATUS.md)
- [Project audit](./docs/PROJECT_AUDIT.md)
- [Project progress](./docs/PROJECT_PROGRESS.md)
- [Submission readiness](./docs/SUBMISSION_READINESS.md)
- [Architecture and data flow](./docs/architecture.md)
- [Pressure methodology](./docs/pressure_methodology.md)
- [Data dictionary](./docs/data_dictionary.md)
- [Dataset relationships](./docs/dataset_relationships.md)
- [Cricket Analyst guide](./docs/AI_CRICKET_ANALYST.md)
- [Cricket Analyst architecture audit](./docs/AI_ANALYST_ARCHITECTURE.md)
- [Cricket Analyst test report](./docs/AI_ANALYST_TEST_REPORT.md)
- [Generated methodology report](./reports/methodology_report.md)
- [Database design notes](./databases/README.md)
- [Final presentation outline](./docs/final_presentation.md)
