#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
case "${1-}" in
    '') set -- ;;
    --kernel-events) test "$#" -eq 1; set -- --cap-add NET_ADMIN -e RUSTBOX_KERNEL_EVENTS=1 ;;
    *) echo "usage: $0 [--kernel-events]" >&2; exit 2 ;;
esac
exec docker run --rm -i --network none "$@" --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-iproute2-7.3.0:/rustbox-iproute2:ro \
    --workdir /tmp rustbox-iproute2:2026-11-24 sh -eu <<'PILOT'
export LC_ALL=C TZ=UTC
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
cp -R "$crates/bridge/bridge-final" engine
module=engine/src/lib/libnetlink.rs
printf '%s  %s\n' 0d659c3db5057da08bdb4b530222fba2597454ca0bc240ce7dbf3558ee40fb8b "$module" | sha256sum -c
cp /work/compat/iproute2/monitor_buffer.rs /work/compat/iproute2/rtattr.rs /work/compat/iproute2/fdb_activity.rs engine/
printf '%s  %s\n' 7bff7bf55b1f70ead9d3ce82026db11a5380fcdd7471ef4369b0d37a133c3461 engine/src/bridge/fdb.rs | sha256sum -c
python3 - "$module" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
s = path.read_text()
start = s.index('#[no_mangle]\npub unsafe extern "C" fn parse_rtattr_flags(')
end = s.index('#[no_mangle]\npub unsafe extern "C" fn parse_rtattr_one(', start)
decl = '''extern "C" {
    pub fn parse_rtattr_flags(tb: *mut *mut rtattr, max: i32, rta: *mut rtattr,
                              len: i32, flags: u16) -> i32;
}
'''
s = s[:start] + decl + s[end:]
for name, old_iov_base in [
    ('rtnl_from_file', '&raw mut buf as *mut ::core::ffi::c_void'),
    ('rtnl_listen', '&raw mut buf as *mut ::core::ffi::c_char as *mut ::core::ffi::c_void'),
]:
    start = s.index(f'pub unsafe extern "C" fn {name}(')
    end = s.index('#[no_mangle]', start)
    reader = s[start:end]
    changes = [
        ('let mut buf: [::core::ffi::c_char; 16384] = [0; 16384];',
         'let mut storage = crate::monitor_buffer::MonitorBuffer::new();\n'
         '    let buf = storage.as_mut_ptr();'),
        ('&raw mut buf as *mut ::core::ffi::c_char as *mut nlmsghdr', 'buf.cast::<nlmsghdr>()'),
        (old_iov_base, 'buf.cast::<::core::ffi::c_void>()'),
        ('::core::mem::size_of::<[::core::ffi::c_char; 16384]>() as usize',
         'crate::monitor_buffer::WIRE_LIMIT'),
    ]
    for old, new in changes:
        if reader.count(old) != 1:
            raise ValueError(f"unexpected {name} receive buffer for {old}")
        reader = reader.replace(old, new)
    s = s[:start] + reader + s[end:]

# The dumper and single-reply paths share this malloc/free owner. The first
# syscall sizes the allocation, and the second returns the copied byte count.
start = s.index('unsafe extern "C" fn rtnl_recvmsg(')
end = s.index('unsafe extern "C" fn rtnl_dump_filter_l(', start)
reader = s[start:end]
for old, new in [
    ('malloc(len as size_t)',
     'malloc((len as usize + crate::monitor_buffer::diagnostic_tail(len as usize)) as size_t)'),
    ('    if !answer.is_null() {',
     '    let used = len as usize;\n'
     '    buf.add(used).write_bytes(0, crate::monitor_buffer::diagnostic_tail(used));\n'
     '    if !answer.is_null() {'),
]:
    if reader.count(old) != 1:
        raise ValueError(f'unexpected heap receiver for {old}')
    reader = reader.replace(old, new)
# Expose the private receiver only in the disposable test engine. This allows
# Memcheck to inspect the initialized suffix after a real recvmsg call.
s = s[:start] + '#[export_name = "rustbox_pilot_recvmsg"]\n' + reader + s[end:]
path.write_text(s)
# The parent was accepted by the outer walker. Its child stream starts on
# the same four-byte grid and cannot round beyond the parent's aligned end.
fdb = Path('engine/src/bridge/fdb.rs')
source = fdb.read_text()
start = source.index('    let mut tb:', source.index('unsafe extern "C" fn fdb_print_ext_attrs('))
end = source.index('        if notify as', start)
source = source[:start] + '''    let payload_len = (*nfea).rta_len - 4;
    let len = usize::from(payload_len);
    let bytes = ::core::slice::from_raw_parts(nfea.add(1).cast::<u8>(),
        len + crate::monitor_buffer::diagnostic_tail(len));
    let (notify, diagnostic) = crate::fdb_activity::decode(bytes, payload_len);
    if let Some((remaining, length)) = diagnostic {
        fprintf(stderr, c"!!!Deficit %d, rta_len=%d\\n".as_ptr(), remaining, i32::from(length));
    }
    if notify != 0 {
''' + source[end:]
fdb.write_text(source)
with Path('engine/lib.rs').open('a') as root:
    root.write('\nmod monitor_buffer;\nmod rtattr;\nmod fdb_activity;\n')
PY
deps=$crates/cargo-target/bridge/release/deps
set -- "$deps"/libc2rust_asm_casts-*.rlib "$deps"/libf128-*.rlib
test "$#" -eq 2
rustc --edition=2021 --crate-type=staticlib --crate-name bridge_audit -C opt-level=3 \
    --cap-lints=allow -L "dependency=$deps" --extern "c2rust_asm_casts=$1" --extern "f128=$2" \
    engine/lib.rs -o engine.a
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
