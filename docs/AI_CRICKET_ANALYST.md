# AI Cricket Analyst

## Status

The analyst is implemented in `analytics/cricket_analyst.py` and is available
as the **AI Cricket Analyst** tab in `dashboard/app.py`. It calculates answers
from the read-only curated delivery archive via the existing metric and
ranking functions and reports source-backed match evidence. The pressure
labels and SPI remain provisional; the analyst does not promote them to
official selection criteria.

The dashboard tests exercise the tab, an actual historical-player query,
theme reruns, and the local analytics path. The live local browser rendered
the new tab and returned a verified Rinku Singh result with match evidence.
External LLM behavior is not verified because no provider credentials are
configured in this workspace.

## Data and safety

- Analytics read `data/curated/pressure_deliveries.parquet` and recalculate
  filtered summaries with the existing metric/ranking helpers. The analyst
  never writes to the database or source data.
- The question interpreter uses an allowlisted JSON schema. Player IDs,
  seasons, formats, competitions, phases, matches, and teams are validated
  against the loaded archive before filtering.
- SQL and command-like inputs are rejected; there is no SQL execution path.
- Player pressure rates and normal baselines are independently recomputed
  from filtered delivery records before display. Match IDs and player IDs in
  evidence must exist in the same filtered source data.
- A configured LLM may classify the question and provide qualitative
  commentary. It does not calculate statistics. Numerical claims in its
  commentary are rejected, and the UI always displays application-calculated
  values separately.
- Without an LLM key, the local rule-based interpreter remains usable. If
  configured interpretation fails, the dashboard reports the issue and falls
  back to that parser.

## Supported query paths

Use explicit roles and filters for reliable results. Examples:

- `Who is the best batter under pressure in IPL 2023?`
- `Who is the best bowler under pressure in T20I 2024?`
- `Compare batter Rinku Singh and David Miller under pressure`
- `Show batter <name> pressure performance in death overs`
- `Most consistent batter under pressure`
- `Most reliable bowler under pressure`
- `Show batter <name> sample size and eligibility`
- `Show batter pressure leaders by season`
- `Compare batter <name> across 2023 and 2024`
- `Compare IPL and T20I batter pressure performance`
- `Best batter under pressure for <team>`
- `Show batting pressure for match <match ID>`

The analyst also supports pressure strike-rate and bowling-economy rankings,
SPI/rank explanations, player profiles, and competition/season/phase filters.
Queries that omit a required role, metric, or comparison subject receive a
clarification rather than an assumed answer. Unsupported nationality or
venue-based selection is not inferred from player names.

Ranked SPI queries use the current minimum of three pressure matches and
twelve role-specific pressure balls. Player-profile and sample-analysis
queries can show below-threshold observations; those rows are marked with
their eligibility state. Evidence displays are capped to 200 match records.

## Optional LLM configuration

No additional Python dependency is required. The provider uses Python's
standard-library HTTP client and an OpenAI-compatible chat-completions API.
Set these variables in the process environment before starting Streamlit:

```text
SUPERR_LLM_API_KEY=<provider key>
SUPERR_LLM_MODEL=<model name>
SUPERR_LLM_BASE_URL=https://api.openai.com/v1
```

`SUPERR_LLM_BASE_URL` is optional and defaults to the OpenAI API base URL.
The key is never rendered or logged. Configure only a provider endpoint you
trust; verified metric rows are sent to the configured endpoint for
interpretation/commentary.

Run the dashboard from the project root:

```bash
streamlit run dashboard/app.py --server.port 8501
```

## Validation

The targeted tests are in `tests/test_cricket_analyst.py` and
`tests/test_dashboard_app.py`. They cover player resolution, ambiguity,
season/format/team/phase filters, batter and bowler calculations, comparisons,
SPI explanations, sample eligibility, source evidence, empty data, unsupported
and SQL-like requests, allowlisted LLM interpretation, and rejection of
numeric LLM commentary.

The feature remains limited by the source-data ambiguities documented in
`reports/methodology_report.md`; the analyst does not resolve or conceal them.
