# SupeRR Intelligence

SupeRR Intelligence is a historical cricket analytics project built around
ball-by-ball IPL and T20I data. It includes a reproducible data pipeline,
exploratory pressure and player-performance analysis, ranking exports, a
Streamlit dashboard, and a local evidence-backed cricket question analyst.

The project is intended for analysis and demonstration. **Pressure weights,
SPI formulas, eligibility rules, and the resulting rankings are provisional,
not official Rajasthan Royals selection criteria.** The official hackathon
problem statement and domain approval are not available in this workspace.
Review [`docs/MASTER_IMPLEMENTATION_STATUS.md`](./docs/MASTER_IMPLEMENTATION_STATUS.md)
and [`docs/SUBMISSION_READINESS.md`](./docs/SUBMISSION_READINESS.md) before
using results as a final submission.

## What is included

- **Historical archive:** six source CSVs in `data/raw/`, with data definitions
  and relationships documented under `data/metadata/` and `docs/`.
- **ETL and validation:** source profiling, integrity checks, match-state
  reconstruction, pressure indicators, and processed/curated Parquet outputs.
- **Cricket analytics:** batter and bowler metrics, pressure-versus-normal
  comparisons, provisional SPI scores, sensitivity checks, and ranking
  exports.
- **Streamlit dashboard:** nine views for match exploration, pressure,
  batting, bowling, player insights, methodology, fixtures, final validation,
  and the Cricket Analyst.
- **Supporting demonstrations:** local MapReduce-compatible processing,
  single-machine Spark, machine-learning experiments, historical event replay,
  and player-match graph analysis. These do not imply deployed Hadoop, Kafka,
  Cassandra, HBase, or multi-node Spark services.

## Dashboard

Start the app from the project root:

```bash
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

Open [http://localhost:8501](http://localhost:8501). The sidebar provides:

- **Theme:** Rajasthan Royals Theme or IPL Theme. Rajasthan Royals is the
  default.
- **Appearance:** Dark mode or Light mode. Dark mode is the default.
- **Filters:** competition, season, and team. These scope the applicable
  match, pressure, and player views.

Both palettes share the same dashboard and theme configuration. Dark surfaces
use light text; light surfaces use dark text. Theme accents remain pink for
Rajasthan Royals and gold for IPL. The supplied SupeRR artwork is located at
`dashboard/assets/superr_intelligence_logo.png`.

The dashboard views are:

1. **Match centre** — scoring trends, results, and match/innings exploration.
2. **Pressure Analytics** — pressure states, metrics, and delivery evidence.
3. **Batting room** — batting and boundary analysis.
4. **Bowling lab** — bowling performance analysis.
5. **Player Insights** — player-level comparisons and metrics.
6. **Methodology** — current metric definitions and methodology reporting.
7. **Fixtures** — historical match listings.
8. **Final Methodology & Validation** — validation evidence, sensitivity,
   ranking outputs, and submission-readiness status.
9. **Cricket Analyst** — locally calculated, evidence-backed supported
   questions, with optional provider-backed dynamic investigation through
   bounded data tools.

### Cricket Analyst

The analyst can answer implemented question paths for pressure performance,
player comparisons, season and competition comparisons, phase-specific
performance, consistency, reliability, SPI/rank explanations, sample size,
team-scoped queries, and match-level pressure. Use explicit roles and filters
for clearer results. Examples:

```text
Who is the best batter under pressure in IPL 2023?
Who is the best bowler under pressure in T20I 2024?
Compare batter Rinku Singh and David Miller under pressure
Show batter <name> pressure performance in death overs
Show batting pressure for match <match ID>
```

The local mode calculates supported questions from the curated delivery
archive and verifies evidence against source player and match identifiers.
When an OpenAI-compatible provider is configured, the analyst can also
discover available datasets, inspect schemas, call existing role metrics, and
run guarded read-only analytical queries through an allowlisted tool loop.
Unsupported or ambiguous requests should receive a clarification or an
insufficient-evidence response; venue- and nationality-based analyses are not
inferred from names.

An external OpenAI-compatible provider is **optional**. Without it, the
documented local parser remains available but does not support arbitrary
question formulations. Provider-backed tool calling has been tested with
mocked responses, not a live model; no live provider credentials were
available for verification. To enable dynamic tool calling, set these
environment variables before starting Streamlit:

Ranking questions default to the existing pressure SPI and all available
historical scope. If no role is specified, the analyst returns separate
batter and bowler rankings. Rank gaps, top-N comparisons, and comparisons
against the eligible-player average use the existing formulas and eligibility
rules; insufficient eligible samples are reported rather than backfilled.

```bash
export SUPERR_LLM_API_KEY="your-provider-key"
export SUPERR_LLM_MODEL="your-model-name"
# Optional; defaults to https://api.openai.com/v1
export SUPERR_LLM_BASE_URL="https://api.openai.com/v1"
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

Do not commit credentials. When configured, the question, bounded catalog
context, and results required for the analysis are sent to the configured
provider. SQL tools accept only bounded, single SELECT/WITH...SELECT queries
over registered tables. Numerical results are calculated by application
tools, not by the model. See
[`docs/AI_CRICKET_ANALYST.md`](./docs/AI_CRICKET_ANALYST.md) for operating
modes, tool limits, supported local intents, and safety details.

