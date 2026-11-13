#!/usr/bin/env python3
"""Hadoop Streaming-compatible reducer and combiner for mapper emissions."""

import json
import sys


def reduce_sorted_lines(lines):
    current_key = None
    totals = {}
    for line in lines:
        key, value_json = line.rstrip("\n").split("\t", 1)
        if current_key is not None and key != current_key:
            yield current_key, totals
            totals = {}
        current_key = key
        value = json.loads(value_json)
        for field, amount in value.items():
            totals[field] = totals.get(field, 0.0) + float(amount)
    if current_key is not None:
        yield current_key, totals


def main():
    for key, values in reduce_sorted_lines(sys.stdin):
        print(f"{key}\t{json.dumps(values, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
