#!/usr/bin/env python3
"""Compare the per-update states TrickHLA logged with the published recording.

The TrickHLA observer writes one INTEROP line per received update with the
object name, the HLA logical time derived from the state time tag, and the
fourteen decoded state values at full precision. This script matches those
lines to the recording decoded with the independent wire oracle, tick by tick,
and reports which fields match bit for bit and the largest difference for the
fields that do not.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wire"))
from oracle import EPOCH_TT, Spool, decode_state  # noqa: E402

FIELDS = (
    "pos_x", "pos_y", "pos_z",
    "vel_x", "vel_y", "vel_z",
    "quat_w", "quat_x", "quat_y", "quat_z",
    "ang_x", "ang_y", "ang_z",
    "time",
)

LINE = re.compile(
    r"INTEROP object=(?P<object>\S+) tick=(?P<tick>\d+) hla_time_us=(?P<hla>\d+) "
    r"time=(?P<time>\S+) pos=(?P<pos>\S+),(?P<pos2>\S+),(?P<pos3>\S+) "
    r"vel=(?P<vel>\S+),(?P<vel2>\S+),(?P<vel3>\S+) "
    r"quat=(?P<quat>\S+),(?P<quat2>\S+),(?P<quat3>\S+),(?P<quat4>\S+) "
    r"ang_vel=(?P<ang>\S+),(?P<ang2>\S+),(?P<ang3>\S+)"
)


def parse_log(path: Path) -> dict:
    updates = {}
    for line in path.read_text(errors="replace").splitlines():
        match = LINE.search(line)
        if not match:
            continue
        values = (
            match.group("pos"), match.group("pos2"), match.group("pos3"),
            match.group("vel"), match.group("vel2"), match.group("vel3"),
            match.group("quat"), match.group("quat2"), match.group("quat3"), match.group("quat4"),
            match.group("ang"), match.group("ang2"), match.group("ang3"),
            match.group("time"),
        )
        key = (match.group("object"), int(match.group("tick")))
        updates[key] = (int(match.group("hla")), tuple(float(value) for value in values))
    return updates


def relative(reference: float, value: float) -> float:
    if reference == value:
        return 0.0
    scale = max(abs(reference), abs(value), 1e-300)
    return abs(reference - value) / scale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path, help="TrickHLA log with INTEROP lines")
    parser.add_argument("--recording", required=True, type=Path, help="published recording")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    updates = parse_log(args.log)
    spool = Spool.read(args.recording)
    body_index = {body.identifier: index for index, body in enumerate(spool.bodies)}

    targets = {
        "orbital_vessel": 0,
        "body_10": body_index["10"] + 1,
    }

    report = {"recording": str(args.recording), "log": str(args.log), "objects": {}}
    for name, state_index in targets.items():
        exact = {field: 0 for field in FIELDS}
        worst = {field: 0.0 for field in FIELDS}
        worst_tick = {field: None for field in FIELDS}
        compared = 0
        missing = []
        for tick in range(spool.frame_count):
            key = (name, tick)
            if key not in updates:
                missing.append(tick)
                continue
            recorded = decode_state(
                spool.raw,
                spool.frame_offset(tick) + 40 + state_index * 112,
                EPOCH_TT + tick / 64,
                f"{name}[{tick}]",
            )
            hla_time, received = updates[key]
            compared += 1
            if hla_time != tick * 15625:
                report.setdefault("hla_time_mismatch", []).append([name, tick, hla_time])
            for field_index, field in enumerate(FIELDS):
                if recorded[field_index] == received[field_index]:
                    exact[field] += 1
                else:
                    difference = relative(recorded[field_index], received[field_index])
                    if difference > worst[field]:
                        worst[field] = difference
                        worst_tick[field] = tick
        report["objects"][name] = {
            "updates_compared": compared,
            "missing_ticks": len(missing),
            "first_missing": missing[:5],
            "fields": {
                field: {
                    "exact_matches": exact[field],
                    "max_relative_difference": worst[field],
                    "worst_tick": worst_tick[field],
                }
                for field in FIELDS
            },
        }

    root_updates = {tick: values for (name, tick), values in updates.items() if name == "SolarSystemBarycentricInertial"}
    root = {"updates": len(root_updates)}
    if root_updates:
        tick, (hla_time, values) = sorted(root_updates.items())[0]
        expected = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, EPOCH_TT + tick / 64)
        root.update({
            "tick": tick,
            "hla_time_us": hla_time,
            "exact_matches": sum(1 for a, b in zip(expected, values) if a == b),
            "time_matches": values[13] == EPOCH_TT + tick / 64,
        })
    report["objects"]["SolarSystemBarycentricInertial"] = root

    text = json.dumps(report, indent=2)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
