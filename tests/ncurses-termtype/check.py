#!/usr/bin/env python3
"""Compare both translated terminal types with the independently configured ncurses headers."""
# SPDX-License-Identifier: MIT
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_ncurses_termtype_layouts import DEFINITIONS
from check_cargo_private_inlines import digest
from rank_leaf_c_layouts import STRUCT

base = ROOT / "work/analysis/ncurses-6.6"
source = base / "translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable/src/progs/tset.rs"
fields = ("term_names str_table Booleans Numbers Strings ext_str_table ext_Names "
          "num_Booleans num_Numbers num_Strings ext_Booleans ext_Numbers ext_Strings").split()

with TemporaryDirectory() as tmp:
    work = Path(tmp)
    types = {m[1].decode(): m[0] for m in STRUCT.finditer(source.read_bytes()) if m[1].decode() in DEFINITIONS}
    if {k: sha256(v).hexdigest() for k, v in types.items()} != DEFINITIONS:
        raise ValueError("changed ncurses Rust ABI definitions")
    rust = bytearray(b"#![allow(non_snake_case)]\n" + b"".join(types.values()))
    c = ["#define NCURSES_INTERNALS 1", "#include <term.h>", "#include <stddef.h>", "#include <stdio.h>"]
    main = []
    for name in DEFINITIONS:
        shape = [f"core::mem::size_of::<{name}>()", f"core::mem::align_of::<{name}>()"]
        shape += [f"core::mem::offset_of!({name}, {field})" for field in fields]
        rust.extend((f'#[no_mangle] pub extern "C" fn {name}_layout(i: usize) -> usize {{\n'
                     f'    [{", ".join(shape)}][i]\n}}\n'
                     f'#[no_mangle] pub extern "C" fn {name}_number(t: &{name}) -> i32 {{\n'
                     f'    unsafe {{ i32::from(*t.Numbers) }}\n}}\n').encode())
        ct = name.upper()
        c.extend([f"extern size_t {name}_layout(size_t);", f"extern int {name}_number(const {ct} *);"])
        offsets = [f"sizeof({ct})", f"_Alignof({ct})", *[f"offsetof({ct}, {field})" for field in fields]]
        scalar, maximum = ("short", 32767) if name == "termtype" else ("int", 65537)
        main.extend(["{", f"size_t layout[] = {{{', '.join(offsets)}}};",
                     f"for (size_t i = 0; i < {len(offsets)}; ++i) {{",
                     f'    if (layout[i] != {name}_layout(i)) return 1;',
                     '    printf("%zu ", layout[i]);', "}",
                     f"{scalar} numbers[] = {{-2, -1, 0, {maximum}}};", f"{ct} t = {{0}};",
                     "for (unsigned i=0; i<4; ++i) { t.Numbers = &numbers[i];",
                     f"    if ({name}_number(&t) != numbers[i]) return 2;", "}", 'puts("");', "}"])
    (work / "types.rs").write_bytes(rust)
    (work / "probe.c").write_text("\n".join([*c, "int main(void) {", *main, "return 0;", "}"]))
    subprocess.run(["rustc", "+1.99.0", "--edition=2021", "-O", "--crate-type=staticlib", "types.rs", "-o", "types.a"],
                   cwd=work, check=True)
    result = {}
    for cc, tree in (("gcc", "gcc-root"), ("clang-18", "clang-root")):
        headers = base / "oracle" / tree / "usr/include"
        subprocess.run([cc, "-O2", "-Werror", "-I", headers, "probe.c", "types.a", "-o", "probe"], cwd=work, check=True)
        measurements = [list(map(int, row.split())) for row in subprocess.check_output([work / "probe"]).splitlines()]
        if len(measurements) != 2 or any(len(row) != 15 for row in measurements):
            raise ValueError("missing terminal layout observations")
        result[cc] = dict(header_sha256=digest(headers / "term.h"), size_alignment_field_offsets=measurements,
                          numeric_read_cases=8)
    print(json.dumps(result, sort_keys=True))
