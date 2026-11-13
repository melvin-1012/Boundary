#!/usr/bin/env python3
"""Hadoop Streaming-compatible mapper for JSON-delivery player aggregates."""

import json
import sys


FIELDS = (
    "runs",
    "balls",
    "fours",
    "sixes",
    "runs_conceded",
    "legal_balls",
    "wickets",
    "dots",
    "boundaries",
)


def _zero():
    return {field: 0.0 for field in FIELDS}


def map_delivery(event):
    results = []
    batter_id = event.get("striker_id")
    bowler_id = event.get("bowler_id")
    if batter_id is not None:
        for scope in ("all", "pressure"):
            if scope == "pressure" and not event.get("is_batting_pressure", False):
                continue
            value = _zero()
            value["runs"] = float(event.get("batter_runs") or 0)
            value["balls"] = float(
                bool(event.get("is_batter_ball_faced", False))
                if scope == "all"
                else bool(event.get("pressure_batter_ball", False))
            )
            value["fours"] = float(bool(event.get("is_four", False)))
            value["sixes"] = float(bool(event.get("is_six", False)))
            results.append((f"batter:{scope}:{int(batter_id)}", value))
    if bowler_id is not None:
        for scope in ("all", "pressure"):
            if scope == "pressure" and not event.get("is_bowling_pressure", False):
                continue
            value = _zero()
            value["runs_conceded"] = float(event.get("bowler_conceded_runs") or 0)
            value["legal_balls"] = float(
                bool(event.get("is_legal_ball", False))
                if scope == "all"
                else bool(event.get("pressure_bowler_ball", False))
            )
            value["wickets"] = float(bool(event.get("is_bowler_wicket", False)))
            value["dots"] = float(
                bool(event.get("is_dot_ball", False))
                and (
                    scope == "all"
                    or bool(event.get("is_bowling_pressure", False))
                )
            )
            value["boundaries"] = float(
                bool(event.get("has_boundary_flag", False))
                and (
                    scope == "all"
                    or bool(event.get("is_bowling_pressure", False))
                )
            )
            results.append((f"bowler:{scope}:{int(bowler_id)}", value))
    return results


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        event = json.loads(line)
        for key, value in map_delivery(event):
            print(f"{key}\t{json.dumps(value, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
