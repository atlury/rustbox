#!/usr/bin/env python3
"""Check constant byte lengths against libc and reject ambiguous bindings and non-literals."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_literal_lengths_pilot import rewrite
from check_e2fsprogs_dirhash_arrays import source_list_digest
from verify_c_string_sources import replay

target = ROOT / "work/analysis/syntax-tools-native"
subprocess.run(["cargo", "build", "--locked", "--offline", "--manifest-path", ROOT / "tools/private-inlines/Cargo.toml",
                "--release", "--bin", "literal-lengths", "--target-dir", target], check=True)
checker = target / "release/literal-lengths"
decl = 'type size_t = usize;\nextern "C" { fn strlen(__s: *const ::core::ffi::c_char) -> size_t; }\n'
cast = ' as *const u8 as *const ::core::ffi::c_char'
body = r'''pub fn lengths() -> (usize, usize, usize, usize) { unsafe {
    let a = strlen(b"\0"CAST);
    let b = strlen(
        b"\xff\x80hello\0"CAST,
    );
    let embedded = strlen(b"a\0b\0"CAST);
    let variable = b"z\0"CAST;
    let c = strlen(variable);
    (a, b, embedded, c)
} }
'''.replace("CAST", cast)
with TemporaryDirectory() as tmp:
    folder = Path(tmp)
    source = (decl + body).replace("\n", "\r\n").encode()
    (folder / "before.rs").write_bytes(source)
    excluded = {
        "local.rs": decl + body.replace("let a", "let strlen = |_: *const ::core::ffi::c_char| 7usize; let a"),
        "raw_local.rs": decl + body.replace("let a", "let r#strlen = |_: *const ::core::ffi::c_char| 7usize; let a"),
        "link.rs": decl.replace("fn strlen", '#[link_name="custom"] fn strlen') + body,
        "macro.rs": decl + "macro_rules! name { () => { strlen } }\n" + body,
        "glob.rs": decl + body.replace("let a", "use scope::*; let a"),
        "missing.rs": decl + r'fn f() -> usize {unsafe {strlen(b"a"CAST)}}'.replace("CAST", cast),
    }
    for name, text in excluded.items():
        (folder / name).write_text(text)
    converted, receipt = rewrite(folder, ["before.rs", *excluded], checker)
    assert set(converted) == {"before.rs"} and receipt["strlen_calls_removed"] == 2
    after = converted["before.rs"]
    inputs = {name: (folder / name).read_bytes() for name in ("before.rs", *excluded)}
    hashes = {name: sha256(data).hexdigest() for name, data in inputs.items()}
    row = dict(receipt, compiler_selected_sources=len(hashes), parent_sources_sha256=source_list_digest(hashes),
               candidate_sources_sha256=source_list_digest({**hashes, "before.rs": sha256(after).hexdigest()}))
    assert replay(hashes, inputs.__getitem__, row, checker, lengths=True) == converted
    # A receipt that omits another eligible module must fail even when the
    # recorded post-edit digest treats the omitted module as unchanged.
    inputs["also.rs"] = source
    more = {**hashes, "also.rs": hashes["before.rs"]}
    incomplete = dict(row, compiler_selected_sources=len(more), parent_sources_sha256=source_list_digest(more),
                      candidate_sources_sha256=source_list_digest({**more, "before.rs": sha256(after).hexdigest()}))
    for selected, record in ((more, incomplete), (hashes, dict(row, raw_pointer_types_removed=0)),
                             (hashes, dict(row, candidate_sources_sha256="0" * 64))):
        try:
            replay(selected, inputs.__getitem__, record, checker, lengths=True)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an incomplete or inconsistent literal length receipt")
    assert after.count(b"\r\n") == source.count(b"\r\n") and rb'strlen(b"a\0b\0"' in after
    (folder / "after.rs").write_bytes(after)
    for variant in ("before", "after"):
        exe = folder / variant
        main = folder / "main.rs"
        main.write_text(f'#[path="{variant}.rs"] mod module; fn main() {{ let (a,b,c,d) = module::lengths(); print!("{{a}} {{b}} {{c}} {{d}}"); }}')
        subprocess.run(["rustc", "--edition=2021", "-A", "warnings", main, "-o", exe], check=True)
        assert subprocess.check_output([exe]) == b"0 7 1 1"
print("Two constant lengths agree with libc. Six ambiguous or ineligible modules were preserved.")
