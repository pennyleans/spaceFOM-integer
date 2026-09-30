"""Supplement frozen wire evidence with asymmetric semantics and isolated mutants."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from build_faults import digest, redact, write_json
from test_oracle import run_checks, run_semantic_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-state", required=True, type=Path)
    parser.add_argument("--boundary-receipt", required=True, type=Path)
    parser.add_argument("--boundary-source", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    scratch, evidence = args.scratch.resolve(), args.evidence.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent
    original_known_hash = digest(source / "known_state.json")
    original_receipt = repo / "evidence/qualification/wire/run02/oracle-tests.json"
    original_receipt_hash = digest(original_receipt)
    raw = args.production_state.read_bytes()
    production = run_semantic_checks(raw)
    complete = run_checks()
    (evidence / "asymmetric-mapped-state.bin").write_bytes(raw)
    (evidence / "boundary-receipt.json").write_bytes(args.boundary_receipt.read_bytes())
    write_json(evidence / "semantic-receipt.json", production)
    write_json(evidence / "oracle-tests-v2.json", complete)

    mutations = (
        ("quaternion-yz-label-swap", '"quaternion_y", "quaternion_z"',
         '"quaternion_z", "quaternion_y"', "semantic component mismatch: quaternion_y"),
        ("wrong-decoder-conjugation", '    values = struct.unpack_from("<14d", raw, offset)',
         '    values = struct.unpack_from("<14d", raw, offset)\n'
         '    values = tuple(-v if 7 <= i <= 9 else v for i, v in enumerate(values))',
         "semantic component mismatch: quaternion_x"),
    )
    mutant_results = []
    for name, anchor, replacement, expected in mutations:
        target = scratch / name
        target.mkdir()
        for filename in ("oracle.py", "test_oracle.py", "known_state.json", "asymmetric_state.json"):
            (target / filename).write_bytes((source / filename).read_bytes())
        old = (target / "oracle.py").read_text()
        if old.count(anchor) != 1:
            raise RuntimeError("mutation anchor changed: " + name)
        new = old.replace(anchor, replacement, 1)
        (target / "oracle.py").write_text(new, encoding="utf-8", newline="\n")
        patch = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                           "accepted/oracle.py", name + "/oracle.py"))
        (evidence / (name + ".patch")).write_text(patch, encoding="utf-8", newline="\n")
        result = subprocess.run([sys.executable, str(target / "test_oracle.py")],
                                capture_output=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        original = result.stdout + b"\n--- stderr ---\n" + result.stderr
        (target / "result.raw.log").write_bytes(original)
        clean = redact(original.decode(errors="replace"), [(scratch, "$SCRATCH"), (repo, "$REPO")]).encode()
        (evidence / (name + ".log")).write_bytes(clean)
        if result.returncode == 0 or expected.encode() not in result.stderr:
            raise AssertionError("semantic mutant did not fail at expected named component: " + name)
        mutant_results.append({"name": name, "exit": result.returncode, "expected_rejection": expected,
                               "mutated_oracle_sha256": digest(target / "oracle.py"),
                               "patch_sha256": digest(evidence / (name + ".patch")),
                               "original_log_sha256": hashlib.sha256(original).hexdigest(),
                               "redacted_log_sha256": hashlib.sha256(clean).hexdigest()})
    if original_known_hash != digest(source / "known_state.json") or original_receipt_hash != digest(original_receipt):
        raise AssertionError("original fixture or accepted 61-gate receipt changed")
    summary = {"schema": "wire-semantic-supplement-v1", "passed": True,
               "original_61_gate_receipt_sha256": original_receipt_hash,
               "original_known_state_document_sha256": original_known_hash,
               "original_fixture_and_receipt_unchanged": True,
               "updated_default_gate_count": complete["count"],
               "supplemental_gate_count_with_production": production["count"],
               "boundary_source": {"path": args.boundary_source.resolve().relative_to(repo).as_posix(),
                                    "sha256": digest(args.boundary_source)},
               "boundary_receipt_sha256": digest(args.boundary_receipt),
               "production_wire_sha256": digest(args.production_state),
               "producer_inputs": {"position_mm": [1250, -2500, 3750], "position_remainder": [0, 0, 0],
                                   "velocity_nmps": [4_000_000_000, -8_000_000_000, 16_000_000_000],
                                   "velocity_remainder": [0, 0, 0], "attitude_scale": 2**60,
                                   "body_to_parent_attitude": "integer-truncated (1,2,4,10)*scale/11",
                                   "body_rates_nradps": [125_000_000, -250_000_000, 500_000_000],
                                   "angular_remainder": [0, 0, 0], "tick": 64},
               "isolated_source_mutants": mutant_results,
               "qualification_sources": [{"path": path.relative_to(repo).as_posix(), "sha256": digest(path)}
                                         for path in sorted(source.iterdir()) if path.is_file()],
               "scope": "supplemental semantic qualification authored separately; independent hostile re-review pending"}
    write_json(evidence / "summary.json", summary)
    print(json.dumps({"passed": True, "default_gates": complete["count"],
                      "semantic_gates": production["count"], "external_mutants_rejected": len(mutant_results)}))


if __name__ == "__main__":
    main()
