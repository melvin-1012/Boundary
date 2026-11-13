# Cricket Analyst Test Report

## Result summary

- Full project suite: **51 tests passed** with
  `.venv/bin/python -m unittest discover -s tests -v`.
- Python compilation: **passed** with the project-wide `py_compile` command
  recorded in the README.
- Live model endpoint: **not tested**; no provider credentials were available.
- Live browser/provider interaction: **not verified** in this implementation
  increment. Existing Streamlit AppTest and prior local-browser checks validate
  the dashboard UI and local analytics path, not external LLM behavior.

## Verified behavior

The test suite and archive smoke check cover:

- Dataset discovery and schema metadata for the available CSV/Parquet archive.
- Player, team, and match lookup; match filters; date and venue filtering.
- Existing batter/bowler metric reuse with pressure evidence verification.
- Season, phase, pressure-only, player, and bowling-type metric filters;
  sample-size limitations and sorting.
- Single SELECT query execution with bound parameters and registered tables.
- Rejection of mutation or multiple-statement SQL, unknown tables/columns, and
  unapproved functions.
- Structured provider tool-call parsing, mocked multi-step tool execution,
  recent-turn context, bounded result handling, and withholding model-written
  numerical summaries.
- Provider HTTP request serialization without placing the API key in the
  request body.
- Dashboard AppTest rendering, theme switch, and local analyst integration.
- Natural-language regression cases for rank gaps, top-N, second-most-reliable,
  top-versus-average, no-role defaults, qualitative "why" questions, and
  unsupported formal significance claims. These use calculated results and
  retain source evidence.
- The default no-role comparison returns distinct batter and bowler
  leaderboard results; the tool reports separate eligible counts and does
  not combine the role score scales.
- Format-specific IPL/T20I leader comparisons use the existing eligibility
  rules; a scope with no eligible player is reported as insufficient rather
  than filled with an ineligible fallback.

The local archive smoke check discovered **20 CSV/Parquet datasets**; checked
the six supplied source counts (200,999 deliveries, 883 matches, 141
competitions, 353 teams, 28,381 playing-eleven rows, and 6,413
competition/team/player mappings); resolved a player and match; and executed a
filtered IPL 2023 batter analysis with independent pressure-rate and baseline
checks. A bounded aggregate query over deliveries returned 200,999 source
rows as its aggregate input. The tool result size was checked against the
32,000-character cap.

All eight requested natural-language examples plus the IPL-versus-T20I
difference question were run through the local parser against the actual
curated archive. Each produced calculated results or an explicit eligibility
limitation, with no clarification status. The reusable ranking comparison
tool was also run on the full archive: both roles returned eligible top-two
results and passed independent source-record rate/baseline verification.

## Scope and limitations

The local parser has explicit calculation paths for pressure leaderboards,
season and format comparisons, player comparisons/profiles, phase-scoped
performance, consistency, reliability, rank/SPI explanations, sample
eligibility, mapped team analysis, and match-ID pressure analysis. The
provider-backed path can discover and query registered datasets and request
existing batter/bowler calculations through tools. Tool orchestration tests
use a mock provider.

The following are **not established by these checks**:

- Correct behavior or response quality from a live LLM provider.
- Live interoperability with a specific OpenAI-compatible provider/model.
- End-to-end live-model tests for all natural-language categories in the
  earlier feature request.
- Arbitrary question understanding, player nationality, or venue-country
  inference.
- Resolution of documented source-data ambiguities or approval of provisional
  pressure/SPI methodology.

See `docs/AI_CRICKET_ANALYST.md` for setup, local-mode behavior, tool limits,
and security details.
