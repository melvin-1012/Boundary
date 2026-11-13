CREATE KEYSPACE IF NOT EXISTS superr_intelligence
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE superr_intelligence;

CREATE TABLE IF NOT EXISTS player_pressure_rankings_by_competition (
  competition text,
  season text,
  spi double,
  player_id bigint,
  player_name text,
  role text,
  pressure_opportunities int,
  pressure_matches int,
  reliability double,
  evidence_summary text,
  PRIMARY KEY ((competition, season), spi, player_id)
) WITH CLUSTERING ORDER BY (spi DESC, player_id ASC);

CREATE TABLE IF NOT EXISTS deliveries_by_match_innings (
  match_id bigint,
  innings int,
  innings_ball_num int,
  batter_id bigint,
  bowler_id bigint,
  score_before int,
  wickets_before int,
  pressure_score double,
  is_pressure boolean,
  PRIMARY KEY ((match_id, innings), innings_ball_num)
) WITH CLUSTERING ORDER BY (innings_ball_num ASC);

-- Example prepared queries:
-- SELECT * FROM player_pressure_rankings_by_competition
-- WHERE competition = ? AND season = ? LIMIT 10;
-- SELECT * FROM deliveries_by_match_innings
-- WHERE match_id = ? AND innings = ?;
