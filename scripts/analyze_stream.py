#!/usr/bin/env python3
"""Check rate, sequence loss and read/arrival spacing in an IMU session CSV."""
import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imu_protocol import Sample, StreamStats, UINT32_MASK


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered)-1)*percent/100
    left = int(position)
    fraction = position-left
    return ordered[left]*(1-fraction)+ordered[min(left+1, len(ordered)-1)]*fraction


def analyze(path, target_hz=100, minimum_seconds=30):
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if len(rows) < 2:
        raise ValueError("At least two measurements are required")
    stats = StreamStats()
    board_times, arrivals, magnitudes, gyros = [], [], [], []
    for row in rows:
        data = Sample(int(row["seq"]), int(row["device_ms"]),
                      *[float(row[k]) for k in ("ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps")])
        vector = (data.ax_g, data.ay_g, data.az_g, data.gx_dps, data.gy_dps, data.gz_dps)
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("Non-finite sensor value")
        board_times.append(stats.observe(data))
        arrivals.append(float(row["received_unix_s"]))
        magnitudes.append(math.sqrt(sum(value*value for value in vector[:3])))
        gyros.append(math.sqrt(sum(value*value for value in vector[3:])))
    intervals = [((int(b["device_ms"])-int(a["device_ms"])) & UINT32_MASK)
                 for a, b in zip(rows, rows[1:])]
    arrival_intervals = [(b-a)*1000 for a, b in zip(arrivals, arrivals[1:])]
    arrival_duration = arrivals[-1]-arrivals[0]
    if arrival_duration <= 0:
        raise ValueError("Receive timestamps do not advance")
    arrival_hz = (stats.count-1)/arrival_duration
    # Relative clock origins cancel here. This is offset variation, not a
    # synchronized measurement of absolute end-to-end latency.
    offset = [(arrival-arrivals[0]-board)*1000 for arrival, board in zip(arrivals, board_times)]
    conditions = {
        "duration": board_times[-1] >= minimum_seconds,
        "board_rate": abs(stats.rate_hz-target_hz) <= target_hz*.05,
        "arrival_rate": abs(arrival_hz-target_hz) <= target_hz*.05,
        "no_sequence_gaps": stats.missing == 0,
        "read_spacing": min(intervals) > 0 and max(intervals) <= 1500/target_hz,
    }
    result = {
        "csv": str(path.resolve()), "target_hz": target_hz,
        "count": stats.count, "sequence_gaps": stats.missing,
        "first_seq": int(rows[0]["seq"]), "last_seq": int(rows[-1]["seq"]),
        "board_duration_s": board_times[-1], "arrival_duration_s": arrival_duration,
        "board_rate_hz": stats.rate_hz, "arrival_rate_hz": arrival_hz,
        "board_read_spacing_ms": {"min": min(intervals), "median": statistics.median(intervals),
            "mean": statistics.mean(intervals), "p95": percentile(intervals, 95), "max": max(intervals)},
        "arrival_spacing_ms": {"min": min(arrival_intervals), "median": statistics.median(arrival_intervals),
            "p95": percentile(arrival_intervals, 95), "max": max(arrival_intervals)},
        "relative_arrival_offset_range_ms": max(offset)-min(offset),
        "acceleration_magnitude_median_g": statistics.median(magnitudes),
        "angular_rate_magnitude_max_dps": max(gyros),
        "checks": conditions, "passed": all(conditions.values()),
        "timestamp_note": "device_ms is MCU read completion time; arrival offset range is not absolute latency",
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--target-hz", type=float, default=100)
    parser.add_argument("--minimum-seconds", type=float, default=30)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.target_hz <= 0 or args.minimum_seconds < 0:
        parser.error("target-hz must be positive; minimum-seconds must be nonnegative")
    result = analyze(args.csv, args.target_hz, args.minimum_seconds)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)+"\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
