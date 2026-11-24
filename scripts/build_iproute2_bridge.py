#!/usr/bin/env python3
"""Build the Rustbox bridge archive from the pinned, finalized IPRoute2 translation."""
# SPDX-License-Identifier: GPL-2.0-or-later

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POINTER = re.compile(rb"\*(?:mut|const)\b")
PINNED = {
    "src/lib/libnetlink.rs": "0d659c3db5057da08bdb4b530222fba2597454ca0bc240ce7dbf3558ee40fb8b",
    "src/bridge/fdb.rs": "7bff7bf55b1f70ead9d3ce82026db11a5380fcdd7471ef4369b0d37a133c3461",
}


def stage(engine, pilot):
    for relative, expected in PINNED.items():
        if hashlib.sha256((engine / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"IPRoute2 bridge translation changed: {relative}")
    for name in ("monitor_buffer.rs", "rtattr.rs", "fdb_activity.rs"):
        shutil.copyfile(REPO / "compat/iproute2" / name, engine / name)
    path = engine / 'src/lib/libnetlink.rs'
    s = path.read_text()
    if pilot:
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
    if pilot:
        reader = '#[export_name = "rustbox_pilot_recvmsg"]\n' + reader
    s = s[:start] + reader + s[end:]
    path.write_text(s)
    # The parent was accepted by the outer walker. Its child stream starts on
    # the same four-byte grid and cannot round beyond the parent's aligned end.
    fdb = engine / 'src/bridge/fdb.rs'
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
    with (engine / 'lib.rs').open('a') as root:
        root.write('\nmod monitor_buffer;\nmod rtattr;\nmod fdb_activity;\n')


def count_raw_types(engine):
    return sum(len(POINTER.findall(path.read_bytes())) for path in engine.rglob("*.rs"))


def build_bridge(target, output, *, pilot=False, prune_inlines=False):
    source = target.parent / "bridge/bridge-final"
    deps = target / "bridge/release/deps"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        engine = Path(scratch) / "engine"
        shutil.copytree(source, engine, ignore=shutil.ignore_patterns("target"))
        before = count_raw_types(engine)
        stage(engine, pilot)
        after = count_raw_types(engine)
        arguments = ["rustc", "--edition=2021", "--crate-type=staticlib",
                     "--crate-name", "bridge_audit", "-C", "opt-level=3", "--cap-lints=allow",
                     "--remap-path-prefix", f"{scratch}=/rustbox-bridge", "-L", f"dependency={deps}"]
        for dependency in ("c2rust_asm_casts", "f128"):
            library, = deps.glob(f"lib{dependency}-*.rlib")
            arguments.extend(["--extern", f"{dependency}={library}"])
        # Publish only after rustc finishes; concurrent builds use private output files.
        with tempfile.TemporaryDirectory(dir=output.parent) as staging:
            archive = Path(staging) / output.name
            deps_file = Path(staging) / "compiler.d"
            subprocess.run([*arguments, f"--emit=link,dep-info={deps_file}", "lib.rs",
                            "-o", str(archive)], cwd=engine, check=True)
            rule = deps_file.read_text().splitlines()[0].split(": ", 1)[1]
            inputs = sorted({name for name in shlex.split(rule) if name.endswith(".rs")})
            manifest = {
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "sources": {name: hashlib.sha256((engine / name).read_bytes()).hexdigest()
                            for name in inputs},
            }
            cleanup = None
            if prune_inlines:
                from prune_private_inlines import prune_identical
                plan = prune_identical(engine, arguments, archive, deps_file)
                trimmed_rule = deps_file.read_text().splitlines()[0].split(": ", 1)[1]
                trimmed_inputs = {name for name in shlex.split(trimmed_rule) if name.endswith(".rs")}
                if trimmed_inputs != set(inputs) or not set(plan) <= trimmed_inputs:
                    raise ValueError("bridge compiler inputs changed during private-inline cleanup")
                proof = {"archive_sha256": manifest["archive_sha256"], "ranges": plan,
                         "sources": {n: hashlib.sha256((engine / n).read_bytes()).hexdigest() for n in plan}}
                data = (json.dumps(proof, sort_keys=True, separators=(",", ":")) + "\n").encode()
                digest = hashlib.sha256(data).hexdigest()
                filename = archive.with_suffix(f".inlines-{digest}.json").name
                candidate = Path(staging) / filename
                candidate.write_bytes(data)
                candidate.replace(output.with_name(filename))
                cleanup = {"file": filename, "sha256": digest}
                after = count_raw_types(engine)
            sidecar = archive.with_suffix(".sources.json")
            sidecar.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            sidecar.replace(output.with_suffix(".sources.json"))
            archive.replace(output)
    return {"before": before, "after": after, **({"inline_proof": cleanup} if cleanup else {})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--prune-inlines", action="store_true")
    args = parser.parse_args()
    print(build_bridge(args.target.resolve(), args.output.resolve(), pilot=args.pilot, prune_inlines=args.prune_inlines))
