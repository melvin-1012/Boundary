# AI Cricket Analyst

## Overview and operating modes

The **AI Cricket Analyst** is available as a tab in `dashboard/app.py`. It has
two modes:

- **Local mode:** With no provider configured, the existing rule-based
  question parser calculates supported questions from the curated delivery
  data. It is the dependable fallback, but only handles its implemented
  intents and filters.
- **Dynamic tool mode:** With an OpenAI-compatible provider configured, the
  model can inspect the discovered data catalog, request bounded analyses,
  issue safe read-only analytical queries, and make follow-up tool calls. The
  application executes every tool call and supplies the resulting data back
  to the model. The tool loop is limited to 8 rounds and 12 tool calls.

The provider is optional. No provider credentials are configured in the
development environment, so dynamic behavior has only been verified with
mocked provider responses, not a live model. Do not treat the list of local
question intents as proof of end-to-end live-provider support for every
natural-language formulation.

Ranking questions use sensible defaults instead of stopping for role or scope
choices: "best under pressure" means the existing eligible pressure SPI;
missing season or competition means the full available historical archive;
and an unspecified role means separate batter and bowler results. Rank-gap,
top-N, reliability/consistency ordering, and top-versus-eligible-average
questions use the reusable `compare_player_rankings` operation. It returns
role-specific score gaps, SPI component values, opportunity counts, sample
sizes, reliability, uncertainty indicators, and source-backed evidence.
Cross-role scores are never combined. A gap is descriptive, not a statistical
significance test; the current methodology does not define such a test.
The local answer text now includes calculated top names and IDs, ranking scores,
score and component gaps, sample opportunity counts, reliability, and scope;
the same values remain available in the results table and evidence sections.

## Data discovery and calculations

`analytics/analyst_tools.py` discovers CSV and Parquet datasets under `data/`
and builds a catalog containing schemas, data types, row counts, null counts,
key candidates, relationships, and known metadata. The generated snapshot is
`data/metadata/ai_analyst_catalog.json`; runtime discovery uses dataset file
signatures to refresh cached metadata when inputs change.

The allowlisted tools provide:

- Dataset discovery, selected table inspection, and dataset summaries.
- Player, team, and match lookups over registered records.
- Parameterized, bounded analytical queries over explicitly registered
  datasets.
- Existing role-specific batter and bowler analytics through
  `analytics.cricket_metrics.calculate_player_metrics()` and
  `rank_players()`, with competition, season, phase, team/opponent, player,
  bowling-type, format, and pressure filters where the available fields allow.

Metric tools reuse the project's pressure and SPI methodology; they do not
redefine it. Pressure weights, SPI choices, and eligibility remain provisional.
Reported pressure rates and normal baselines are independently recomputed
from the filtered delivery records. Results include evidence and limitations
when available. Missing or unsupported fields are reported rather than
invented.

## Query safety and answer boundaries

The general query tool accepts only a single `SELECT` or `WITH ... SELECT`.
Queries are restricted to tables explicitly registered for that request,
catalogued columns, an allowlist of SQL functions, up to 8 tables, 100 bound
parameters, an 8,000-character query, a 3-second SQLite execution budget, and
500 returned rows. SQLite's authorizer denies writes, schema changes, access
to unregistered tables/columns, and unapproved functions. SQL comments and
multiple statements are rejected. Tool dispatch itself is allowlisted; the
model cannot execute Python, shell commands, or arbitrary SQL outside these
checks.

The model is not the source of calculated statistics. Tool results and
application-computed metrics are rendered separately, and model-generated
numerical summary claims are withheld. The provider may interpret results in
qualitative prose, but that prose is not a substitute for the displayed
metrics or evidence.

Raw input records are read-only. Secrets are sent only as HTTP authorization
headers to the configured provider and are not included in prompts, tool
arguments, or dashboard output. Configure only an endpoint trusted to receive
the question and the bounded context/results required for analysis.

## Local question support

The no-provider parser has implemented paths for:

- Pressure rankings, pressure strike rate, and bowling economy.
- Batter or bowler player profiles and player comparisons.
- Season and competition/format comparisons, season trends, and mapped team
  analysis.
- Powerplay, middle-over, and death-over analysis.
- Consistency, reliability, rank/SPI explanations, and sample eligibility.
- Match-level pressure analysis when a match ID is explicit.

Use explicit role and scope where possible. Examples:

```text
Who is the best batter under pressure in IPL 2023?
Who is the best bowler under pressure in T20I 2024?
Compare batter Rinku Singh and David Miller under pressure
Show batter <name> pressure performance in death overs
Most reliable bowler under pressure in T20I 2024
Compare batter <name> across 2023 and 2024
Compare IPL and T20I batter pressure performance
Show batting pressure for match <match ID>
```

Only unresolved player identities or a metric that cannot reasonably be
inferred should require clarification. The local parser does not infer
nationality or venue-country from a player's name, competition, or team
membership. Evidence is capped to 200 match records in the local results.

Examples of natural-language ranking questions handled by the local parser:

```text
How much is the difference between first and second best player under pressure?
Who is the second most reliable bowler?
Compare the top three pressure performers
How much better is the top batter than the average batter?
Who ranks first overall in pressure performance?
Is the gap between first and second significant?
Why is the top-ranked player better?
```

The local parser calculates these using the same existing SPI eligibility and
formula. If a scope has too few eligible players—for example, a short
format-specific subset—it reports that limitation instead of substituting an
ineligible player. Dynamic language understanding still depends on the
configured model and has not been live-provider tested here.

## Configuration and launch

No additional Python package is required. The provider uses Python's
standard-library HTTP client and an OpenAI-compatible chat-completions API.
Set these variables before starting Streamlit:

```bash
export SUPERR_LLM_API_KEY="your-provider-key"
export SUPERR_LLM_MODEL="your-model-name"
# Optional; defaults to https://api.openai.com/v1
export SUPERR_LLM_BASE_URL="https://api.openai.com/v1"
.venv/bin/streamlit run dashboard/app.py --server.port 8501
```

Without a key, the dashboard clearly indicates that dynamic tool calling is
not enabled and keeps the local parser available. A configured key without a
model is a configuration error. Provider/network errors are surfaced and the
dashboard falls back to local analysis where possible.

## Validation and known limits

`tests/test_analyst_tools.py` covers data discovery, schema inspection, entity
and match lookup, query restrictions, role metrics, rank comparisons, tool
dispatch, multi-step calls, recent-turn context, and model numerical-claim
withholding. Provider request serialization is tested with a mocked HTTP
response. `tests/test_cricket_analyst.py` covers the natural-language rank
forms and defaults against hand-calculable fixtures; `tests/test_dashboard_app.py`
covers dashboard integration. The full project suite currently passes 51
tests.

These automated and local checks do not establish live provider quality,
live tool-call interoperability, or successful coverage of every requested
question category. No live LLM credentials were available during development.
Source-data ambiguities, including extras and boundary semantics, remain
documented in `reports/methodology_report.md`; the analyst does not resolve
them silently.
