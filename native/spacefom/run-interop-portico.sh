#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 3 ]; then
    echo "usage: run-interop-portico.sh <input.sf> <new-evidence-dir> <portico-home> [port]" >&2
    exit 2
fi

input=$(realpath "$1")
evidence=$2
portico_home=$(realpath "$3")
port=${4:-31416}
repo=$(realpath "$(dirname "$0")/../..")
fom=$(realpath "$(dirname "$0")/../../fom")
portico_commit=${PORTICO_COMMIT:-unknown}

if [ -e "$evidence" ]; then echo "refusing an existing evidence directory" >&2; exit 1; fi
if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then echo "invalid port" >&2; exit 1; fi
if [ ! -f "$portico_home/lib/portico.jar" ]; then echo "portico-home is not a Portico installation" >&2; exit 1; fi
if [ -z "${JAVA_HOME:-}" ] || [ ! -f "$JAVA_HOME/lib/server/libjvm.so" ]; then
    echo "JAVA_HOME must identify a JVM with lib/server/libjvm.so" >&2
    exit 1
fi

mkdir -p "$evidence"
evidence=$(realpath "$evidence")
mkdir -p "$evidence/publisher-work" "$evidence/observer-work"
tmp=$(mktemp -d)
shim="$tmp/shim"
adapter_build="$tmp/adapter-build"
adapter_src="$repo/native/spacefom"
federation="orbital_$port"
url="rti://127.0.0.1:$port"
pids=()

cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    if [ -n "${tmp:-}" ] && [ -d "$tmp" ]; then rm -rf -- "$tmp"; fi
}
trap cleanup EXIT

mkdir -p "$shim/include/rti1516e" "$shim/lib"
cp -a "$portico_home/include/ieee1516e/." "$shim/include/rti1516e/"
find "$shim/include/rti1516e" -type f \( -name '*.h' -o -name '*.hpp' \) \
    -exec perl -0777 -pi -e 's/\bthrow\s*\(\s*(?=\S)[^)]*\)//gs' {} +
if ! find "$shim/include/rti1516e" -type f \( -name '*.h' -o -name '*.hpp' \) -print0 |
    xargs -0 perl -0777 -ne 'exit 1 if /\bthrow\s*\(\s*\S/'; then
    echo "non-empty dynamic exception specification remains in copied headers" >&2
    exit 1
fi
ln -s "$portico_home/lib/gcc11/librti1516e64.so" "$shim/lib/rti1516e.lib"
ln -s "$portico_home/lib/gcc11/libfedtime1516e64.so" "$shim/lib/fedtime1516e.lib"

cat >"$evidence/RTI.rid" <<'EOF'
portico.logdir = logs
portico.loglevel = INFO
portico.container.loglevel = WARN
portico.jgroups.udp.bindAddress = LOOPBACK
EOF

if ! CXXFLAGS="${CXXFLAGS:+$CXXFLAGS }-Wno-deprecated-declarations" \
    cmake -S "$adapter_src" -B "$adapter_build" -DCMAKE_BUILD_TYPE=Release \
        -DOPENRTI_ROOT="$shim" \
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$JAVA_HOME/lib/server" \
        >"$evidence/configure.log" 2>&1; then
    echo "adapter CMake configure failed; see configure.log" >&2
    exit 1
fi
if ! cmake --build "$adapter_build" --parallel >"$evidence/build.log" 2>&1; then
    echo "adapter build failed; see build.log" >&2
    exit 1
fi

export RTI_HOME="$portico_home"
export RTI_RID_FILE="$evidence/RTI.rid"
export LD_LIBRARY_PATH="$portico_home/lib/gcc11:$JAVA_HOME/lib/server${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

(cd "$evidence/publisher-work" && "$adapter_build/spacefom-publisher" \
    "$input" "$fom" "$url" "$federation") >"$evidence/publisher.log" 2>"$evidence/publisher.err" &
publisher=$!
pids+=("$publisher")

# Portico assigns channel handles only while answering find-coordinator requests, and
# it ignores such requests until a manifest exists. Start the observer only after the
# publisher reports federation creation so the coordinator records the observer's
# channel handle before the join arrives.
federation_ready=false
for _ in $(seq 1 300); do
    if grep -q 'SUCCESS Created federation execution' "$evidence/publisher.log" 2>/dev/null; then
        federation_ready=true
        break
    fi
    kill -0 "$publisher" 2>/dev/null || break
    sleep 0.2
done

(cd "$evidence/observer-work" && "$adapter_build/spacefom-observer" \
    "$evidence/observed.sf" "$url" "$federation") >"$evidence/observer.log" 2>"$evidence/observer.err" &
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

cat >"$evidence/receipt.json" <<EOF
{
  "rti": "Portico IEEE 1516-2010",
  "rti_version": "2.2.0",
  "rti_commit": "$portico_commit",
  "platform": "$(uname -s) $(uname -m)",
  "transport": "JGroups UDP multicast bound to LOOPBACK; no rtinode",
  "url_argument_ignored_by_portico": "$url",
  "federation": "$federation",
  "publisher_exit": $publisher_exit,
  "observer_exit": $observer_exit,
  "timed_out": $timed_out,
  "published_sha256": "$published_sha",
  "observed_sha256": $([ "$observed_sha" = null ] && echo null || printf '"%s"' "$observed_sha"),
  "byte_identity": $byte_identity,
  "observer_freeze_seen": $freeze_seen,
  "observer_resume_seen": $resume_seen,
  "input_bytes": $(stat -c %s "$input")
}
EOF

if [ "$publisher_exit" -ne 0 ] || [ "$observer_exit" -ne 0 ] ||
    [ "$timed_out" = true ] || [ "$byte_identity" != true ]; then
    echo "federate failed: publisher=$publisher_exit, observer=$observer_exit, timed_out=$timed_out, byte_identity=$byte_identity" >&2
    exit 1
fi
cat "$evidence/receipt.json"
