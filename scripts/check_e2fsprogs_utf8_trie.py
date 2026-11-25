#!/usr/bin/env python3
"""Build an isolated safe Unicode trie lookup on top of a verified Hangul archive."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import json
from pathlib import Path
import re

from check_cargo_private_inlines import digest
from check_e2fsprogs_dirhash_arrays import borrow_arrays, compile_staged, source_list_digest
from check_next_inline_layer import apply_receipt
from e2fsprogs_foreign_declarations import read_proof, staged_compiler_inputs
from e2fsprogs_hangul import replace_hangul

SAFE = Path(__file__).resolve().parents[1] / "compat/e2fsprogs/utf8_trie.rs"
HANGUL_MODULE = "a3fdb547cc58881f713b9bba253c49a05740f9a61d161162bcb067c358506180"
LOOKUP = b'''unsafe extern "C" fn utf8nlookup(
    data: *const utf8data, hangul: *mut u8, s: *const ::core::ffi::c_char, len: size_t,
) -> *const utf8leaf_t {
    if data.is_null() || len == 0 {
        return ::core::ptr::null();
    }
    // Unbounded lookup uses SIZE_MAX. Read only the bytes visited by the trie.
    let leaf = utf8_trie::lookup(&utf8data, (*data).offset as usize, |i| {
        if i < len as usize { Some(*s.add(i) as u8) } else { None }
    });
    match leaf {
        None => ::core::ptr::null(),
        Some(utf8_trie::Leaf::Table(first)) => first,
        Some(utf8_trie::Leaf::Hangul(start)) => {
            let input = s.add(start).cast::<[u8; 3]>().read();
            match hangul_leaf::decompose(input) {
                hangul_leaf::Leaf::Lv(bytes) => hangul.cast::<[u8; 9]>().write(bytes),
                hangul_leaf::Leaf::Lvt(bytes) => hangul.cast::<[u8; 12]>().write(bytes),
            }
            hangul
        }
    }
}
'''


def replace_lookup(module):
    if digest(module) != HANGUL_MODULE:
        raise ValueError("trie module differs from the reviewed Hangul translation")
    data = module.read_bytes()
    start, end = (data.index(b'unsafe extern "C" fn ' + fn + b'(') for fn in (b"utf8nlookup", b"utf8lookup"))
    output = data[:start] + SAFE.read_bytes() + LOOKUP + data[end:]
    table = b"static mut utf8data: [::core::ffi::c_uchar; 64256]"
    if output.count(table) != 1:
        raise ValueError("unexpected Unicode data table")
    output = output.replace(table, table.replace(b"static mut", b"static"))
    module.write_bytes(output)
    return {"raw_pointer_type_tokens_removed": len(re.findall(rb"\*(?:mut|const)\b", data)) -
            len(re.findall(rb"\*(?:mut|const)\b", output)), "module_after": digest(module)}


def compile_trie(parent, archive, scratch, receipt):
    crate, inputs, rustc = staged_compiler_inputs(parent, archive, scratch)
    selection = parent["linked_foreign_declaration_proofs"][str(archive)]
    apply_receipt(crate, read_proof(parent, archive, selection)["declarations"], inputs)
    borrow_arrays(crate / receipt["module"])
    module = crate / receipt["hangul"]["module"]
    replace_hangul(module)
    candidate = scratch / archive.name
    if (source_list_digest({n: digest(crate / n) for n in inputs}) != receipt["compiler_sources_sha256"]
            or compile_staged(crate, inputs, rustc, candidate) != receipt["candidate_sha256"]):
        raise ValueError("trial did not reproduce the complete Hangul compiler inputs and archive")
    layer = replace_lookup(module)
    layer.update(module=receipt["hangul"]["module"], module_before=receipt["hangul"]["module_after"],
                 parent_archive_sha256=receipt["candidate_sha256"], parent_sources_sha256=receipt["compiler_sources_sha256"])
    return dict(receipt, trie=layer, candidate_sha256=compile_staged(crate, inputs, rustc, candidate),
                compiler_sources_sha256=source_list_digest({n: digest(crate / n) for n in inputs}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("scratch", type=Path)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    scratch.mkdir()
    from e2fsprogs_dirhash_archives import control_view
    link = json.loads(args.link_report.read_bytes())
    record = compile_trie(control_view(link), args.archive, scratch, link["e2fsprogs_dirhash_arrays"][str(args.archive)])
    layer = record["trie"]
    result = dict(archive=str(args.archive), parent_sha256=layer["parent_archive_sha256"],
                  candidate_sha256=record["candidate_sha256"], compiler_sources_sha256=record["compiler_sources_sha256"],
                  module_after=layer["module_after"], raw_pointer_type_tokens_removed=layer["raw_pointer_type_tokens_removed"])
    (scratch / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
