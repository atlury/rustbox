#!/usr/bin/env python3
"""Replace Less's compiled default and symbol pointer tables with checked immutable byte ranges."""
# SPDX-License-Identifier: BSD-2-Clause OR GPL-3.0-or-later
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import re

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

SOURCE = ROOT / "work/upstream/less-710"
MODULE = "src/lmsg.rs"
HELPER = ROOT / "compat/less/message_catalog.rs"
MARKER = ".rustbox-less-messages"


def table(name, values):
    offsets = [0]
    for value in values:
        offsets.append(offsets[-1] + len(value))
    if offsets[-1] > 65535:
        raise ValueError("Less catalog offsets exceed u16")
    # Rust accepts ASCII hex escapes for every byte of a byte string.
    data = b"".join(values)
    lines = [", ".join(map(str, offsets[i:i+12])) + "," for i in range(0, len(offsets), 12)]
    literal = "".join(chr(b) if 32 <= b < 127 and b not in (34, 92) else f"\\x{b:02x}" for b in data)
    return (f'static {name}_BYTES: &[u8] = b"{literal}";\n'
            f'static {name}_OFFSETS: [u16; {len(offsets)}] = [\n    ' + "\n    ".join(lines) + "\n];\n").encode()


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    baseline = json.loads((ROOT / "evidence/less-message-catalog-baseline.json").read_bytes())
    if (MODULE not in sources or sha256(data).hexdigest() != "ae93f6e533568e6e4c916f5a621fb6d413de2c9136b7b7741a3eb6d08b351ef7"
            or any(digest(SOURCE / name) != pin for name, pin in baseline["canonical_sources"].items())):
        raise ValueError("Less message source or native C-string compiler selection differs")
    names, values = [], []
    for line in (SOURCE / "lessmsg.inc").read_text(encoding="ascii").splitlines():
        record = re.fullmatch(r'M\(([A-Za-z_]\w*),("(?:[^"\\]|\\.)*")\)', line)
        if record is None:
            raise ValueError("unrecognized canonical Less message declaration")
        names.append(record[1].encode())
        values.append(ast.literal_eval("b" + record[2]) + b"\0")
    if (len(names) != baseline["public_messages"] or len(set(names)) != len(names) or b"HELP" in names
            or any(b"\0" in value[:-1] for value in values)):
        raise ValueError("unexpected message ids or default contents")
    begin = data.index(b"static mut lmsgs:")
    end = data.index(b'#[no_mangle]\npub static mut help_data:', begin)
    generated = table("MESSAGE", values) + table("SYMBOL", [*names, b"HELP"]) + HELPER.read_bytes()
    result = data[:begin] + generated + data[end:]
    start = result.index(b'unsafe extern "C" fn lmsg_id(')
    end = result.index(b'unsafe extern "C" fn numeric_char(', start)
    result = result[:start] + b'''unsafe extern "C" fn lmsg_id(sym: *const ::core::ffi::c_char) -> lessmsg_id {
    messages::id(core::ffi::CStr::from_ptr(sym))
}
''' + result[end:]
    for old, new in (
        (b"lmsgs[id as usize] = msg;", b"messages::set(id, msg);"),
        (b"return lmsgs[id as usize];", b"return messages::get(id);"),
    ):
        if result.count(old) != 1:
            raise ValueError("Less catalog consumer changed")
        result = result.replace(old, new)
    first = result.index(b"    if id as ::core::ffi::c_uint <= 0", result.index(b'fn lmsg(mut id:'))
    last = result.index(b"    {\n", first)
    result = result[:first] + b"    if id == 0 || id as usize > messages::COUNT\n" + result[last:]
    if b"lmsg_syms" in result or b"lmsgs[" in result:
        raise ValueError("unconverted Less catalog consumer")
    return {MODULE: result}, dict(module=MODULE, default_messages=len(values), symbols=len(names)+1,
                                  helper_sha256=digest(HELPER), canonical_sources=baseline["canonical_sources"],
                                  control_module_sha256=sha256(data).hexdigest(), candidate_module_sha256=sha256(result).hexdigest(),
                                  raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(result)),
                                  pointer_extractions_removed=data.count(b".as_ptr()")-result.count(b".as_ptr()"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("mounted", "link", "output"):
        p.add_argument("--" + name, type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        parent = json.loads(args.link.read_bytes())
        key, = [k for k in parent["source_library_sha256"] if k.endswith("/libless_710_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        p.error("supply --link and --output")
