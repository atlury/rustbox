#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm -i --network none --platform linux/amd64 \
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
rustc --edition=2021 --test /work/compat/iproute2/replay_buffer.rs -o check-replay-bound
./check-replay-bound
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
cp /work/compat/iproute2/replay_buffer.rs /work/compat/iproute2/rtattr.rs engine/
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
start = s.index('pub unsafe extern "C" fn rtnl_from_file(')
end = s.index('#[no_mangle]', start)
reader = s[start:end]
changes = [
    ('let mut buf: [::core::ffi::c_char; 16384] = [0; 16384];',
     'let mut storage = crate::replay_buffer::ReplayBuffer::new();\n'
     '    let buf = storage.as_mut_ptr();'),
    ('&raw mut buf as *mut ::core::ffi::c_char as *mut nlmsghdr', 'buf.cast::<nlmsghdr>()'),
    ('&raw mut buf as *mut ::core::ffi::c_void', 'buf.cast::<::core::ffi::c_void>()'),
    ('::core::mem::size_of::<[::core::ffi::c_char; 16384]>() as usize',
     'crate::replay_buffer::WIRE_LIMIT'),
]
for old, new in changes:
    if reader.count(old) != 1:
        raise ValueError(f"unexpected replay reader for {old}")
    reader = reader.replace(old, new)
path.write_text(s[:start] + reader + s[end:])
with Path('engine/lib.rs').open('a') as root:
    root.write('\nmod replay_buffer;\n')
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

# Replay a valid saved bridge FDB update, offline. Duplicate VLAN attributes
# exercise first-match selection after NLA_F_NESTED has been masked.
python3 - <<'PY'
from struct import pack
from pathlib import Path
def attr(kind, payload):
    size = 4 + len(payload)
    return pack("=HH", size, kind) + payload + bytes(-size % 4)
ndmsg = pack("=BBHiHBB", 7, 0, 0, 0, 0x80, 0, 0)
attrs = attr(0x8005, pack("=H", 42)) + attr(5, pack("=H", 99))
def record(extra=b''):
    body = ndmsg + attrs + extra
    return pack("=IHHII", 16 + len(body), 28, 0, 0, 0) + body
small = record()
def padded(size):
    # Unknown, well-formed attribute ignored by the FDB printer.
    result = record(attr(0x3fff, bytes(size - len(small) - 4)))
    assert len(result) == size
    return result
Path("fdb.dump").write_bytes(small + padded(16384) + small)
Path("oversize.dump").write_bytes(padded(16388))
PY
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
PILOT
