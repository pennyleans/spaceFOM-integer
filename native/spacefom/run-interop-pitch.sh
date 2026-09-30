#!/usr/bin/env bash
# Pitch pRTI counterpart of run-interop.sh: headless central RTI, publisher and observer
# on loopback, then a byte comparison. Built for the Pitch pRTI Free edition.
set -euo pipefail

if [ $# -lt 3 ]; then
    echo "usage: run-interop-pitch.sh <input.sf> <new-evidence-dir> <pitch-home> [crc-host] [crc-port]" >&2
    exit 2
fi

input=$(realpath "$1")
evidence=$2
pitch_home=$(realpath "$3")
crc_host=${4:-localhost}
crc_port=${5:-8989}
repo=$(realpath "$(dirname "$0")/../..")
fom=$(realpath "$(dirname "$0")/../../fom")
pitch_version=$(head -c 64 "$pitch_home/versioninfo.txt" 2>/dev/null | tr -d '\r\n')
installer_sha=${PITCH_SHA256:-unknown}

if [ -e "$evidence" ]; then echo "refusing an existing evidence directory" >&2; exit 1; fi
if [ ! -f "$pitch_home/lib/gcc73_64/librti1516e64.so" ]; then echo "pitch-home is not a pRTI installation" >&2; exit 1; fi
if [ ! -x "$pitch_home/bin/prti1516e-nogui.sh" ]; then echo "pitch-home has no headless RTI launcher" >&2; exit 1; fi

mkdir -p "$evidence"
evidence=$(realpath "$evidence")
mkdir -p "$evidence/publisher-work" "$evidence/observer-work"
tmp=$(mktemp -d)
shim="$tmp/shim"
adapter_build="$tmp/adapter-build"
adapter_src="$repo/native/spacefom"
federation="orbital_$crc_port"
designator=$(printf 'crcHost = %s\ncrcPort = %s' "$crc_host" "$crc_port")
crc_location=remote
if [ "$crc_host" = localhost ] || [ "$crc_host" = 127.0.0.1 ]; then crc_location=local; fi
pids=()

cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    if [ -n "${tmp:-}" ] && [ -d "$tmp" ]; then rm -rf -- "$tmp"; fi
}
trap cleanup EXIT

# The Pitch 1516-2010 headers map throw specifications to nothing under C++17
# through RTI_THROW, so the copy needs no edits.
mkdir -p "$shim/include/rti1516e" "$shim/lib"
cp -a "$pitch_home/api/cpp/HLA_1516-2010/." "$shim/include/rti1516e/"
ln -s "$pitch_home/lib/gcc73_64/librti1516e64.so" "$shim/lib/rti1516e.lib"
ln -s "$pitch_home/lib/gcc73_64/libfedtime1516e64.so" "$shim/lib/fedtime1516e.lib"

if ! CXXFLAGS="${CXXFLAGS:+$CXXFLAGS }-Wno-deprecated-declarations" \
    cmake -S "$adapter_src" -B "$adapter_build" -DCMAKE_BUILD_TYPE=Release \
        -DOPENRTI_ROOT="$shim" \
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$pitch_home/lib/gcc73_64" \
        >"$evidence/configure.log" 2>&1; then
    echo "adapter CMake configure failed; see configure.log" >&2
    exit 1
fi
if ! cmake --build "$adapter_build" --parallel >"$evidence/build.log" 2>&1; then
    echo "adapter build failed; see build.log" >&2
    exit 1
fi

export PRTI1516E_HOME="$pitch_home"
export PitchRTI_ROOT="$pitch_home"
export CLASSPATH="$pitch_home/lib/prti1516e.jar${CLASSPATH:+:$CLASSPATH}"
export LD_LIBRARY_PATH="$pitch_home/jre/lib/amd64:$pitch_home/jre/lib/amd64/server:$pitch_home/lib/gcc73_64:$pitch_home/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

crc_ready=false
if [ "$crc_location" = local ]; then
    "$pitch_home/bin/prti1516e-nogui.sh" >"$evidence/crc.log" 2>&1 &
    crc=$!
    pids+=("$crc")
    for _ in $(seq 1 300); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$crc_port") 2>/dev/null; then crc_ready=true; break; fi
        kill -0 "$crc" 2>/dev/null || break
        sleep 0.2
    done
