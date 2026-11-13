"""Replay historical, batch-enriched deliveries as ordered event envelopes."""

import json
from pathlib import Path

import pandas as pd

from analytics.cricket_metrics import PRESSURE_THRESHOLD, PRESSURE_WEIGHTS


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated" / "pressure_deliveries.parquet"
OUTPUT = ROOT / "reports" / "streaming" / "replay_validation.json"
EVENT_COLUMNS = [
    "match_id",
    "innings",
    "innings_ball_num",
    "overid",
    "over_ball_num",
    "runs",
    "extras1_runs",
    "extras_2_runs",
    "extras_type",
    "is_legal_ball",
    "is_wicket",
    "score_before",
    "wickets_before",
    "legal_balls_before",
    "target",
    "innings",
    "batting_pressure",
    "bowling_pressure",
    "is_batting_pressure",
    "is_bowling_pressure",
    *[
        f"{role}_{component}_component"
        for role, components in PRESSURE_WEIGHTS.items()
        for component in components
    ],
]
NON_LEGAL_EXTRAS = {"wide", "Overstep"}
TOPIC = "cricket-deliveries"


class HistoricalDeliveryProducer:
    """Produce ordered, locally simulated topic messages from archive rows."""

    def produce(self, frame):
        for row in frame.itertuples(index=False, name=None):
            event = dict(zip(frame.columns, row))
            yield {
                "topic": TOPIC,
                "key": f"{int(event['match_id'])}:{int(event['innings'])}",
                "sequence": int(event["innings_ball_num"]),
                "payload": event,
            }


class ReplayConsumer:
    """Consume messages sequentially and pass payloads to the state engine."""

    def consume(self, messages):
        for message in messages:
            if message["topic"] != TOPIC:
                raise ValueError(f"Unexpected replay topic: {message['topic']}")
            event = message["payload"]
            if message["key"] != f"{int(event['match_id'])}:{int(event['innings'])}":
                raise ValueError("Replay message key does not match its event partition.")
            if message["sequence"] != int(event["innings_ball_num"]):
                raise ValueError("Replay message sequence does not match its event.")
            yield event


def _number(value, default=0.0):
    return default if pd.isna(value) else float(value)


def _flag(value):
    return False if pd.isna(value) else bool(value)


def _pressure_score(event, role):
    supported = event["innings"] in (1, 3) or (
        event["innings"] in (2, 4) and not pd.isna(event["target"])
    )
    if not supported:
        return None
    weights = PRESSURE_WEIGHTS["batting" if role == "batting" else "bowling"]
    score = 100.0 * sum(
        _number(event[f"{role}_{component}_component"]) * weight
        for component, weight in weights.items()
    )
    return min(100.0, max(0.0, score))


def replay_events(events, threshold=PRESSURE_THRESHOLD):
    """Rebuild pre-delivery state and pressure flags from an ordered event feed."""
    state = {}
    last_delivery = {}
    counts = {
        "delivery_count": 0,
        "ordering_errors": 0,
        "state_mismatches": 0,
        "pressure_mismatches": 0,
        "checked_batting_pressure_scores": 0,
        "checked_bowling_pressure_scores": 0,
    }
    examples = []
    for event in events:
        key = (int(event["match_id"]), int(event["innings"]))
        sequence = int(event["innings_ball_num"])
        if key in last_delivery and sequence <= last_delivery[key]:
            counts["ordering_errors"] += 1
            if len(examples) < 10:
                examples.append({"type": "ordering", "key": key, "sequence": sequence})
        last_delivery[key] = sequence
        current = state.setdefault(key, {"runs": 0, "wickets": 0, "legal_balls": 0})
        expected_before = (
            int(_number(event["score_before"])),
            int(_number(event["wickets_before"])),
            int(_number(event["legal_balls_before"])),
        )
        actual_before = (current["runs"], current["wickets"], current["legal_balls"])
        if expected_before != actual_before:
            counts["state_mismatches"] += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "type": "state",
                        "key": key,
                        "sequence": sequence,
                        "expected": expected_before,
                        "actual": actual_before,
                    }
                )
        for role in ("batting", "bowling"):
            calculated = _pressure_score(event, role)
            source_score = event[f"{role}_pressure"]
            if calculated is None:
                actual_flag = False
            else:
                counts[f"checked_{role}_pressure_scores"] += 1
                actual_flag = calculated >= threshold
                if pd.isna(source_score) or abs(calculated - float(source_score)) > 1e-8:
                    counts["pressure_mismatches"] += 1
                    if len(examples) < 10:
                        examples.append(
                            {
                                "type": f"{role}_pressure_score",
                                "key": key,
                                "sequence": sequence,
                                "calculated": calculated,
                                "batch": None if pd.isna(source_score) else float(source_score),
                            }
                        )
            if actual_flag != _flag(event[f"is_{role}_pressure"]):
                counts["pressure_mismatches"] += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "type": f"{role}_pressure_label",
                            "key": key,
                            "sequence": sequence,
                            "calculated": actual_flag,
                            "batch": _flag(event[f"is_{role}_pressure"]),
                        }
                    )

        runs = (
            _number(event["runs"])
            + _number(event["extras1_runs"])
            + _number(event["extras_2_runs"])
        )
        extras = "" if pd.isna(event["extras_type"]) else str(event["extras_type"])
        legal = extras not in NON_LEGAL_EXTRAS
        if legal != _flag(event["is_legal_ball"]):
            counts["state_mismatches"] += 1
        current["runs"] += int(runs)
        current["wickets"] += int(_flag(event["is_wicket"]))
        current["legal_balls"] += int(legal)
        counts["delivery_count"] += 1
    counts["innings_count"] = len(state)
    counts["validated"] = not any(
        counts[key] for key in ("ordering_errors", "state_mismatches", "pressure_mismatches")
    )
    counts["mismatch_examples"] = examples
    return counts


def run_replay(curated_path=CURATED, output_path=OUTPUT):
    """Run a deterministic full-archive historical replay and write validation."""
    frame = pd.read_parquet(curated_path, columns=list(dict.fromkeys(EVENT_COLUMNS)))
    frame = frame.sort_values(
        ["match_id", "innings", "innings_ball_num", "overid", "over_ball_num"],
        kind="stable",
    )
    producer = HistoricalDeliveryProducer()
    consumer = ReplayConsumer()
    result = replay_events(consumer.consume(producer.produce(frame)))
    result.update(
        {
            "mode": "historical replay simulation; no Kafka service was used",
            "producer": "HistoricalDeliveryProducer",
            "consumer": "ReplayConsumer",
            "topic": TOPIC,
            "partition_key": "match_id:innings",
            "ordering": ["match_id", "innings", "innings_ball_num", "overid", "over_ball_num"],
            "pressure_source": (
                "The replay recalculates weighted pressure from batch-enriched "
                "pre-delivery component fields; it independently reconstructs "
                "score, wickets, and legal balls from each event."
            ),
            "pressure_threshold": PRESSURE_THRESHOLD,
        }
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result


def main():
    result = run_replay()
    print(
        f"Replayed {result['delivery_count']:,} deliveries across "
        f"{result['innings_count']:,} innings; validated={result['validated']}"
    )
    if not result["validated"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
