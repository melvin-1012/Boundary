# AI Cricket Analyst Architecture Audit and Implementation Plan

## Audit scope

This audit records the analyst architecture and available data as inspected
before the dynamic-tool implementation. It focuses on the runtime entry points,
data schemas, calculation ownership, provider boundary, tests, and limitations.
The source archive is read-only.

## Existing architecture

### User interface and request path

`dashboard/app.py` renders the **AI Cricket Analyst** tab and keeps a
conversation list in Streamlit session state. On each submitted prompt it:

1. Loads `data/curated/pressure_deliveries.parquet`.
2. Builds a team lookup from `competition_team_player_mapping.csv`.
3. Optionally builds an `OpenAICompatibleProvider` from environment variables.
4. Calls `analyze_question()`, optionally calls a one-sentence LLM commentary
   method, then displays the application-owned metrics and evidence.

The shown history is not supplied as conversational context to the next
request. There is no tool-call loop, tool status trace, retry button, or
analytical plan in the current flow.

### Question interpretation and calculations

`analytics/cricket_analyst.py` contains a local rule-based intent parser,
player-name resolution, a fixed list of question categories, filter
application, role-specific metric shaping, evidence checks, and optional
provider-based intent classification. The normal calculation path reuses
`analytics.cricket_metrics.calculate_player_metrics()` and `rank_players()`.
The code currently supports selected pressure rankings, player profiles and
comparisons, phases, season/format comparisons, trends, team and match
questions, consistency, reliability, and sample analysis.

The implementation is evidence-conscious: it verifies player and match IDs,
recomputes pressure performance and normal baselines from filtered rows, and
withholds results when these checks fail. However, the local parser has
predefined intents and cannot discover arbitrary table columns or compose new
analysis operations.

### LLM provider and configuration

There is no declared external LLM SDK dependency. The optional
`OpenAICompatibleProvider` uses Python's standard-library HTTP client against
an OpenAI-compatible chat-completions endpoint. Configuration is:

- `SUPERR_LLM_API_KEY` — optional secret, never rendered.
- `SUPERR_LLM_MODEL` — required when a key is set.
- `SUPERR_LLM_BASE_URL` — optional endpoint base URL.

The provider currently classifies a question into an allowlisted JSON shape
and may create qualitative commentary from already-calculated results. It
does not call analytical tools, inspect schemas, construct a multi-step plan,
or execute a general read-only query. No live provider credentials are
configured in the audited workspace.

### Source datasets and data engineering

The six supplied CSV datasets are:

| Dataset | Observed/declared key | Main role |
|---|---|---|
| `ball_by_ball.csv` | `(match_id, innings, innings_ball_num)` | Delivery, player, scoring, extras, dismissal and bowling-style observations |
| `matches.csv` | `match_id` | Competition, teams, date, venue, result and match context |
| `competitions.csv` | `comp_id` | Competition name, format and season |
| `teams.csv` | `(comp_id, team_id)` | Competition-scoped team names |
| `playing_eleven.csv` | Candidate `(match_id, team_id, player_id)`; not unique | Match lineup observations |
| `competition_team_player_mapping.csv` | `(comp_id, team_id, player_id)` | Competition-scoped player and team mapping |

`ingestion/data_validation.py`, `ingestion/data_dictionary.py`, and
`ingestion/dataset_relationships.py` already define source columns, inferred
types, key candidates, observed relationships, and known validation
limitations. The ETL in `ingestion/run_etl.py` writes processed and curated
Parquet data and quality reports. Existing `data/metadata` artifacts capture
the current source dictionary and relationships.

The runtime also has processed Parquet copies and curated batter, bowler,
match, and pressure datasets. The dashboard's pressure archive includes
derived cricket state and metrics such as batter/bowler IDs, competition,
season, phase, pressure flags, legal-ball and batter-ball indicators,
conceded runs, match ID, team IDs, and score/target state.

### Existing calculation modules

- `analytics/cricket_metrics.py` owns delivery-derived batter/bowler metrics,
  pressure comparisons, sample adjustments, SPI and ranking helpers.
- `analytics/build_rankings.py` builds ranking CSVs and provenance outputs.
- `analytics/final_validation.py` independently checks source-to-curated
  calculations, sensitivity and provenance.
- `ingestion/run_etl.py` derives delivery state and pressure from the raw
  archive and emits metadata and validation reports.
- The dashboard applies shared theme and competition/season/team controls.

The analyst should call or wrap these modules; it should not duplicate their
pressure/SPI definitions or silently adjust them.

### Current tests and gaps

`tests/test_cricket_analyst.py` covers parser behavior, selected scope filters,
player comparisons, pressure metrics, SPI fields, evidence checks, unsupported
requests, and mocked provider classification/commentary. Dashboard AppTest
covers tab rendering, theme switching and an actual historical query. These
tests establish the existing fixed-intent behavior, not arbitrary analysis or
tool execution.

Main gaps identified:

1. No runtime registry discovers tables and columns across the data directory.
2. No machine-readable catalog combines actual schemas, row counts, keys,
   relationships, metric definitions, and known limitations.
3. The provider cannot request or sequence analysis tools.
4. There is no safe general-purpose read-only analytical query interface.
5. Prior turns are displayed but are not parsed as context for follow-ups.
6. There is no inspectable tool-call trace, retry path, or unseen-query
   acceptance report.