else
    for _ in $(seq 1 30); do
        if timeout 3 bash -c "exec 3<>/dev/tcp/$crc_host/$crc_port" 2>/dev/null; then
            crc_ready=true
            break
        fi
    done
fi
if [ "$crc_ready" != true ]; then
    echo "pRTI central component is not reachable at $crc_host:$crc_port" >&2
    exit 1
fi

(cd "$evidence/publisher-work" && "$adapter_build/spacefom-publisher" \
    "$input" "$fom" "$designator" "$federation" ${PUBLISHER_OPTIONS:-}) >"$evidence/publisher.log" 2>"$evidence/publisher.err" &
publisher=$!
pids+=("$publisher")
(cd "$evidence/observer-work" && "$adapter_build/spacefom-observer" \
    "$evidence/observed.sf" "$designator" "$federation") >"$evidence/observer.log" 2>"$evidence/observer.err" &
observer=$!
pids+=("$observer")

timed_out=false
deadline=$((SECONDS + 120))
while kill -0 "$publisher" 2>/dev/null || kill -0 "$observer" 2>/dev/null; do
    if [ "$SECONDS" -gt "$deadline" ]; then
        timed_out=true
        kill "$publisher" "$observer" 2>/dev/null || true
        break
    fi
    sleep 0.1
done

publisher_exit=0
wait "$publisher" || publisher_exit=$?
observer_exit=0
wait "$observer" || observer_exit=$?
pids=()

published_sha=$(sha256sum "$input" | cut -d' ' -f1)
observed_sha=null
byte_identity=false
if [ -f "$evidence/observed.sf" ]; then
    observed_sha=$(sha256sum "$evidence/observed.sf" | cut -d' ' -f1)
    if [ "$published_sha" = "$observed_sha" ]; then byte_identity=true; fi
fi
freeze_seen=false
resume_seen=false
if grep -q '^freeze ' "$evidence/observer.log"; then freeze_seen=true; fi
if [ "$(grep -c '^run ' "$evidence/observer.log" || true)" -ge 2 ]; then resume_seen=true; fi
# With --save-restore: frames received again after the restore that matched the first pass, and the saved states.
rematerialized=$(grep -o 'rematerialized_identical frames=[0-9]*' "$evidence/observer.log" | cut -d= -f2 || true)
(cd "$evidence" && find publisher-work observer-work -name '*.state' -exec sha256sum {} +) >"$evidence/saved-states.sha256" || true

cat >"$evidence/receipt.json" <<EOF
{
  "rti": "Pitch pRTI IEEE 1516-2010",
  "rti_version": "$pitch_version",
  "rti_edition": "Free (two federates)",
  "rti_installer_sha256": "$installer_sha",
  "platform": "$(uname -s) $(uname -m)",
  "transport": "TCP from the WSL federates to the pRTI central component ($crc_location)",
  "crc_host": "$crc_host",
  "crc_port": $crc_port,
  "local_settings": "crcHost = $crc_host; crcPort = $crc_port",
  "federation": "$federation",
  "publisher_exit": $publisher_exit,
  "observer_exit": $observer_exit,
  "timed_out": $timed_out,
  "published_sha256": "$published_sha",
  "observed_sha256": $([ "$observed_sha" = null ] && echo null || printf '"%s"' "$observed_sha"),
  "byte_identity": $byte_identity,
  "observer_freeze_seen": $freeze_seen,
  "observer_resume_seen": $resume_seen,
  "publisher_options": "${PUBLISHER_OPTIONS:-}",
  "rematerialized_frames": ${rematerialized:-0},
  "input_bytes": $(stat -c %s "$input")
}
EOF

if [ "$publisher_exit" -ne 0 ] || [ "$observer_exit" -ne 0 ] ||
    [ "$timed_out" = true ] || [ "$byte_identity" != true ]; then
    echo "federate failed: publisher=$publisher_exit, observer=$observer_exit, timed_out=$timed_out, byte_identity=$byte_identity" >&2
    exit 1
fi
cat "$evidence/receipt.json"
