#!/usr/bin/env bash
# Pitch pRTI counterpart of run-latejoin.sh: starts our publisher and observer against
# the Pitch central component, then starts the late-join probe once the exchange is
# running, and checks the observer's recording.
set -euo pipefail
if [ $# -lt 4 ]; then
    echo "usage: run-latejoin-pitch.sh <input.sf> <new-evidence-dir> <pitch-home> <crc-host> [crc-port]" >&2
    exit 2
fi
input=$(realpath "$1")
evidence=$2
pitch_home=$(realpath "$3")
crc_host=$4
crc_port=${5:-8989}
repo=$(realpath "$(dirname "$0")/../..")
fom=$(realpath "$(dirname "$0")/../../fom")
pitch_version=$(head -c 64 "$pitch_home/versioninfo.txt" 2>/dev/null | tr -d '\r\n')
installer_sha=${PITCH_SHA256:-unknown}

if [ -e "$evidence" ]; then echo "refusing an existing evidence directory" >&2; exit 1; fi
if [ ! -f "$pitch_home/lib/gcc73_64/librti1516e64.so" ]; then echo "pitch-home is not a pRTI installation" >&2; exit 1; fi

mkdir -p "$evidence"
evidence=$(realpath "$evidence")
mkdir -p "$evidence/publisher-work" "$evidence/observer-work"
tmp=$(mktemp -d)
shim="$tmp/shim"
adapter_build="$tmp/adapter-build"
probe_build="$tmp/probe-build"
federation="orbital_$crc_port"
designator=$(printf 'crcHost = %s\ncrcPort = %s' "$crc_host" "$crc_port")
pids=()

cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    if [ -n "${tmp:-}" ] && [ -d "$tmp" ]; then rm -rf -- "$tmp"; fi
}
trap cleanup EXIT

mkdir -p "$shim/include/rti1516e" "$shim/lib"
cp -a "$pitch_home/api/cpp/HLA_1516-2010/." "$shim/include/rti1516e/"
ln -s "$pitch_home/lib/gcc73_64/librti1516e64.so" "$shim/lib/rti1516e.lib"
ln -s "$pitch_home/lib/gcc73_64/libfedtime1516e64.so" "$shim/lib/fedtime1516e.lib"

if ! CXXFLAGS="${CXXFLAGS:+$CXXFLAGS }-Wno-deprecated-declarations" \
    cmake -S "$repo/native/spacefom" -B "$adapter_build" -DCMAKE_BUILD_TYPE=Release \
        -DOPENRTI_ROOT="$shim" \
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$pitch_home/lib/gcc73_64" \
        >"$evidence/adapter-configure.log" 2>&1; then
    echo "adapter CMake configure failed; see adapter-configure.log" >&2
    exit 1
fi
if ! cmake --build "$adapter_build" --parallel >"$evidence/adapter-build.log" 2>&1; then
    echo "adapter build failed; see adapter-build.log" >&2
    exit 1
fi
if ! cmake -S "$repo/qualification/latejoin" -B "$probe_build" -DCMAKE_BUILD_TYPE=Release \
        -DOPENRTI_ROOT="$shim" \
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$pitch_home/lib/gcc73_64" \
        "-DCMAKE_CXX_FLAGS=-Wno-deprecated-declarations -Wno-error=deprecated-declarations" \
        >"$evidence/probe-configure.log" 2>&1; then
    echo "probe CMake configure failed; see probe-configure.log" >&2
    exit 1
fi
if ! cmake --build "$probe_build" --parallel >"$evidence/probe-build.log" 2>&1; then
    echo "probe build failed; see probe-build.log" >&2
    exit 1
fi

export PRTI1516E_HOME="$pitch_home"
export PitchRTI_ROOT="$pitch_home"
export CLASSPATH="$pitch_home/lib/prti1516e.jar${CLASSPATH:+:$CLASSPATH}"
export LD_LIBRARY_PATH="$pitch_home/jre/lib/amd64:$pitch_home/jre/lib/amd64/server:$pitch_home/lib/gcc73_64:$pitch_home/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

(cd "$evidence/publisher-work" && "$adapter_build/spacefom-publisher" \
    "$input" "$fom" "$designator" "$federation") >"$evidence/publisher.log" 2>"$evidence/publisher.err" &
publisher=$!
pids+=("$publisher")
(cd "$evidence/observer-work" && "$adapter_build/spacefom-observer" \
    "$evidence/observed.sf" "$designator" "$federation") >"$evidence/observer.log" 2>"$evidence/observer.err" &
observer=$!
pids+=("$observer")

deadline=$((SECONDS + 30))
until grep -q '^run ' "$evidence/publisher.log" 2>/dev/null; do
    if [ "$SECONDS" -gt "$deadline" ]; then echo "publisher never entered run mode" >&2; exit 1; fi
    kill -0 $publisher 2>/dev/null || { echo "publisher exited early" >&2; exit 1; }
    sleep 0.01
done

"$probe_build/spacefom-latejoin" "$designator" "$federation" >"$evidence/probe.log" 2>"$evidence/probe.err" &
late=$!
pids+=("$late")

deadline=$((SECONDS + 120))
while kill -0 "$publisher" 2>/dev/null || kill -0 "$observer" 2>/dev/null || kill -0 "$late" 2>/dev/null; do
    if [ "$SECONDS" -gt "$deadline" ]; then echo "federation exceeded 120 second bound" >&2; exit 1; fi
    sleep 0.1
done
p=0; wait "$publisher" || p=$?
o=0; wait "$observer" || o=$?
l=0; wait "$late" || l=$?
pids=()

published=$(sha256sum "$input" | cut -d' ' -f1)
observed=null
identity=false
if [ -f "$evidence/observed.sf" ]; then
    observed=$(sha256sum "$evidence/observed.sf" | cut -d' ' -f1)
    [ "$published" = "$observed" ] && identity=true
fi
late_result=$(tail -n 1 "$evidence/probe.log" | grep '^{' || echo null)

cat >"$evidence/receipt.json" <<JSON
{
  "check": "exchange with a third federate joining after initialization",
  "rti": "Pitch pRTI IEEE 1516-2010",
  "rti_version": "$pitch_version",
  "rti_edition": "Free (two federates)",
  "rti_installer_sha256": "$installer_sha",
  "platform": "$(uname -s) $(uname -m)",
  "transport": "TCP from the WSL federates to the pRTI central component",
  "crc_host": "$crc_host",
  "crc_port": $crc_port,
  "federation": "$federation",
  "publisher_exit": $p,
  "observer_exit": $o,
  "late_joiner_exit": $l,
  "published_sha256": "$published",
  "observed_sha256": $([ "$observed" = null ] && echo null || printf '"%s"' "$observed"),
  "byte_identity": $identity,
  "late_joiner_result": $late_result
}
JSON
cat "$evidence/receipt.json"
[ "$p" -eq 0 ] && [ "$o" -eq 0 ] && [ "$l" -eq 0 ] && [ "$identity" = true ]
