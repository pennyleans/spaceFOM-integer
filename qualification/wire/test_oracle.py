"""Known-byte oracle and hostile profile tests. No production code imports."""
from pathlib import Path
import argparse
from fractions import Fraction
import json
import math
import struct

from oracle import EPOCH_TT, FIELDS, Rejected, Spool, compare, decode_state, sha256


def semantic_observation(raw, fixture, fields=None):
    """Read components through their declared names, then apply the passive rotation."""
    if fields is None:
        fields = FIELDS
    expected = {name: float(Fraction(value)) for name, value in fixture["expected_by_name"].items()}
    if len(fields) != 14 or len(set(fields)) != 14 or set(fields) != set(expected):
        raise AssertionError("semantic field names differ")
    if len(raw) != 112:
        raise AssertionError("semantic state must be exactly 112 bytes")
    values = decode_state(raw, 0, expected["tt_seconds"], "asymmetric")
    named = dict(zip(fields, values))
    tolerance = fixture["quaternion_and_basis_tolerance"]
    for name, wanted in expected.items():
        observed = named[name]
        if name.startswith("quaternion_"):
            if abs(observed - wanted) > tolerance:
                raise AssertionError("semantic component mismatch: " + name)
        elif struct.pack("<d", observed) != struct.pack("<d", wanted):
            raise AssertionError("semantic component mismatch: " + name)
    w, x, y, z = (named["quaternion_" + axis] for axis in ("w", "x", "y", "z"))
    # q is parent-to-body: q * parent_x * conjugate(q), with no second conjugation.
    parent_x_in_body = [w*w + x*x - y*y - z*z, 2*(x*y + w*z), 2*(x*z - w*y)]
    expected_basis = [float(Fraction(value)) for value in fixture["parent_x_in_body"]]
    for axis, observed, wanted in zip("xyz", parent_x_in_body, expected_basis):
        if abs(observed - wanted) > tolerance:
            raise AssertionError("passive parent-x direction mismatch: body " + axis)
    return {"named_components": named, "parent_x_in_body": parent_x_in_body,
            "expected_parent_x_in_body": expected_basis, "tolerance": tolerance}


def run_semantic_checks(production_raw=None):
    fixture_path = Path(__file__).with_name("asymmetric_state.json")
    fixture = json.loads(fixture_path.read_text())
    known = bytes.fromhex("".join(fixture["little_endian_words"]))
    observed = semantic_observation(known, fixture)
    checks = ["asymmetric named component " + name for name in fixture["expected_by_name"]]
    checks.append("asymmetric parent x maps to hand-derived body (-111,-4,48)/121")
    rejected = []

    def rejects(label, raw=known, fields=None):
        try:
            semantic_observation(raw, fixture, fields)
        except (AssertionError, Rejected) as failure:
            rejected.append({"mutation": label, "rejection": str(failure)})
            checks.append("semantic mutation rejected: " + label)
            return
        raise AssertionError("semantic mutant survived: " + label)

    names = list(FIELDS)
    yi, zi = names.index("quaternion_y"), names.index("quaternion_z")
    names[yi], names[zi] = names[zi], names[yi]
    rejects("quaternion y/z label swap", fields=names)
    swapped = bytearray(known)
    swapped[64:72], swapped[72:80] = known[72:80], known[64:72]
    rejects("quaternion y/z wire swap", raw=bytes(swapped))
    conjugated = bytearray(known)
    for index in (7, 8, 9):
        value, = struct.unpack_from("<d", known, index * 8)
        struct.pack_into("<d", conjugated, index * 8, -value)
    rejects("wrong conjugation", raw=bytes(conjugated))
    rates = list(FIELDS)
    ai, bi = rates.index("angular_velocity_y_radps"), rates.index("angular_velocity_z_radps")
    rates[ai], rates[bi] = rates[bi], rates[ai]
    rejects("body angular y/z label swap", fields=rates)
    result = {"schema": "independent-wire-semantics-v1", "passed": True,
              "count": len(checks), "checks": checks, "fixture_sha256": sha256(known),
              "fixture_document_sha256": sha256(fixture_path.read_bytes()),
              "known_observation": observed, "mutation_rejections": rejected,
              "scope": "named-component and passive-rotation semantics; not general astronomical frame accuracy"}
    if production_raw is not None:
        result["production_observation"] = semantic_observation(production_raw, fixture)
        result["production_wire_sha256"] = sha256(production_raw)
        result["production_bits_equal_known"] = production_raw == known
        checks.append("production From export matches declared asymmetric components and passive basis")
        result["count"] = len(checks)
    return result


def sample() -> bytes:
    raw = bytearray(b"2207SF01" + struct.pack("<ii", 3, 2))
    for identifier, name in ((b"301", b"moon"), (b"399", b"earth")):
        for text in (identifier, name):
            raw += struct.pack("<i", len(text)) + text
        raw += struct.pack("<dd", 1_000_000, 1e12)
    for tick in range(3):
        raw += struct.pack("<q", tick) + bytes(range(32))
        for index in range(3):
            raw += struct.pack("<14d", index + tick, -2, .5, 4, -8, .125,
                               1, 0, 0, 0, .25, -.5, 2, EPOCH_TT + tick / 64)
    return bytes(raw)


