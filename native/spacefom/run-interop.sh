#!/usr/bin/env bash
# Linux counterpart of run-interop.ps1: RTI server, publisher and observer on loopback, then a byte comparison.
set -euo pipefail
if [ $# -lt 3 ]; then
    echo "usage: run-interop.sh <input.sf> <new-evidence-dir> <transport-root> [port]" >&2
    exit 2
fi
input=$(realpath "$1")
evidence=$2
transport=$(realpath "$3")
port=${4:-31416}
fom=$(realpath "$(dirname "$0")/../../fom")
if [ -e "$evidence" ]; then echo "refusing an existing evidence directory" >&2; exit 1; fi
if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then echo "invalid port" >&2; exit 1; fi
mkdir -p "$evidence"
evidence=$(realpath "$evidence")
url="rti://127.0.0.1:$port"
federation="orbital_$port"
export LD_LIBRARY_PATH="$transport/runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

"$transport/runtime/bin/rtinode" -i "$url" >"$evidence/rti.log" 2>"$evidence/rti.err" &
server=$!; pids+=("$server")
sleep 0.15
kill -0 "$server" 2>/dev/null || { echo "RTI server failed to start" >&2; exit 1; }
"$transport/adapter-build/spacefom-publisher" "$input" "$fom" "$url" "$federation" ${PUBLISHER_OPTIONS:-} >"$evidence/publisher.log" 2>"$evidence/publisher.err" &
publisher=$!; pids+=("$publisher")
"$transport/adapter-build/spacefom-observer" "$evidence/observed.sf" "$url" "$federation" >"$evidence/observer.log" 2>"$evidence/observer.err" &
observer=$!; pids+=("$observer")

deadline=$((SECONDS + 120))
while kill -0 "$publisher" 2>/dev/null || kill -0 "$observer" 2>/dev/null; do
    if [ $SECONDS -gt $deadline ]; then echo "federation exceeded 120 second bound" >&2; exit 1; fi
    sleep 0.1
done
publisher_exit=0; wait "$publisher" || publisher_exit=$?
observer_exit=0; wait "$observer" || observer_exit=$?
if [ "$publisher_exit" -ne 0 ] || [ "$observer_exit" -ne 0 ]; then
    echo "federate failed: publisher=$publisher_exit, observer=$observer_exit" >&2; exit 1
fi
published=$(sha256sum "$input" | cut -d' ' -f1)
observed=$(sha256sum "$evidence/observed.sf" | cut -d' ' -f1)
if [ "$published" != "$observed" ]; then echo "received spool bytes differ from published spool" >&2; exit 1; fi
cat >"$evidence/receipt.json" <<EOF
{
  "transport": "OpenRTI IEEE1516e TCP loopback",
  "platform": "$(uname -s) $(uname -m)",
  "url": "$url",
  "federation": "$federation",
  "publisher_exit": $publisher_exit,
  "observer_exit": $observer_exit,
  "published_sha256": "$published",
  "observed_sha256": "$observed",
  "byte_identity": true,
  "input_bytes": $(stat -c %s "$input"),
  "provenance": "transferred source hash is metadata, not receiver authority or authenticity proof",
  "scope": "bounded two-federate subset; no full SpaceFOM or RTI compliance claim"
}
EOF
cat "$evidence/receipt.json"
