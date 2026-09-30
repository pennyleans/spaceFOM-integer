#!/usr/bin/env bash
# Runs the exchange with a third federate that joins after initialization, then checks the observer's recording.
set -euo pipefail
if [ $# -lt 4 ]; then
    echo "usage: run-latejoin.sh <input.sf> <new-evidence-dir> <transport-root> <probe-executable> [port]" >&2
    exit 2
fi
input=$(realpath "$1"); evidence=$2; transport=$(realpath "$3"); probe=$(realpath "$4"); port=${5:-31430}
fom=$(realpath "$(dirname "$0")/../../fom")
if [ -e "$evidence" ]; then echo "refusing an existing evidence directory" >&2; exit 1; fi
mkdir -p "$evidence"; evidence=$(realpath "$evidence")
url="rti://127.0.0.1:$port"; federation="orbital_$port"
export LD_LIBRARY_PATH="$transport/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
pids=(); cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }; trap cleanup EXIT
"$transport/runtime/bin/rtinode" -i "$url" >"$evidence/rti.log" 2>"$evidence/rti.err" & pids+=($!)
sleep 0.15
"$transport/adapter-build/spacefom-publisher" "$input" "$fom" "$url" "$federation" >"$evidence/publisher.log" 2>"$evidence/publisher.err" & publisher=$!; pids+=($publisher)
"$transport/adapter-build/spacefom-observer" "$evidence/observed.sf" "$url" "$federation" >"$evidence/observer.log" 2>"$evidence/observer.err" & observer=$!; pids+=($observer)
deadline=$((SECONDS + 30))
until grep -q "^run " "$evidence/publisher.log" 2>/dev/null; do
    if [ $SECONDS -gt $deadline ]; then echo "publisher never entered run mode" >&2; exit 1; fi
    sleep 0.01
done
"$probe" "$url" "$federation" >"$evidence/probe.log" 2>"$evidence/probe.err" & late=$!; pids+=($late)
deadline=$((SECONDS + 120))
while kill -0 "$publisher" 2>/dev/null || kill -0 "$observer" 2>/dev/null || kill -0 "$late" 2>/dev/null; do
    if [ $SECONDS -gt $deadline ]; then echo "federation exceeded 120 second bound" >&2; exit 1; fi
    sleep 0.1
done
p=0; wait "$publisher" || p=$?; o=0; wait "$observer" || o=$?; l=0; wait "$late" || l=$?
published=$(sha256sum "$input" | cut -d' ' -f1)
observed=$( [ -f "$evidence/observed.sf" ] && sha256sum "$evidence/observed.sf" | cut -d' ' -f1 || echo none)
identity=false; [ "$published" = "$observed" ] && identity=true
cat >"$evidence/receipt.json" <<JSON
{
  "check": "exchange with a third federate joining after initialization",
  "transport": "OpenRTI IEEE1516e TCP loopback",
  "platform": "$(uname -s) $(uname -m)",
  "publisher_exit": $p,
  "observer_exit": $o,
  "late_joiner_exit": $l,
  "published_sha256": "$published",
  "observed_sha256": "$observed",
  "byte_identity": $identity,
  "late_joiner_result": $(tail -n 1 "$evidence/probe.log" | grep '^{' || echo null)
}
JSON
cat "$evidence/receipt.json"
[ "$p" -eq 0 ] && [ "$o" -eq 0 ] && [ "$l" -eq 0 ] && [ "$identity" = true ]