def run_checks() -> dict:
    passed = []

    def gate(condition, label):
        if not condition:
            raise AssertionError(label)
        passed.append(label)

    def refuses(raw, label, expected=None):
        try:
            Spool(raw)
        except Rejected as error:
            if expected and expected not in error.field:
                raise AssertionError(f"{label}: unexpected field {error.field}") from error
            passed.append(label)
            return
        raise AssertionError(f"{label}: accepted")

    fixture = json.loads(Path(__file__).with_name("known_state.json").read_text())
    known = bytes.fromhex("".join(fixture["little_endian_words"]))
    gate(len(known) == 112, "known fixture has exactly fourteen float64 words")
    values = decode_state(known, 0, .015625, "known")
    for name, observed, expected in zip(FIELDS, values, fixture["values"]):
        gate(observed == expected, "known value " + name)
    gate(struct.pack("<14d", *fixture["values"]) == known, "known byte identity in the reverse direction")

    raw = sample()
    spool = Spool(raw)
    gate(spool.frame_count == 3 and spool.body_count == 2, "all declared dimensions decoded")
    gate(spool.bodies[1].identifier == "399" and spool.bodies[1].name == "earth",
         "body order and both metadata strings decoded")
    gate(compare(spool, Spool(raw))["equal"], "all fields equal for identical spool")

    def changed(offset, data):
        result = bytearray(raw)
        result[offset:offset + len(data)] = data
        return bytes(result)

    for label, offset, value in (("negative frames", 8, -1), ("zero frames", 8, 0),
                                  ("too many frames", 8, 115202), ("negative bodies", 12, -1),
                                  ("zero bodies", 12, 0), ("too many bodies", 12, 129)):
        refuses(changed(offset, struct.pack("<i", value)), label)
    dimension_header = bytearray(raw)
    struct.pack_into("<ii", dimension_header, 8, 115201, 128)
    refuses(dimension_header, "combined allocation bound", "dimensions")
    refuses(changed(0, b"x"), "bad magic", "magic")
    for size in (0, 7, 15, 16, len(raw) - 1):
        refuses(raw[:size], f"truncation at {size}")
    refuses(raw + b"\x00", "trailing data")
    for length in (-1, 0, 129, 2**31 - 1):
        refuses(changed(16, struct.pack("<i", length)), f"string length {length}")
    refuses(changed(20, b"\x00"), "nul in metadata", ".id")
    refuses(changed(20, b"\xff"), "nonascii metadata", ".id")
    refuses(changed(spool.bodies[1].field_offsets[0] + 4, b"301"), "duplicate body id", ".id")
    radius_offset, gm_offset = spool.bodies[0].field_offsets[2:]
    for label, offset, value in (("nan radius", radius_offset, math.nan),
                                 ("zero radius", radius_offset, 0),
                                 ("infinite gm", gm_offset, math.inf), ("negative gm", gm_offset, -1)):
        refuses(changed(offset, struct.pack("<d", value)), label)
    frame = spool.frame_offset(1)
    refuses(changed(frame, struct.pack("<q", 2)), "skipped tick", ".tick")
    refuses(changed(frame, struct.pack("<q", 0)), "repeated tick", ".tick")
    for name, index, value in (("nan position", 0, math.nan), ("infinite velocity", 3, math.inf),
                               ("zero attitude", 6, 0), ("nonunit attitude", 6, 2),
                               ("position envelope", 0, 1e15), ("velocity envelope", 3, 1e8),
                               ("angular envelope", 10, 101), ("wrong time", 13, EPOCH_TT),
                               ("negative time", 13, -1)):
        refuses(changed(frame + 40 + index * 8, struct.pack("<d", value)), name)
    refuses(changed(frame + 40 + 112 * 2 + 104, struct.pack("<d", EPOCH_TT)),
            "last body time checked", ".bodies[1].tt_seconds")
    field_mutation = Spool(changed(frame + 40, struct.pack("<d", 99)))
    d = compare(spool, field_mutation)["first_divergence"]
    gate(d["field"] == "frames[1].vessel.position_x_m" and d["left_offset"] == frame + 40
         and d["left"] == 1 and d["right"] == 99, "first differing numeric field and offset")
    provenance = Spool(changed(frame + 8, b"\xff"))
    gate(compare(spool, provenance)["first_divergence"]["field"] == "frames[1].provenance",
         "first differing carried provenance, no authority claim")
    signed_zero = Spool(changed(frame + 40 + 7 * 8, struct.pack("<d", -0.0)))
    gate(compare(spool, signed_zero)["first_divergence"]["field"] == "frames[1].vessel.quaternion_x",
         "signed zero is a bitwise difference")
    name = Spool(changed(spool.bodies[0].field_offsets[1] + 4, b"Moon"))
    gate(compare(spool, name)["first_divergence"]["field"] == "bodies[0].name", "metadata name difference")
    radius = Spool(changed(radius_offset, struct.pack("<d", 1_000_001)))
    gate(compare(spool, radius)["first_divergence"]["field"] == "bodies[0].radius_m", "metadata radius difference")
    semantics = run_semantic_checks()
    passed.extend(semantics["checks"])
    return {"schema": "independent-wire-oracle-tests-v2", "passed": True, "count": len(passed),
            "checks": passed, "known_fixture_sha256": sha256(known),
            "first_divergence_example": d,
            "asymmetric_semantics": semantics,
            "independence": "separately implemented oracle; author previously read adapter source"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic-only", action="store_true")
    parser.add_argument("--production-state", type=Path)
    args = parser.parse_args()
    if args.production_state and not args.semantic_only:
        parser.error("--production-state requires --semantic-only")
    result = run_semantic_checks(args.production_state.read_bytes() if args.production_state else None) if args.semantic_only else run_checks()
    print(json.dumps(result, indent=2, allow_nan=False))
