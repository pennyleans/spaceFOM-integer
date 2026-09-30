"""Bounded real-HLA probes. All subprocesses are local and cleaned up by handle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from build_faults import digest, redact, write_json
from oracle import Spool, compare
from test_oracle import run_checks

FROZEN_SHA256 = "b83ad5e6eada4626606e1d5358af97e49a25c102a51b5a8364b3b1efdf0efc56"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--fault-publisher", type=Path, required=True)
    parser.add_argument("--fault-build-receipt", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 20:
        parser.error("fault trial deadline must be between 10 and 20 seconds")
    repo = Path(__file__).resolve().parents[2]
    scratch, evidence = args.scratch.resolve(), args.evidence.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    runtime = repo / "out/transport/runtime/bin"
    adapter = repo / "out/transport/adapter-build/Release"
    fom = repo / "out/transport/TrickHLA/FOMs/SpaceFOM"
    published = repo / "data/published.sf"
    fault_publisher = args.fault_publisher.resolve()
    build = json.loads(args.fault_build_receipt.read_text(encoding="utf-8-sig"))
    if not build["passed"] or digest(fault_publisher) != build["publisher_sha256"]:
        raise RuntimeError("fault publisher does not match its build receipt")
    if digest(published) != FROZEN_SHA256:
        raise RuntimeError("frozen publisher input differs")
    accepted = Spool.read(published)
    baseline = {p: digest(p) for p in [published, *sorted((repo / "native/spacefom").glob("*"))] if p.is_file()}
    replacements = [(repo, "$REPO"), (scratch, "$SCRATCH"),
                    (fault_publisher.parents[2], "$FAULT_BUILD")]
    checks = run_checks()
    write_json(evidence / "oracle-tests.json", checks)
    write_json(evidence / "frozen-decode.json", accepted.summary())
    identities = {"accepted_files": [{"path": p.relative_to(repo).as_posix(), "sha256": h}
                                      for p, h in baseline.items()],
                  "binaries": [{"path": p.relative_to(repo).as_posix(), "sha256": digest(p)}
                               for p in sorted(runtime.glob("*")) if p.is_file()] +
                              [{"path": p.relative_to(repo).as_posix(), "sha256": digest(p)}
                               for p in sorted(adapter.glob("*.exe"))],
                  "fom": [{"path": p.relative_to(repo).as_posix(), "sha256": digest(p)}
                          for p in sorted(fom.glob("*.xml"))],
                  "fault_publisher_sha256": digest(fault_publisher),
                  "fault_build_receipt_sha256": digest(args.fault_build_receipt),
                  "test_sources": [{"path": p.relative_to(repo).as_posix(), "sha256": digest(p)}
                                   for p in sorted(Path(__file__).parent.iterdir()) if p.is_file()]}
    write_json(evidence / "identities.json", identities)
    environment = os.environ.copy()
    environment["PATH"] = str(runtime) + os.pathsep + environment.get("PATH", "")
    environment.pop("SF_QUAL_FAULT", None)

    def trial(name, observer_delay=0.0, fault="", interrupt=""):
        work = scratch / name
        result_dir = evidence / name
        work.mkdir()
        result_dir.mkdir()
        output = work / "observed.sf"
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        url, federation = f"rti://127.0.0.1:{port}", f"qualification_{port}"
        processes, streams, commands = {}, [], {}
        started, natural = {}, {}
        forced, event, timed_out, error = [], None, False, None
        began = time.monotonic()
        deadline = began + args.timeout
        trial_environment = environment.copy()
        if fault:
            trial_environment["SF_QUAL_FAULT"] = fault

        def launch(role, command):
            stdout = (work / f"{role}.stdout.raw.log").open("xb")
            stderr = (work / f"{role}.stderr.raw.log").open("xb")
            streams.extend((stdout, stderr))
            process = subprocess.Popen([str(x) for x in command], stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, env=trial_environment, cwd=work,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            processes[role] = process
            started[role] = time.monotonic() - began
            commands[role] = [redact(str(x), replacements) for x in command]

        try:
            launch("rti", [runtime / "rtinode.exe", "-i", url])
            time.sleep(.15)
            if processes["rti"].poll() is not None:
                raise RuntimeError("owned RTI server failed to start")
            launch("publisher", [fault_publisher if fault else adapter / "spacefom-publisher.exe",
                                 published, fom, url, federation])
            if observer_delay:
                time.sleep(observer_delay)
            launch("observer", [adapter / "spacefom-observer.exe", output, url, federation])
            while True:
                for role in ("publisher", "observer"):
                    status = processes[role].poll()
                    if status is not None and role not in natural and role not in forced:
                        natural[role] = {"exit": status, "seconds": time.monotonic() - began}
                if interrupt and event is None:
                    log = (work / "publisher.stdout.raw.log").read_bytes()
                    if b"qualification_interrupt_ready tick=256" in log:
                        target = processes[interrupt]
                        alive = target.poll() is None
                        event = {"target": interrupt, "marker": "qualification_interrupt_ready tick=256",
                                 "target_alive": alive, "seconds": time.monotonic() - began}
                        if not alive:
                            raise RuntimeError("interrupt target already exited")
                        # kill uses the exact process handle held by Popen, never a name search.
                        target.kill()
                        target.wait(timeout=2)
                        forced.append(interrupt)
                        event["exit_after_kill"] = target.returncode
                if all(processes[role].poll() is not None for role in ("publisher", "observer")):
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(.005)
        except Exception as failure:
            error = redact(str(failure), replacements)
        finally:
            for role, process in reversed(list(processes.items())):
                if process.poll() is None:
                    process.kill()
                    forced.append(role)
                process.wait(timeout=3)
            for stream in streams:
                stream.close()
        logs = []
        for path in sorted(work.glob("*.raw.log")):
            raw = path.read_bytes()
            clean = redact(raw.decode("utf-8", errors="replace"), replacements).encode()
            clean_name = path.name.replace(".raw", "")
            (result_dir / clean_name).write_bytes(clean)
            logs.append({"file": clean_name, "original_sha256": hashlib.sha256(raw).hexdigest(),
                         "redacted_sha256": hashlib.sha256(clean).hexdigest(), "original_bytes": len(raw)})
        observer_error = (work / "observer.stderr.raw.log").read_text(errors="replace") if "observer" in processes else ""
        exists = output.exists()
        partial_exists = Path(str(output) + ".partial").exists()
        comparison = None
        if exists:
            try:
                comparison = compare(accepted, Spool.read(output))
            except Exception as failure:
                comparison = {"accepted": False, "error": redact(str(failure), replacements)}
        expected_success = not fault
        transport_pass = (not error and not timed_out and all(natural.get(role, {}).get("exit") == 0
                          for role in ("publisher", "observer")) and comparison is not None
                          and comparison.get("equal") is True and not partial_exists)
        containment_pass = (not error and not exists and not partial_exists and
                            (event is not None if interrupt else "time grant without complete frame" in observer_error))
        receipt = {"schema": "wire-hla-probe-v1", "name": name, "expected_success": expected_success,
                   "passed": transport_pass if expected_success else containment_pass,
                   "pass_criterion": "complete exact exchange" if expected_success else "fault detected or injected and no committed or partial observer output",
                   "both_federates_terminated_without_deadline_cleanup": not timed_out,
                   "recovery_timing_qualified": False,
                   "federation": federation, "url": url, "deadline_seconds": args.timeout,
                   "elapsed_seconds": time.monotonic() - began, "deadline_reached": timed_out,
                   "commands": commands, "process_start_seconds": started,
                   "observer_start_delay_seconds": started.get("observer", 0) - started.get("publisher", 0),
                   "requested_observer_delay_seconds": observer_delay, "fault_selector": fault,
                   "interrupt": event, "natural_exits": natural, "forced_cleanup_or_interrupt": forced,
                   "processes": {role: {"pid": p.pid, "exit": p.returncode, "reaped": p.poll() is not None}
                                 for role, p in processes.items()},
                   "observed_committed": exists, "partial_output_exists": partial_exists,
                   "comparison": comparison, "error": error, "logs": logs,
                   "accepted_input_unchanged": digest(published) == FROZEN_SHA256,
                   "scope": "bounded early-joiner prototype; containment is distinct from graceful peer-failure recovery"}
        write_json(result_dir / "receipt.json", receipt)
        print(json.dumps({"probe": name, "passed": receipt["passed"], "deadline_reached": timed_out,
                          "natural_exits": natural, "forced": forced}), flush=True)
        return receipt

    results = [trial("normal"), trial("early-observer-delay-500ms", observer_delay=.5),
               trial("missing-body-update", fault="missing-update"),
               trial("publisher-interrupted-tick256", fault="peer-interrupt", interrupt="publisher"),
               trial("observer-interrupted-tick256", fault="peer-interrupt", interrupt="observer")]

    # Exercise the observer's existing-output refusal on an exact accepted-data copy.
    guard_dir = scratch / "existing-output"
    guard_dir.mkdir()
    guarded = guard_dir / "accepted-copy.sf"
    shutil.copyfile(published, guarded)
    before = digest(guarded)
    guard = subprocess.run([str(adapter / "spacefom-observer.exe"), str(guarded),
                            "rti://127.0.0.1:1", "must_not_join"], env=environment,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    raw_guard = guard.stdout + b"\n--- stderr ---\n" + guard.stderr
    (guard_dir / "guard.raw.log").write_bytes(raw_guard)
    cleaned = redact(raw_guard.decode(errors="replace"), replacements).encode()
    (evidence / "existing-output.log").write_bytes(cleaned)
    guard_result = {"passed": guard.returncode == 1 and digest(guarded) == before
                   and b"refusing existing output" in guard.stderr,
                   "exit": guard.returncode, "sha256_before": before, "sha256_after": digest(guarded),
                   "original_log_sha256": hashlib.sha256(raw_guard).hexdigest(),
                   "redacted_log_sha256": hashlib.sha256(cleaned).hexdigest()}
    write_json(evidence / "existing-output.json", guard_result)
    changed = [p.relative_to(repo).as_posix() for p, h in baseline.items() if digest(p) != h]
    summary = {"schema": "wire-qualification-v1", "oracle_gates": checks["count"],
               "passed": all(item["passed"] for item in results) and guard_result["passed"] and not changed,
               "pass_scope": "exact exchange plus incomplete-output containment only",
               "general_failure_recovery_qualified": False,
               "deadline_cleanup_cases": [item["name"] for item in results if item["deadline_reached"]],
               "probe_results": [{"name": item["name"], "passed": item["passed"],
                                   "deadline_reached": item["deadline_reached"]} for item in results],
               "existing_output_guard": guard_result["passed"], "changed_accepted_files": changed,
               "limitations": ["separately implemented oracle, not blind authorship",
                               "related federates on one Windows x64 runtime",
                               "incomplete-output containment is not graceful peer-failure recovery",
                               "no physical accuracy, full compliance or source-hash authentication claim"]}
    write_json(evidence / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
