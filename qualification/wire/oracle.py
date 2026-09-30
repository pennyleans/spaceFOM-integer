"""Independent stdlib reader for the declared 2207SF01 observation profile.

This is a separate implementation, not a blind review: its author previously
read the adapter. No native/managed decoder or RTI encoding helper is imported.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct

MAGIC = b"2207SF01"
EPOCH_TT = 7529673600.00018
MAX_FRAMES = 115201
MAX_BODIES = 128
MAX_BODY_FRAMES = 2_000_000
MAX_FILE_BYTES = 256 * 1024 * 1024
STATE_BYTES = 112
FIELDS = (
    "position_x_m", "position_y_m", "position_z_m",
    "velocity_x_mps", "velocity_y_mps", "velocity_z_mps",
    "quaternion_w", "quaternion_x", "quaternion_y", "quaternion_z",
    "angular_velocity_x_radps", "angular_velocity_y_radps", "angular_velocity_z_radps",
    "tt_seconds",
)


class Rejected(ValueError):
    def __init__(self, field: str, offset: int, reason: str):
        self.field, self.offset, self.reason = field, offset, reason
        super().__init__(f"{field} at byte {offset}: {reason}")


@dataclass(frozen=True)
class Body:
    identifier: str
    name: str
    radius_m: float
    gm_m3ps2: float
    field_offsets: tuple[int, int, int, int]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decode_state(raw: bytes, offset: int, expected_time: float, field: str) -> tuple[float, ...]:
    if offset < 0 or len(raw) - offset < STATE_BYTES:
        raise Rejected(field, offset, "truncated 14-float64 state")
    values = struct.unpack_from("<14d", raw, offset)
    for i, value in enumerate(values):
        if not math.isfinite(value):
            raise Rejected(f"{field}.{FIELDS[i]}", offset + i * 8, "nonfinite")
    norm2 = math.fsum(value * value for value in values[6:10])
    if abs(norm2 - 1.0) > 1e-10:
        raise Rejected(f"{field}.quaternion", offset + 48, "norm squared differs from one")
    if values[13] != expected_time:
        raise Rejected(f"{field}.tt_seconds", offset + 104, "time differs from epoch plus tick/64")
    for start, stop, bound in ((0, 3, 1e14), (3, 6, 1e7), (10, 13, 100.0)):
        for i in range(start, stop):
            if abs(values[i]) > bound:
                raise Rejected(f"{field}.{FIELDS[i]}", offset + i * 8, "outside declared observation envelope")
    return values


class Spool:
    """Own an immutable byte snapshot; validate before exposing any state."""

    def __init__(self, raw: bytes):
        self.raw = bytes(raw)
        if len(raw) > MAX_FILE_BYTES:
            raise Rejected("file", 0, "file allocation bound")
        if len(raw) < 16:
            raise Rejected("header", len(raw), "truncated header")
        if raw[:8] != MAGIC:
            raise Rejected("magic", 0, "unsupported recording version")
        self.frame_count, self.body_count = struct.unpack_from("<ii", raw, 8)
        if not 1 <= self.frame_count <= MAX_FRAMES:
            raise Rejected("frame_count", 8, "outside profile bounds")
        if not 1 <= self.body_count <= MAX_BODIES:
            raise Rejected("body_count", 12, "outside profile bounds")
        if self.frame_count * self.body_count > MAX_BODY_FRAMES:
            raise Rejected("dimensions", 8, "combined body-frame allocation bound")
        self.record_bytes = 40 + STATE_BYTES * (self.body_count + 1)
        minimum = 16 + 26 * self.body_count + self.frame_count * self.record_bytes
        if len(raw) < minimum:
            raise Rejected("dimensions", 8, "declared dimensions exceed file size")
        cursor = 16

        def text(field: str) -> tuple[str, int]:
            nonlocal cursor
            start = cursor
            if len(raw) - cursor < 4:
                raise Rejected(field, cursor, "truncated text length")
            length, = struct.unpack_from("<i", raw, cursor)
            cursor += 4
            if not 1 <= length <= 128:
                raise Rejected(field, start, "text byte length outside profile bounds")
            if len(raw) - cursor < length:
                raise Rejected(field, cursor, "truncated text")
            encoded = raw[cursor:cursor + length]
            if any(byte < 32 or byte > 126 for byte in encoded):
                raise Rejected(field, cursor, "metadata is not printable ASCII")
            cursor += length
            return encoded.decode("ascii"), start

        bodies, identifiers = [], set()
        for index in range(self.body_count):
            prefix = f"bodies[{index}]"
            identifier, id_offset = text(prefix + ".id")
            name, name_offset = text(prefix + ".name")
            if identifier in identifiers:
                raise Rejected(prefix + ".id", id_offset, "duplicate body id")
            identifiers.add(identifier)
            if len(raw) - cursor < 16:
                raise Rejected(prefix, cursor, "truncated physical metadata")
            radius, gm = struct.unpack_from("<dd", raw, cursor)
            if not math.isfinite(radius) or not 1 <= radius <= 1e12:
                raise Rejected(prefix + ".radius_m", cursor, "invalid radius")
            if not math.isfinite(gm) or not 0 < gm <= 1e25:
                raise Rejected(prefix + ".gm_m3ps2", cursor + 8, "invalid gravitational parameter")
            bodies.append(Body(identifier, name, radius, gm, (id_offset, name_offset, cursor, cursor + 8)))
            cursor += 16
        self.bodies = tuple(bodies)
        self.frames_offset = cursor
        expected_size = cursor + self.frame_count * self.record_bytes
        if len(raw) != expected_size:
            raise Rejected("file", min(len(raw), expected_size), "truncated frames or trailing bytes")
        for index in range(self.frame_count):
            base = self.frame_offset(index)
            tick, = struct.unpack_from("<q", raw, base)
            if tick != index:
                raise Rejected(f"frames[{index}].tick", base, "ticks must be contiguous from zero")
            for body in range(self.body_count + 1):
                decode_state(raw, base + 40 + body * STATE_BYTES, EPOCH_TT + index / 64,
                             self.state_label(index, body))

    @classmethod
    def read(cls, path: Path) -> "Spool":
        if path.stat().st_size > MAX_FILE_BYTES:
            raise Rejected("file", 0, "file allocation bound")
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        return cls(raw)

    def frame_offset(self, index: int) -> int:
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        return self.frames_offset + index * self.record_bytes

    @staticmethod
    def state_label(index: int, body: int) -> str:
        return f"frames[{index}]." + ("vessel" if body == 0 else f"bodies[{body - 1}]")

    def summary(self) -> dict:
        return {"schema": "independent-wire-decode-v1", "sha256": sha256(self.raw),
                "bytes": len(self.raw), "frames": self.frame_count, "bodies": self.body_count,
                "states": self.frame_count * (self.body_count + 1),
                "body_ids": [body.identifier for body in self.bodies],
                "first_tick": 0, "last_tick": self.frame_count - 1,
                "epoch_tt_seconds": EPOCH_TT, "hz": 64,
                "source_hash_scope": "carried provenance, not authentication or reconstructed authority"}


def first_divergence(left: Spool, right: Spool) -> dict | None:
    def difference(field, lo, ro, lv, rv, width=None):
        result = {"field": field, "left_offset": lo, "right_offset": ro,
                  "left": lv, "right": rv}
        if width:
            result.update(left_hex=left.raw[lo:lo + width].hex(), right_hex=right.raw[ro:ro + width].hex())
        return result

    for field, offset in (("frame_count", 8), ("body_count", 12)):
        lv, rv = getattr(left, field), getattr(right, field)
        if lv != rv:
            return difference(field, offset, offset, lv, rv, 4)
    for i, (lb, rb) in enumerate(zip(left.bodies, right.bodies)):
        for j, field in enumerate(("identifier", "name", "radius_m", "gm_m3ps2")):
            lv, rv = getattr(lb, field), getattr(rb, field)
            lo, ro = lb.field_offsets[j], rb.field_offsets[j]
            differs = lv != rv if j < 2 else left.raw[lo:lo + 8] != right.raw[ro:ro + 8]
            if differs:
                return difference(f"bodies[{i}].{field}", lo, ro, lv, rv, 8 if j >= 2 else None)
    for i in range(left.frame_count):
        lo, ro = left.frame_offset(i), right.frame_offset(i)
        if left.raw[lo:lo + 8] != right.raw[ro:ro + 8]:
            return difference(f"frames[{i}].tick", lo, ro, i, i, 8)
        if left.raw[lo + 8:lo + 40] != right.raw[ro + 8:ro + 40]:
            return difference(f"frames[{i}].provenance", lo + 8, ro + 8,
                              left.raw[lo + 8:lo + 40].hex(), right.raw[ro + 8:ro + 40].hex(), 32)
        for body in range(left.body_count + 1):
            for field_index, field in enumerate(FIELDS):
                lp = lo + 40 + body * STATE_BYTES + field_index * 8
                rp = ro + 40 + body * STATE_BYTES + field_index * 8
                if left.raw[lp:lp + 8] != right.raw[rp:rp + 8]:
                    return difference(left.state_label(i, body) + "." + field, lp, rp,
                                      struct.unpack_from("<d", left.raw, lp)[0],
                                      struct.unpack_from("<d", right.raw, rp)[0], 8)
    if left.raw != right.raw:
        raise AssertionError("comparison failed to cover every encoded field")
    return None


def compare(left: Spool, right: Spool) -> dict:
    divergence = first_divergence(left, right)
    return {"schema": "independent-wire-compare-v1", "equal": divergence is None,
            "left_sha256": sha256(left.raw), "right_sha256": sha256(right.raw),
            "first_divergence": divergence,
            "scope": "exact metadata, tick, provenance and binary64 field bits including signed zero"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("decode", "compare"))
    parser.add_argument("left", type=Path)
    parser.add_argument("right", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        left = Spool.read(args.left)
        if args.operation == "decode":
            result = left.summary()
        else:
            if args.right is None:
                parser.error("compare requires two recordings")
            result = compare(left, Spool.read(args.right))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result.get("equal", True) else 1
    except Rejected as error:
        print(json.dumps({"accepted": False, "field": error.field, "offset": error.offset,
                          "reason": error.reason}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
