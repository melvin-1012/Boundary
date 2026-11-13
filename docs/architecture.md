# Architecture and analytical flows

## Project architecture

```mermaid
flowchart LR
    raw["data/raw<br/>six source CSVs<br/>read-only"]
    validate["ingestion validation<br/>schema · keys · relationships"]
    etl["ingestion ETL<br/>scope · state · pressure"]
    processed["data/processed<br/>source-aligned Parquet"]
    curated["data/curated<br/>pressure events · player metrics"]
    spi["analytics<br/>SPI · sensitivity · rankings"]
    bigdata["hadoop / spark<br/>local MapReduce · local[2]"]
    demos["ML · replay · graph<br/>exploratory demonstrations"]
    reports["reports<br/>rankings · QA · evidence"]
    dashboard["Streamlit dashboard<br/>7 integrated views"]
    raw --> validate --> etl
    etl --> processed
    etl --> curated
    curated --> spi --> reports
    processed --> bigdata --> reports
    curated --> demos --> reports
    curated --> dashboard
    reports --> dashboard
```

## Data pipeline

```mermaid
flowchart TD
    A["Raw match, competition, team,<br/>roster and delivery CSVs"] --> B["Profile schema, nulls,<br/>duplicates and keys"]
    B --> C["Select exact IPL metadata and<br/>post-2022 T20I scope"]
    C --> D["Write source-aligned Parquet<br/>without editing raw inputs"]
    D --> E["Join match and competition context"]
    E --> F["Reconstruct pre-delivery<br/>score, wickets and legal balls"]
    F --> G["Derive targets, required rate,<br/>phase and pressure components"]
    G --> H["Aggregate batter/bowler<br/>match and player metrics"]
    H --> I["Calculate provisional SPI,<br/>reliability and sensitivity"]
    I --> J["Export top-ten + full rankings,<br/>quality report and methodology"]
    J --> K["Dashboard and submission outputs"]
```

## Pressure classification

```mermaid
flowchart TD
    A["Ordered delivery event"] --> B["Read state before delivery"]
    B --> C{"Supported innings<br/>with valid chase target?"}
    C -->|No| D["Pressure score unavailable;<br/>not classified"]
    C -->|Yes| E["Compute batting and bowling<br/>run-rate, wickets, time, closeness"]
    E --> F["Apply separate weighted<br/>0–100 heuristic scores"]
    F --> G{"Score >= provisional 50?"}
    G -->|Yes| H["Label pressure opportunity"]
    G -->|No| I["Retain state and score;<br/>label non-pressure"]
    H --> J["Aggregate player metrics,<br/>reliability and consistency"]
    I --> J
    J --> K["Provisional SPI and<br/>ranked evidence exports"]
```

## Runtime boundaries

- `reports/streaming/replay_validation.json` is a deterministic historical
  event replay; there is no Kafka broker or connector.
- `databases/` contains Cassandra/HBase query-oriented design and sample
  commands; there is no live NoSQL deployment.
- The graph links only players and matches observed in delivery rows. PageRank
  is a supplementary participation signal and does not enter SPI.
- ML outputs predict delivery boundaries or cluster observed player metrics;
  neither is used in official/provisional ranking calculations.
