#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tool_image=rustbox-iproute2:2026-11-24
case "${1-}" in
    '') set -- ;;
    --kernel-events) test "$#" -eq 1; set -- --cap-add NET_ADMIN -e RUSTBOX_KERNEL_EVENTS=1 ;;
    --multicall) test "$#" -eq 1; tool_image=rustbox-e2fsprogs:2026-11-24
        set -- --cap-add NET_ADMIN -e RUSTBOX_FDB_MULTICALL=1 \
        -v rustbox-coreutils-9.12:/rustbox-coreutils:ro ;;
    *) echo "usage: $0 [--kernel-events | --multicall]" >&2; exit 2 ;;
esac
exec docker run --rm -i --network none "$@" --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-iproute2-7.3.0:/rustbox-iproute2:ro \
    --workdir /tmp "$tool_image" sh -eu <<'PILOT'
export LC_ALL=C TZ=UTC
if [ "${RUSTBOX_FDB_MULTICALL:-0}" = 1 ]; then
    binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    ln -s "$binary" bridge
    PYTHONPATH=/work/tests/iproute2-rtattr python3 -B -c \
        'import monitor, sys; monitor.check_nested([sys.argv[1], "bridge"])' "$binary"
    python3 /work/tests/iproute2-rtattr/kernel_monitor.py
    exit 0
fi
src=/work/work/upstream/iproute2-7.3.0
base=/work/work/analysis/iproute2-7.3.0
cd "$src"
sha256sum -c <<'HASHES'
b7bcc45da00500068db4bba3391d6ec54b0c5282f71f78cb308cc050b8f5da27  lib/libnetlink.c
1ad489115675ce059c7b5dacbb99c5f8ad65aaf11fdd00f0e1f9dda393b7c22a  include/uapi/linux/rtnetlink.h
HASHES
cd /tmp
rustc --edition=2021 --test /work/compat/iproute2/monitor_buffer.rs -o check-monitor-bound
./check-monitor-bound
python3 - "$base/oracle/gcc-compile-commands.json" "$src" <<'PY'
import json, subprocess, sys
from pathlib import Path
record, = (x for x in json.load(open(sys.argv[1])) if x["file"].endswith("/libnetlink.c"))
args = record["arguments"].copy()
args[args.index("-o") + 1] = "/tmp/oracle.o"
args += ["-ffunction-sections", "-fdata-sections"]
subprocess.run(args, cwd=Path(sys.argv[2])/"lib", check=True)
PY
rustc --edition=2021 --crate-type=lib --emit=obj -C opt-level=s -C panic=abort \
    /work/compat/iproute2/rtattr_abi.rs -o candidate.o
for variant in oracle candidate; do
    gcc -Wall -Wextra -Werror -D_GNU_SOURCE -I"$src/include" -I"$src/include/uapi" \
        -O2 /work/tests/iproute2-rtattr/compare.c "$variant.o" -Wl,--gc-sections -o compare
    valgrind --tool=memcheck --error-exitcode=88 --log-file="$variant.memcheck" \
        ./compare > "$variant.out" 2> "$variant.err" || { cat "$variant.memcheck"; exit 1; }
done
cmp oracle.out candidate.out
cmp oracle.err candidate.err
tail -1 candidate.out

crates=$base/program-translations
python3 /work/scripts/build_iproute2_bridge.py "$crates/cargo-target" engine.a --pilot
clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_bridge_main \
    /work/bridges/iproute2_program_main.c engine.a candidate.o \
    -ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm -o bridge

# Both variants use the same socket harness, with their own listener and printer.
oracle_dir=/rustbox-iproute2/oracle-gcc
gcc -Wall -Wextra -Werror -D_GNU_SOURCE -I"$src/include" -I"$src/include/uapi" \
    -c /work/tests/iproute2-rtattr/live.c -o harness.o
objcopy --redefine-sym main=oracle_bridge_main "$oracle_dir/bridge/bridge.o" oracle-bridge.o
set -- oracle-bridge.o
for obj in fdb monitor link mdb mst vlan vni; do set -- "$@" "$oracle_dir/bridge/$obj.o"; done
gcc harness.o "$@" -Wl,--start-group "$oracle_dir/lib/libutil.a" "$oracle_dir/lib/libnetlink.a" \
    -Wl,--end-group -ltirpc -lbpf -lelf -lmnl -lcap -lm -o live-oracle
clang-18 -Wl,--gc-sections harness.o engine.a candidate.o \
    -ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm -o live-candidate
clang-18 -Wall -Wextra -Werror -Wl,--gc-sections /work/tests/iproute2-rtattr/heap_receive.c \
    engine.a candidate.o -ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm \
    -o heap-receive
python3 /work/tests/iproute2-rtattr/monitor.py
for symbol in rtnl_listen print_fdb parse_rtattr_flags; do
    grep -Eq "^(c?fn)=.*${symbol}$" live.trace
done
/rustbox-iproute2/programs-gcc/bridge monitor file fdb.dump > oracle.stdout 2> oracle.stderr
./bridge monitor file fdb.dump > candidate.stdout 2> candidate.stderr
cmp oracle.stdout candidate.stdout
cmp oracle.stderr candidate.stderr
test "$(grep -c 'vlan 42' candidate.stdout)" -eq 3
for binary in /rustbox-iproute2/programs-gcc/bridge ./bridge; do
    status=0
    "$binary" monitor file oversize.dump > limit.out 2> limit.err || status=$?
    test "$status" -ne 0
    if [ "$binary" = ./bridge ]; then
        test "$status" -eq "$oracle_status"
        cmp limit.out oracle-limit.out
        cmp limit.err oracle-limit.err
    else
        oracle_status=$status
        mv limit.out oracle-limit.out
        mv limit.err oracle-limit.err
    fi
done
valgrind --tool=memcheck --error-exitcode=88 --log-file=replay.memcheck \
    ./bridge monitor file fdb.dump > checked.stdout || { cat replay.memcheck; exit 1; }
cmp checked.stdout candidate.stdout
valgrind --tool=callgrind --callgrind-out-file=trace --log-file=valgrind.log \
    ./bridge monitor file fdb.dump > /dev/null
grep -Eq '^(c?fn)=.*parse_rtattr_flags$' trace
echo 'bridge replay matched and called the replacement'
if [ "${RUSTBOX_KERNEL_EVENTS:-0}" = 1 ]; then
    python3 /work/tests/iproute2-rtattr/kernel_monitor.py
fi
PILOT
