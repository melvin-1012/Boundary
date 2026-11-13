# Cassandra and HBase design

## Status

**Design and command demonstration only.** No Cassandra or HBase client,
server, or service is available in this environment. The schema files are
reviewable deployment recipes, not evidence that either database is running
or that these commands have been executed.

## Cassandra

[`cassandra_schema.cql`](./cassandra_schema.cql) models two query patterns:

- `player_pressure_rankings_by_competition` partitions by competition and
  season, then clusters by descending SPI and player ID for a bounded ranking
  read. This is query-oriented denormalization; batter and bowler attributes
  are copied into the table to avoid joins.
- `deliveries_by_match_innings` partitions by match and innings and clusters
  deliveries in sequence for a match timeline.

Example deployment and check, once a Cassandra service is provided:

```bash
cqlsh -f databases/cassandra_schema.cql
cqlsh -e "DESCRIBE TABLE superr_intelligence.player_pressure_rankings_by_competition"
```

The sample keyspace uses replication factor one for a local demonstration; it
is not a production availability configuration. The partition keys must be
checked against actual query volume and partition sizes before deployment.

## HBase

[`hbase_demo.hbase`](./hbase_demo.hbase) shows a composite row key ordered by
match, innings, and zero-padded delivery number. `state` and `event` are
separate column families to group state snapshots and event attributes.
Execute with `hbase shell databases/hbase_demo.hbase` only where HBase is
configured. The sample values illustrate commands and are not project
analytics results.

## Distributed data concepts

- **Partition tolerance:** a distributed store must operate despite network
  partitions; a partition can prevent some replicas from communicating.
- **Consistency:** replicas expose a coherent view according to the chosen
  consistency level. Cassandra lets clients trade read/write consistency
  against latency and availability.
- **Availability:** a responding node returns a result, which may be stale
  under some partition/consistency choices.
- **CAP:** during a partition, a distributed system cannot guarantee both
  linearizable consistency and availability for every request. CAP does not
  mean a system permanently chooses only two properties in normal operation.
- **Relational versus NoSQL:** relational systems favor normalized schemas,
  joins, and transaction constraints; wide-column systems favor denormalized
  tables designed around known access paths and predictable partition keys.
- **HBase architecture:** clients locate row-key ranges through region
  metadata; RegionServers serve regions, while HDFS stores durable data and
  write-ahead logs. Row-key design affects region distribution and scan cost.

These are conceptual notes, not claims of measured database behavior. No
CAP/availability benchmark or HDFS-backed HBase operation was executed.