7. Provider-generated numerical prose needs a stricter boundary: all values
   and cited evidence must remain tool/application outputs.

## Incremental implementation plan

### Phase 1 — Discover and catalog data

- Discover registered CSV and Parquet datasets under `data/` without editing
  them.
- Capture table names, columns, pandas/Arrow types, row counts, null counts,
  candidate keys, relationships, date/competition coverage, and metric
  definitions in a machine-readable catalog.
- Merge known source limitations from the existing quality and relationship
  artifacts rather than silently normalizing anomalies.

### Phase 2 — Expose reusable safe tools

- Add generic discovery, table inspection, dataset summary, player/team/match
  lookup, and query tools.
- Use a read-only in-memory SQL engine over registered dataframes; accept only
  bounded `SELECT` queries, validate identifiers against the catalog, reject
  multiple statements and mutation/attachment commands, and enforce row,
  execution-time, and query-complexity limits.
- Expose existing batter, bowler, pressure, ranking, comparison and match
  calculations by invoking the current analytics helpers.
- Record each tool name, validated arguments, and bounded result summary.

### Phase 3 — Add dynamic multi-step provider orchestration

- Add structured OpenAI-compatible function/tool calling with a finite
  iteration budget.
- Supply tool definitions and concise conversation context, execute tool
  requests only through the allowlisted dispatcher, and send tool results back
  to the model for additional investigation or final qualitative explanation.
- Never pass credentials to the model, accept model-generated executable code,
  or use model-provided values in place of calculated results.
- Keep the local parser path available when no provider is configured; clearly
  distinguish its limited supported intents from dynamic provider analysis.
- Resolve follow-ups against recent validated turns and explicit user changes.

### Phase 4 — Evidence, UX, tests and reports

- Require tool-derived evidence and validated filters for factual results;
  present insufficient evidence and known limitations explicitly.
- Show tool execution status and a concise, user-facing analysis trace in the
  existing tab; preserve current dashboards, themes, filters and animations.
- Test unseen question formulations against real or hand-calculable fixtures,
  tool sequencing, contextual follow-ups, malicious/invalid SQL, timeouts,
  missing data, provider failures, and output verification.
- Record results in `AI_ANALYST_TEST_REPORT.md`; update the implementation
  status and README only to claim behavior actually verified.

## Safety and scope boundaries

- Raw CSVs and generated datasets are query inputs only; analysis code must not
  execute DDL/DML, arbitrary Python, shell commands, or model-supplied code.
- The SQL authorizer, identifier catalog, one-statement check, query timeout
  and result cap form defense in depth; no LLM output is trusted as SQL
  validation.
- The optional LLM receives only the question, bounded catalog/analysis
  context, and tool results necessary for the request. Secrets remain local.
- Player nationality and venue location must not be inferred from names,
  competition labels, or team membership.
- Existing pressure/SPI and rank methodology remains provisional and unchanged.

## Implementation status

The planned tool-based increment is implemented:

- `analytics/analyst_tools.py` discovers CSV/Parquet datasets, produces a
  runtime catalog, exposes schema/summary/entity lookup tools, connects
  role-specific calculations to the existing cricket metric functions, and
  provides bounded read-only SQL over explicitly registered datasets.
- `analytics/cricket_analyst.py` supports OpenAI-compatible structured tool
  calls. The orchestrator executes only allowlisted tools and bounds execution
  to 8 rounds and 12 total calls, with recent conversation context.
- `dashboard/app.py` uses this dynamic path when a compatible provider is
  configured and retains the local rule-based analyzer when no provider is
  configured or a provider failure is recoverable. Tool activity/results are
  shown in the existing tab. The local parser now handles natural-language
  ranking comparisons and displays calculated comparison values directly.
- The `compare_player_rankings` tool applies existing eligibility and SPI
  logic to rank gaps, top-N/ordinal ranks, and eligible-player averages. Its
  default scope includes all available seasons/competitions; a missing role
  returns separate batter and bowler leaderboards.
- `data/metadata/ai_analyst_catalog.json` is the generated catalog snapshot.
- `docs/AI_CRICKET_ANALYST.md` documents both operating modes and safeguards.

The full test suite (**51 tests**) and project compilation passed after this
increment. A live archive smoke test discovered 20 datasets and verified
source counts, player and match lookup, a filtered IPL batter calculation, and
a SELECT aggregate. The new natural-language ranking questions were run
against the actual curated archive; all returned calculations or explicit
eligibility limitations. The reusable ranking operation returned top-two
comparisons for both roles and passed independent source-record checks. Mocked
tests cover tool sequencing, follow-up context, provider request serialization,
query restrictions, filter handling, metric reuse, and withholding
model-generated numerical prose.

**Not verified:** no live model credentials were configured. Therefore the
provider has not been tested against a real endpoint, and the 15 requested
question categories have not each been validated end-to-end with a live model.
The dynamic tool loop can investigate data through its available tools; this
does not guarantee that an LLM will correctly interpret every arbitrary
question. Local parser support remains limited to its documented intents.
Detailed check results are recorded in `docs/AI_ANALYST_TEST_REPORT.md`.