## Requirements and installation

- Python 3.12
- Packages pinned in [`requirements.txt`](./requirements.txt)
- No external database, streaming broker, or cluster is required for the
  standard local pipeline and dashboard.

Create an isolated environment and install dependencies:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Use the virtual environment's Python and Streamlit executables in the commands
below. Run module commands from the repository root so project-relative data
and report paths resolve correctly.

## Data pipeline and analysis

The existing archive lets you run the dashboard directly. To regenerate
processed data and analytics, run the modules in this order:

```bash
# Validate/profile source records and rebuild processed/curated datasets.
.venv/bin/python -m ingestion.run_etl

# Rebuild batter/bowler metrics, SPI rankings, and ranking manifests.
.venv/bin/python -m analytics.build_rankings

# Rebuild the methodology report from the current analytical outputs.
.venv/bin/python -m analytics.build_methodology_report
```

Additional reproducible local demonstrations:

```bash
.venv/bin/python -m machine_learning.run_models
.venv/bin/python -m streaming.replay
.venv/bin/python -m graph_analytics.run_graph
```

Optional local big-data examples:

```bash
.venv/bin/python -m hadoop.run_mapreduce
.venv/bin/python -m spark.run_spark
```

These are deliberately bounded demonstrations: MapReduce runs locally and
does not upload to HDFS; Spark uses a local session rather than a multi-node
cluster; streaming replays historical records rather than consuming Kafka.
Cassandra and HBase artifacts are schema/query demonstrations, not live
database integrations.

## Data layout and outputs

| Location | Contents |
|---|---|
| `data/raw/` | Supplied source CSV files. The ETL reads these and does not edit them. |
| `data/processed/` | Source-shaped and validated Parquet datasets. |
| `data/curated/` | Derived delivery-pressure and batter/bowler metric Parquet datasets. |
| `data/metadata/` | Machine-readable data dictionary and dataset relationships. |
| `reports/top_10_batters.csv`, `reports/top_10_bowlers.csv` | Current provisional top-ten exports. |
| `reports/full_batter_ranking.csv`, `reports/full_bowler_ranking.csv` | Full provisional ranking outputs. |
| `reports/all_batter_metrics.csv`, `reports/all_bowler_metrics.csv` | Supporting player metric exports. |
| `reports/final_rankings.json` | Ranking run and input/output provenance. |
| `reports/final_validation.json`, `reports/data_quality_report.json` | Validation and quality evidence. |
| `reports/methodology_report.md` | Generated methodology, sensitivity, ranking, and limitation report. |
| `reports/machine_learning/`, `reports/graph/`, `reports/streaming/`, `reports/spark/`, `reports/mapreduce/` | Results from the corresponding local analyses/demonstrations. |

Generated rankings and reports are only as authoritative as their documented
assumptions. Do not describe them as final selections while methodology or
source-data ambiguities remain unresolved.

## Methodology and limitations

The pipeline records match state and batting/bowling pressure indicators from
the historical delivery data, then calculates role-specific player metrics
and SPI rankings. The methodology report and validation artifacts document
the currently implemented formulas, thresholds, sensitivity results,
eligibility, and run provenance.

Important caveats:

- Pressure thresholds, weights, SPI choices, and minimum-opportunity rules
  remain exploratory and need domain approval.
- The official Rajasthan Royals challenge brief was not supplied, so alignment
  with official requirements is unverified.
- Source-data ambiguities and anomalies are reported, not silently corrected.
  See the data quality report and methodology report for specific cases.
- IPL and T20I comparisons use only the supplied historical archive; they are
  not real-time feeds or comprehensive career records.
- AI commentary is optional and has not been validated against a live provider
  in this environment. The local analytics path does not require an LLM.

## Tests and checks

Run the complete test suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Compile the Python modules:

```bash
.venv/bin/python -m py_compile \
  analytics/*.py dashboard/*.py graph_analytics/*.py ingestion/*.py \
  machine_learning/*.py streaming/*.py tests/*.py
```

Tests cover source-data validation and immutability, cricket calculations,
ranking exports and provenance, analytics evidence, graph construction,
machine-learning evaluation, historical replay, and Streamlit dashboard
rendering/theme switching. They verify software behavior, not external
methodology approval.

## Project documentation

- [Master implementation status](./docs/MASTER_IMPLEMENTATION_STATUS.md)
- [Project audit](./docs/PROJECT_AUDIT.md)
- [Project progress](./docs/PROJECT_PROGRESS.md)
- [Submission readiness](./docs/SUBMISSION_READINESS.md)
- [AI Cricket Analyst guide](./docs/AI_CRICKET_ANALYST.md)
- [AI Analyst architecture audit and implementation status](./docs/AI_ANALYST_ARCHITECTURE.md)
- [AI Analyst test report](./docs/AI_ANALYST_TEST_REPORT.md)
- [Methodology report](./reports/methodology_report.md)
- [Pressure methodology notes](./docs/pressure_methodology.md)
- [Architecture](./docs/architecture.md)
- [Data dictionary](./docs/data_dictionary.md)
- [Dataset relationships](./docs/dataset_relationships.md)
- [Final presentation outline](./docs/final_presentation.md)
- [Database demonstration notes](./databases/README.md)
