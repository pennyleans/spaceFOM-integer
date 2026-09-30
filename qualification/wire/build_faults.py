"""Build an isolated, explicitly injected publisher without editing the adapter."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redact(text, replacements):
    for path, label in sorted(replacements, key=lambda pair: len(str(pair[0])), reverse=True):
        for spelling in (str(path), str(path).replace("\\", "/")):
            text = text.replace(spelling, label)
    return re.sub(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])[^\r\n\"]+", "<absolute-path>", text)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--rti-sdk", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    scratch, evidence, sdk = args.scratch.resolve(), args.evidence.resolve(), args.rti_sdk.resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    source = scratch / "injected"
    source.mkdir()
    manifest = []
    for name in ("publisher.cpp", "observer.cpp", "transport.hpp", "CMakeLists.txt"):
        accepted = repo / "native/spacefom" / name
        (source / name).write_bytes(accepted.read_bytes())
        manifest.append({"path": "native/spacefom/" + name, "sha256": digest(accepted)})
    publisher = source / "publisher.cpp"
    accepted_text = publisher.read_text()
    modified = accepted_text.replace('#include "transport.hpp"', '#include "transport.hpp"\n#include <cstdlib>', 1)
    anchor = '        require(argc==5,"usage: spacefom-publisher input.spool fom-directory rti://127.0.0.1:port federation");'
    replacement = anchor + '''
        // Qualification-only fault selection in this isolated copy.
        char* injected = nullptr; size_t injectedLength = 0;
        require(_dupenv_s(&injected,&injectedLength,"SF_QUAL_FAULT")==0,"qualification environment read failed");
        const std::string qualificationFault = injected ? injected : "";
        std::free(injected);'''
    if modified.count(anchor) != 1:
        raise RuntimeError("fault selector anchor changed")
    modified = modified.replace(anchor, replacement, 1)
    anchor = '            for(size_t j=0;j<=bodies.size();++j) {'
    replacement = anchor + '''
                // Qualification-only loss of one declared body sample at tick 128.
                if(qualificationFault=="missing-update" && index==128 && j==1) {
                    session.log("qualification_omitted_body_sample tick=128 body_index=0");
                    continue;
                }'''
    if modified.count(anchor) != 1:
        raise RuntimeError("missing update anchor changed")
    modified = modified.replace(anchor, replacement, 1)
    anchor = '            publishFrame(i,true); session.advance(static_cast<int64_t>(i)*stepUs);'
    replacement = anchor + '''
            // Qualification-only rendezvous so the harness interrupts a known in-flight tick.
            if(qualificationFault=="peer-interrupt" && i==256) {
                session.log("qualification_interrupt_ready tick=256");
                std::this_thread::sleep_for(std::chrono::seconds(20));
            }'''
    if modified.count(anchor) != 1:
        raise RuntimeError("interrupt anchor changed")
    modified = modified.replace(anchor, replacement, 1)
    publisher.write_text(modified, encoding="utf-8", newline="\n")
    patch = "".join(difflib.unified_diff(accepted_text.splitlines(True), modified.splitlines(True),
                                       "accepted/publisher.cpp", "injected/publisher.cpp"))
    (evidence / "publisher-fault.patch").write_text(patch, encoding="utf-8", newline="\n")
    replacements = [(repo, "$REPO"), (scratch, "$SCRATCH"), (sdk, "$RTI_SDK")]
    log_receipts = []
    commands = [
        ["cmake", "-S", str(source), "-B", str(scratch / "build"), "-G", "Visual Studio 17 2022",
         "-A", "x64", "-DOPENRTI_ROOT=" + str(sdk)],
        ["cmake", "--build", str(scratch / "build"), "--config", "Release", "--parallel", "2",
         "--target", "spacefom-publisher"],
    ]
    for i, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        raw = result.stdout + b"\n--- stderr ---\n" + result.stderr
        (scratch / f"build-{i}.raw.log").write_bytes(raw)
        clean = redact(raw.decode("utf-8", errors="replace"), replacements).encode()
        (evidence / f"build-{i}.log").write_bytes(clean)
        log_receipts.append({"file": f"build-{i}.log", "original_sha256": hashlib.sha256(raw).hexdigest(),
                             "redacted_sha256": hashlib.sha256(clean).hexdigest(), "exit": result.returncode,
                             "command": [redact(x, replacements) for x in command]})
        if result.returncode:
            write_json(evidence / "build.json", {"passed": False, "logs": log_receipts})
            raise RuntimeError("isolated fault publisher build failed")
    sdk_inputs = [*sorted((sdk / "include/rti1516e").rglob("*")),
                  sdk / "lib/rti1516e.lib", sdk / "lib/fedtime1516e.lib"]
    result = {"schema": "isolated-fault-build-v1", "passed": True,
              "accepted_sources": manifest,
              "injected_sources": [{"path": p.name, "sha256": digest(p)} for p in sorted(source.iterdir())],
              "patch_sha256": digest(evidence / "publisher-fault.patch"),
              "publisher_sha256": digest(scratch / "build/Release/spacefom-publisher.exe"),
              "sdk_inputs": [{"path": p.relative_to(sdk).as_posix(), "sha256": digest(p)}
                             for p in sdk_inputs if p.is_file()],
              "logs": log_receipts,
              "scope": "only fault-injected scratch publisher; accepted adapter not edited"}
    write_json(evidence / "build.json", result)
    print(json.dumps({"passed": True, "publisher_sha256": result["publisher_sha256"]}))


if __name__ == "__main__":
    main()
