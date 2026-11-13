"""Run local PySpark RDD, DataFrame, SQL, and pandas parity demonstrations."""

import json
import os
import platform
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
PANDAS_ORACLE = ROOT / "data" / "curated" / "pressure_deliveries.parquet"
PRESSURE_OUTPUT = ROOT / "data" / "curated" / "spark_pressure_deliveries.parquet"
OUTPUT = ROOT / "data" / "curated" / "spark_batter_aggregation.parquet"
REPORT = ROOT / "reports" / "spark" / "benchmark.json"


def _build_pressure_deliveries(spark, processed_dir):
    from pyspark.sql import Window, functions as F

    processed_dir = Path(processed_dir)
    matches = spark.read.parquet(str(processed_dir / "matches.parquet"))
    competitions = spark.read.parquet(str(processed_dir / "competitions.parquet"))
    balls = spark.read.parquet(str(processed_dir / "ball_by_ball.parquet"))

    required = {
        "matches": {"match_id", "comp_id", "match_date", "first_inn_revised_overs",
                    "second_inn_revised_overs", "revised_target"},
        "competitions": {"comp_id", "comp_name", "match_format", "season"},
        "deliveries": {"match_id", "innings", "innings_ball_num", "runs",
                       "extras1_runs", "extras_2_runs", "extras_type", "is_wicket",
                       "dismissal_type", "dismissed_player_id", "striker_id",
                       "striker_name", "bowler_id", "bowler_name", "is_four", "is_six"},
    }
    for label, frame, expected in [
        ("matches", matches, required["matches"]),
        ("competitions", competitions, required["competitions"]),
        ("deliveries", balls, required["deliveries"]),
    ]:
        missing = sorted(expected - set(frame.columns))
        if missing:
            raise ValueError(f"Spark {label} input is missing required columns: {missing}")
    for label, frame, key in [
        ("matches", matches, "match_id"),
        ("competitions", competitions, "comp_id"),
    ]:
        if frame.select(key).distinct().count() != frame.count():
            raise ValueError(f"Spark {label} input has duplicate {key} values.")
    delivery_key = ["match_id", "innings", "innings_ball_num"]
    source_delivery_count = balls.count()
    distinct_delivery_keys = balls.select(*delivery_key).distinct().count()
    null_delivery_ids = balls.filter(
        F.col("match_id").isNull()
        | F.col("innings").isNull()
        | F.col("innings_ball_num").isNull()
    ).count()
    if source_delivery_count != distinct_delivery_keys or null_delivery_ids:
        raise ValueError(
            "Spark delivery-key validation failed: "
            f"{source_delivery_count} rows, {distinct_delivery_keys} distinct keys, "
            f"{null_delivery_ids} rows with missing identifiers."
        )

    metadata = matches.join(competitions, on="comp_id", how="inner").withColumn(
        "_match_date", F.to_date("match_date")
    )
    ipl_ids = {
        1358: "IPL 2022",
        1715: "IPL 2023",
        2193: "IPL 2024",
        2725: "IPL 2025",
        3298: "IPL 2026",
    }
    ipl_scope = F.lit(False)
    for competition_id, name in ipl_ids.items():
        ipl_scope = ipl_scope | (
            (F.col("comp_id") == competition_id) & (F.col("comp_name") == name)
        )
    metadata = metadata.filter(
        (F.col("_match_date") >= F.lit("2022-01-01"))
        & (
            (F.col("match_format") == "T20I")
            | (ipl_scope & (F.col("match_format") == "T20"))
        )
    )
    match_metadata = metadata.select(
        "match_id",
        "comp_id",
        "match_date",
        "first_inn_revised_overs",
        "second_inn_revised_overs",
        "revised_target",
        "comp_name",
        "match_format",
        "season",
        *[column for column in ("result", "win_team_id") if column in metadata.columns],
    )
    delivery = balls.join(match_metadata, on="match_id", how="inner")
    extras = F.lower(F.coalesce(F.col("extras_type"), F.lit("")))
    delivery = (
        delivery.withColumn(
            "team_runs",
            F.coalesce(F.col("runs"), F.lit(0))
            + F.coalesce(F.col("extras1_runs"), F.lit(0))
            + F.coalesce(F.col("extras_2_runs"), F.lit(0)),
        )
        .withColumn("batter_runs", F.coalesce(F.col("runs"), F.lit(0)))
        .withColumn("is_legal_ball", ~extras.isin("wide", "overstep"))
        .withColumn("is_batter_ball_faced", ~extras.isin("wide"))
        .withColumn(
            "bowler_conceded_runs",
            F.col("team_runs")
            - F.when(
                extras.isin("byes", "legbyes", "penalty"),
                F.coalesce(F.col("extras1_runs"), F.lit(0))
                + F.coalesce(F.col("extras_2_runs"), F.lit(0)),
            ).otherwise(0),
        )
        .withColumn(
            "is_bowler_wicket",
            F.coalesce(F.col("is_wicket"), F.lit(False))
            & F.col("dismissal_type").isin(
                "Bowled", "Caught", "LBW", "Stump", "Hit Wicket"
            ),
        )
        .withColumn("is_dot_ball", F.col("team_runs") == 0)
        .withColumn(
            "has_boundary_flag",
            F.coalesce(F.col("is_four"), F.lit(False))
            | F.coalesce(F.col("is_six"), F.lit(False)),
        )
    )
    order_window = Window.partitionBy("match_id", "innings").orderBy(
        "innings_ball_num"
    )
    prior_window = order_window.rowsBetween(Window.unboundedPreceding, -1)
    delivery = (
        delivery.withColumn(
            "score_before",
            F.coalesce(F.sum("team_runs").over(prior_window), F.lit(0)),
        )
        .withColumn(
            "wickets_before",
            F.coalesce(
                F.sum(F.col("is_wicket").cast("long")).over(prior_window),
                F.lit(0),
            ),
        )
        .withColumn(
            "legal_balls_before",
            F.coalesce(
                F.sum(F.col("is_legal_ball").cast("long")).over(prior_window),
                F.lit(0),
            ),
        )
    )
    innings_totals = delivery.groupBy("match_id", "innings").agg(
        F.sum("team_runs").alias("innings_runs"),
        F.sum(F.col("is_legal_ball").cast("long")).alias("innings_legal_balls"),
    )
    target_source = innings_totals.filter(F.col("innings").isin(1, 3)).select(
        "match_id",
        (F.col("innings") + 1).alias("innings"),
        F.col("innings_runs").alias("preceding_innings_runs"),
    )
    delivery = delivery.join(target_source, ["match_id", "innings"], "left")
    target = F.col("preceding_innings_runs") + 1
    target = F.when(
        (F.col("innings") == 2) & F.col("revised_target").isNotNull(),
        F.col("revised_target"),
    ).otherwise(target)
    delivery = delivery.withColumn(
        "target",
        F.when(F.col("innings").isin(2, 4), target),
    )
    delivery = delivery.withColumn(
        "innings_overs",
        F.when(F.col("innings") == 1, F.col("first_inn_revised_overs"))
        .when(F.col("innings") == 2, F.col("second_inn_revised_overs"))
        .when(F.col("innings").isin(3, 4), F.lit(1.0))
        .otherwise(F.lit(20.0)),
    )
    delivery = delivery.withColumn(
        "innings_overs",
        F.when(
            F.col("innings_overs").isNull() | (F.col("innings_overs") <= 0),
            F.lit(20.0),
        ).otherwise(F.col("innings_overs")),
    ).withColumn(
        "innings_balls", F.round(F.greatest(F.col("innings_overs"), F.lit(1.0)) * 6)
    )
    delivery = (
        delivery.withColumn(
            "balls_remaining",
            F.greatest(F.col("innings_balls") - F.col("legal_balls_before"), F.lit(0)),
        )
        .withColumn(
            "wickets_remaining",
            F.greatest(F.lit(10) - F.col("wickets_before"), F.lit(0)),
        )
        .withColumn(
            "innings_progress",
            F.least(
                F.col("legal_balls_before") / F.col("innings_balls"),
                F.lit(1.0),
            ),
        )
        .withColumn(
            "current_run_rate",
            F.when(
                F.col("legal_balls_before") > 0,
                6 * F.col("score_before") / F.col("legal_balls_before"),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "runs_required",
            F.when(
                F.col("innings").isin(2, 4),
                F.col("target") - F.col("score_before"),
            ),
        )
        .withColumn(
            "required_run_rate",
            F.when(
                F.col("innings").isin(2, 4) & (F.col("balls_remaining") > 0),
                6 * F.greatest(F.col("runs_required"), F.lit(0))
                / F.col("balls_remaining"),
            ),
        )
        .withColumn(
            "innings_phase",
            F.when(F.col("innings_progress") <= 1 / 3, "powerplay")
            .when(F.col("innings_progress") <= 0.75, "middle")
            .otherwise("death"),
        )
    )
    first_innings = (
        innings_totals.filter(
            (F.col("innings") == 1) & (F.col("innings_legal_balls") > 0)
        )
        .join(
            match_metadata.select("match_id", "match_date", "match_format"),
            on="match_id",
        )
        .withColumn(
            "innings_run_rate",
            6 * F.col("innings_runs") / F.col("innings_legal_balls"),
        )
        .withColumn("_match_date", F.to_date("match_date"))
    )
    prior_matches = (
        Window.partitionBy("match_format")
        .orderBy("_match_date", "match_id")
        .rowsBetween(Window.unboundedPreceding, -1)
    )
    first_innings = (
        first_innings.withColumn(
            "_prior_count", F.count("innings_run_rate").over(prior_matches)
        )
        .withColumn(
            "_prior_median",
            F.percentile("innings_run_rate", 0.5).over(prior_matches),
        )
        .withColumn(
            "reference_run_rate",
            F.when(
                F.col("_prior_count") >= 5, F.col("_prior_median")
            ).otherwise(
                F.when(F.col("match_format") == "T20I", 7.5).otherwise(8.0)
            ),
        )
        .select("match_id", "reference_run_rate")
    )
    delivery = delivery.join(first_innings, on="match_id", how="left")
    delivery = delivery.withColumn(
        "reference_run_rate",
        F.greatest(
            F.coalesce(
                F.col("reference_run_rate"),
                F.when(F.col("match_format") == "T20I", 7.5).otherwise(8.0),
            ),
            F.lit(1.0),
        ),
    )
    chase = F.col("innings").isin(2, 4) & F.col("target").isNotNull()
    first = F.col("innings").isin(1, 3)
    normalized_required = (
        F.coalesce(F.col("required_run_rate"), F.lit(0.0))
        / F.col("reference_run_rate")
    )
    progress = F.col("innings_progress")
    wickets_lost = F.least(F.col("wickets_before") / 10.0, F.lit(1.0))
    wickets_available = F.least(F.col("wickets_remaining") / 10.0, F.lit(1.0))
    components = {
        "batting_run_rate_component": F.when(
            chase,
            F.least(F.greatest((normalized_required - 1) / 1.5, F.lit(0)), F.lit(1)),
        ).otherwise(
            F.least(
                F.greatest(
                    (F.col("reference_run_rate") - F.col("current_run_rate"))
                    / F.col("reference_run_rate"),
                    F.lit(0),
                ),
                F.lit(1),
            ) * progress
        ),
        "batting_wickets_component": wickets_lost,
        "batting_time_component": progress,
        "batting_closeness_component": F.when(
            chase,
            F.exp(-F.abs(normalized_required - 1)),
        ).otherwise(
            F.exp(
                -F.abs(F.col("current_run_rate") - F.col("reference_run_rate"))
                / F.col("reference_run_rate")
            )
            * progress
        ),
        "bowling_run_rate_component": F.when(
            chase,
            F.least(
                F.greatest((1 - normalized_required) / 1.5, F.lit(0)), F.lit(1)
            ),
        ).otherwise(
            F.least(
                F.greatest(
                    (F.col("current_run_rate") - F.col("reference_run_rate"))
                    / F.col("reference_run_rate"),
                    F.lit(0),
                ),
                F.lit(1),
            ) * progress
        ),
        "bowling_wickets_component": F.when(
            chase,
            wickets_available,
        ).otherwise(F.least((10 - F.col("wickets_before")) / 10.0, F.lit(1.0))),
        "bowling_time_component": progress,
        "bowling_closeness_component": F.when(
            chase,
            F.exp(-F.abs(normalized_required - 1)),
        ).otherwise(
            F.exp(
                -F.abs(F.col("current_run_rate") - F.col("reference_run_rate"))
                / F.col("reference_run_rate")
            )
            * progress
        ),
    }
    for name, value in components.items():
        delivery = delivery.withColumn(name, value)
    batting_score = (
        F.col("batting_run_rate_component") * 0.35
        + F.col("batting_wickets_component") * 0.25
        + F.col("batting_time_component") * 0.20
        + F.col("batting_closeness_component") * 0.20
    ) * 100
    bowling_score = (
        F.col("bowling_run_rate_component") * 0.30
        + F.col("bowling_wickets_component") * 0.25
        + F.col("bowling_time_component") * 0.20
        + F.col("bowling_closeness_component") * 0.25
    ) * 100
    supported = first | chase
    delivery = (
        delivery.withColumn(
            "batting_pressure",
            F.when(supported, F.least(F.greatest(batting_score, F.lit(0)), F.lit(100))),
        )
        .withColumn(
            "bowling_pressure",
            F.when(supported, F.least(F.greatest(bowling_score, F.lit(0)), F.lit(100))),
        )
        .withColumn(
            "is_batting_pressure", F.coalesce(F.col("batting_pressure") >= 50, F.lit(False))
        )
        .withColumn(
            "is_bowling_pressure", F.coalesce(F.col("bowling_pressure") >= 50, F.lit(False))
        )
        .withColumn(
            "pressure_batter_ball",
            F.col("is_batting_pressure") & F.col("is_batter_ball_faced"),
        )
        .withColumn(
            "pressure_bowler_ball",
            F.col("is_bowling_pressure") & F.col("is_legal_ball"),
        )
    )
    checks = {
        "matches_key_unique": True,
        "competitions_key_unique": True,
        "delivery_sequence_key_unique": True,
        "delivery_sequence_key_null_rows": int(null_delivery_ids),
        "source_delivery_rows": int(source_delivery_count),
    }
    return delivery, checks


def _grouped_state(frame):
    from pyspark.sql import functions as F

    return (
        frame.groupBy("match_id", "innings")
        .agg(
            F.sum("team_runs").alias("team_runs"),
            F.sum(F.col("is_legal_ball").cast("long")).alias("legal_balls"),
            F.sum("score_before").alias("score_before"),
            F.sum("wickets_before").alias("wickets_before"),
            F.sum("batting_pressure").alias("batting_pressure"),
            F.sum("bowling_pressure").alias("bowling_pressure"),
            F.sum(F.col("is_batting_pressure").cast("long")).alias("batting_pressure_balls"),
            F.sum(F.col("is_bowling_pressure").cast("long")).alias("bowling_pressure_balls"),
        )
        .collect()
    )


def run_spark(processed_dir=PROCESSED, oracle_path=PANDAS_ORACLE,
              pressure_output=PRESSURE_OUTPUT, output_path=OUTPUT, report_path=REPORT):
    from pyspark.sql import SparkSession, functions as F

    builder = (
        SparkSession.builder.appName("SupeRR-Cricket-Analytics")
        .master("local[2]")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
    )
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        started = time.perf_counter()
        deliveries, spark_input_checks = _build_pressure_deliveries(spark, processed_dir)
        deliveries.cache()
        input_rows = deliveries.count()
        cache_seconds = time.perf_counter() - started

        oracle = spark.read.parquet(str(oracle_path)).cache()
        oracle_rows = oracle.count()
        spark_state = {
            (int(row["match_id"]), int(row["innings"])): row.asDict()
            for row in _grouped_state(deliveries)
        }
        oracle_state = {
            (int(row["match_id"]), int(row["innings"])): row.asDict()
            for row in _grouped_state(oracle)
        }
        state_fields = [
            "team_runs",
            "legal_balls",
            "score_before",
            "wickets_before",
            "batting_pressure",
            "bowling_pressure",
            "batting_pressure_balls",
            "bowling_pressure_balls",
        ]
        state_differences = []
        for key in sorted(set(spark_state) | set(oracle_state)):
            for field in state_fields:
                actual = spark_state.get(key, {}).get(field)
                expected = oracle_state.get(key, {}).get(field)
                if actual is None or expected is None or abs(float(actual) - float(expected)) > 1e-6:
                    state_differences.append(
                        {
                            "match_id": key[0],
                            "innings": key[1],
                            "field": field,
                            "spark": actual,
                            "pandas": expected,
                        }
                    )

        pressure_output = Path(pressure_output)
        deliveries.write.mode("overwrite").parquet(str(pressure_output))
        dataframe_started = time.perf_counter()
        batter_totals = (
            deliveries.groupBy("striker_id")
            .agg(
                F.sum("batter_runs").alias("batter_runs"),
                F.sum(F.col("is_batter_ball_faced").cast("long")).alias("balls_faced"),
                F.sum(F.col("is_four").cast("long")).alias("fours"),
                F.sum(F.col("is_six").cast("long")).alias("sixes"),
                F.sum(
                    F.when(F.col("is_batting_pressure"), F.col("batter_runs"))
                    .otherwise(0)
                ).alias("pressure_runs"),
                F.sum(F.col("pressure_batter_ball").cast("long")).alias("pressure_balls"),
            )
            .orderBy("striker_id")
        )
        dataframe_rows = batter_totals.collect()
        dataframe_seconds = time.perf_counter() - dataframe_started
        output_path = Path(output_path)
        batter_totals.write.mode("overwrite").parquet(str(output_path))

        sql_started = time.perf_counter()
        deliveries.createOrReplaceTempView("pressure_deliveries")
        sql_result = spark.sql(
            """
            SELECT striker_id, SUM(batter_runs) AS batter_runs
            FROM pressure_deliveries
            GROUP BY striker_id
            ORDER BY striker_id
            """
        )
        sql_data = sql_result.collect()
        sql_rows = len(sql_data)
        sql_seconds = time.perf_counter() - sql_started

        rdd_started = time.perf_counter()
        rdd_totals = (
            deliveries.select("striker_id", "batter_runs")
            .rdd.map(lambda row: (row.striker_id, row.batter_runs or 0))
            .filter(lambda pair: pair[0] is not None and pair[0] > 0)
            .map(lambda pair: (int(pair[0]), int(pair[1])))
            .flatMap(lambda pair: [pair])
            .reduceByKey(lambda left, right: left + right)
            .collectAsMap()
        )
        rdd_seconds = time.perf_counter() - rdd_started

        pandas_started = time.perf_counter()
        pandas_frame = pd.read_parquet(
            oracle_path,
            columns=[
                "striker_id",
                "batter_runs",
                "is_batter_ball_faced",
                "is_four",
                "is_six",
                "is_batting_pressure",
                "pressure_batter_ball",
            ],
        )
        pandas_frame["pressure_runs"] = pandas_frame["batter_runs"].where(
            pandas_frame["is_batting_pressure"], 0
        )
        pandas_totals = (
            pandas_frame.groupby("striker_id", dropna=True)
            .agg(
                batter_runs=("batter_runs", "sum"),
                balls_faced=("is_batter_ball_faced", "sum"),
                fours=("is_four", "sum"),
                sixes=("is_six", "sum"),
                pressure_runs=("pressure_runs", "sum"),
                pressure_balls=("pressure_batter_ball", "sum"),
            )
            .sort_index()
        )
        pandas_seconds = time.perf_counter() - pandas_started

        spark_totals = {
            int(row["striker_id"]): {
                key: int(row[key])
                for key in [
                    "batter_runs",
                    "balls_faced",
                    "fours",
                    "sixes",
                    "pressure_runs",
                    "pressure_balls",
                ]
            }
            for row in dataframe_rows
            if row["striker_id"] is not None
        }
        pandas_expected = {
            int(player_id): {key: int(value) for key, value in row.items()}
            for player_id, row in pandas_totals.iterrows()
        }
        differences = []
        for player_id in sorted(set(spark_totals) | set(pandas_expected)):
            if spark_totals.get(player_id) != pandas_expected.get(player_id):
                differences.append(
                    {
                        "player_id": player_id,
                        "spark": spark_totals.get(player_id),
                        "pandas": pandas_expected.get(player_id),
                    }
                )
        rdd_differences = [
            {
                "player_id": player_id,
                "spark_rdd": rdd_totals.get(player_id),
                "spark_dataframe": expected["batter_runs"],
            }
            for player_id, expected in spark_totals.items()
            if rdd_totals.get(player_id) != expected["batter_runs"]
        ]
        sql_totals = {
            int(row["striker_id"]): int(row["batter_runs"] or 0)
            for row in sql_data
            if row["striker_id"] is not None
        }
        sql_differences = [
            {
                "player_id": player_id,
                "spark_sql": sql_totals.get(player_id),
                "pandas": expected["batter_runs"],
            }
            for player_id, expected in pandas_expected.items()
            if sql_totals.get(player_id) != expected["batter_runs"]
        ]
        report = {
            "execution_mode": "single-machine Spark local[2]; not a multi-node cluster",
            "spark_version": spark.version,
            "python_version": platform.python_version(),
            "java_home_configured": bool(os.environ.get("JAVA_HOME")),
            "inputs": {
                "processed_parquet_directory": str(Path(processed_dir).relative_to(ROOT)),
                "pandas_pressure_oracle": str(Path(oracle_path).relative_to(ROOT)),
            },
            "input_rows": int(input_rows),
            "pandas_oracle_rows": int(oracle_rows),
            "source_pipeline": {
                "schema_and_key_checks": True,
                "input_checks": spark_input_checks,
                "competition_scope_filter": "2022 onward; exact IPL 2022-2026 metadata and T20I",
                "source_joins": ["matches to competitions", "deliveries to selected matches"],
                "match_state_and_pressure_features_derived_in_spark": True,
                "output": str(pressure_output.relative_to(ROOT)),
                "pandas_state_parity": not state_differences,
                "state_differences": state_differences[:50],
            },
            "rdd": {
                "transformations": [
                    "select",
                    "map",
                    "filter",
                    "flatMap",
                    "reduceByKey",
                ],
                "players": len(rdd_totals),
                "seconds": rdd_seconds,
                "pandas_sum_parity": not rdd_differences,
                "differences": rdd_differences[:20],
            },
            "dataframe": {
                "players": len(spark_totals),
                "seconds": dataframe_seconds,
                "pandas_parity": not differences,
                "differences": differences[:20],
                "output": str(Path(output_path).relative_to(ROOT)),
                "execution_plan": batter_totals._jdf.queryExecution().simpleString(),
            },
            "spark_sql": {
                "players": int(sql_rows),
                "seconds": sql_seconds,
                "pandas_sum_parity": not sql_differences,
                "differences": sql_differences[:20],
            },
            "pandas": {
                "players": len(pandas_expected),
                "seconds": pandas_seconds,
            },
            "cache_count_seconds": cache_seconds,
            "caveats": [
                "Local Spark startup and shuffle overhead can exceed pandas cost for this approximately 194k-row dataset.",
                "The Spark calculations validate aggregation mechanics, not the provisional cricket-statistics assumptions.",
            ],
        }
        report["parity"] = (
            report["source_pipeline"]["pandas_state_parity"]
            and input_rows == oracle_rows
            and report["dataframe"]["pandas_parity"]
            and report["rdd"]["pandas_sum_parity"]
            and report["spark_sql"]["pandas_sum_parity"]
        )
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not report["parity"]:
            raise AssertionError(f"PySpark/Pandas parity failed: {report}")
        print(
            f"Spark local aggregation parity passed for {input_rows} deliveries "
            f"and {len(spark_totals)} batters."
        )
        return report
    finally:
        spark.stop()


if __name__ == "__main__":
    run_spark()
