#!/usr/bin/env python3
"""Build the E2fsprogs directory hash with safe fixed arrays at its two private transform calls."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from check_cargo_private_inlines import digest
from check_next_inline_layer import apply_receipt
from e2fsprogs_foreign_declarations import read_proof, staged_compiler_inputs

HELPERS_SHA = "5ea1be107fc3f64ec81b90f7f1710f98d5450982b58715502faa636763b8fe24"
CALLER_SHA = "8e7d2f96094a8828d2ed34caa48a0ff3464bd0bde5ce98741108e1aa91eb1f50"
OFFSET = re.compile(rb"\*(buf|in_0)\.offset\(([0-9]+) as ::core::ffi::c_int as isize\)")
FUNCTIONS = (b"TEA_transform", b"halfMD4Transform")


def borrow_arrays(module):
    data = module.read_bytes()
    start = data.index(b'unsafe extern "C" fn TEA_transform(')
    end = data.index(b'unsafe extern "C" fn dx_hack_hash(', start)
    caller_start = data.index(b'pub unsafe extern "C" fn ext2fs_dirhash(')
    caller_end = data.index(b'#[no_mangle]', caller_start)
    helpers, caller = data[start:end], data[caller_start:caller_end]
    if hashlib.sha256(helpers).hexdigest() != HELPERS_SHA or hashlib.sha256(caller).hexdigest() != CALLER_SHA:
        raise ValueError("hash helpers or the owning stack arrays changed")

    def index(match):
        base, slot = match.groups()
        if int(slot) >= (4 if base == b"buf" else 8):
            raise ValueError("constant subscript exceeds its owning array")
        return base + b"[" + slot + b"]"

    for name in FUNCTIONS:
        if len(re.findall(rb"\b" + name + rb"\b", data)) != 2:
            raise ValueError(f"expected one private definition and one direct call to {name!r}")
        signature = b'unsafe extern "C" fn ' + name + b'(mut buf: *mut __u32, mut in_0: *const __u32)'
        safe_signature = b"#[forbid(unsafe_code)] fn " + name + b"(buf: &mut [__u32; 4], in_0: &[__u32; 8])"
        helpers = helpers.replace(signature, safe_signature)
        arguments = (name + b"(\n                    &raw mut buf as *mut __u32,\n"
                     b"                    &raw mut in_0 as *mut __u32 as *const __u32,\n                )")
        caller = caller.replace(arguments, name + b"(\n                    &mut buf,\n                    &in_0,\n                )")
    helpers, accesses = OFFSET.subn(index, helpers)
    if (helpers.count(b"#[forbid(unsafe_code)]") != 2 or caller.count(b"&mut buf,") != 2
            or re.search(rb"\*(?:mut|const)\b|\.offset\(", helpers)):
        raise ValueError("incomplete array conversion")
    module.write_bytes(data[:start] + helpers + data[end:caller_start] + caller + data[caller_end:])
    return accesses


def source_list_digest(files):
    data = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def compile_candidate(link, archive, scratch):
    if not scratch.is_dir() or any(scratch.iterdir()):
        raise ValueError("expected an empty scratch directory")
    crate, inputs, rustc = staged_compiler_inputs(link, archive, scratch)
    if selection := link.get("linked_foreign_declaration_proofs", {}).get(str(archive)):
        apply_receipt(crate, read_proof(link, archive, selection)["declarations"], inputs)
    module, = [crate / p for p in inputs if p.endswith("/lib/ext2fs/dirhash.rs")]
    candidate = scratch / archive.name
    depfile = scratch / "compiler.d"

    def build():
        subprocess.run([*rustc, "--cap-lints=allow", f"--emit=link,dep-info={depfile}",
                        "lib.rs", "-o", candidate], cwd=crate, check=True)
        rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
        if {name for name in shlex.split(rule) if name.endswith(".rs")} != inputs:
            raise ValueError("pilot compiler source list changed")
        return digest(candidate)

    control = build()
    if control != link["source_library_sha256"][str(archive)]:
        raise ValueError("control did not reproduce the production archive")
    original_module = digest(module)
    accesses = borrow_arrays(module)
    rebuilt = build()
    return {
        "production_sha256": control,
        "candidate_sha256": rebuilt,
        "module": str(module.relative_to(crate)),
        "module_before": original_module,
        "module_after": digest(module),
        "compiler_sources_sha256": source_list_digest({name: digest(crate / name) for name in inputs}),
        "raw_offset_accesses_replaced": accesses,
        "inlines": link["linked_private_inline_proofs"][str(archive)],
        "second_inlines": link.get("linked_second_inline_proofs", {}).get(str(archive)),
        "declarations": link.get("linked_foreign_declaration_proofs", {}).get(str(archive)),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("archive", type=Path, help="staged E2fsprogs archive from the production link")
    parser.add_argument("scratch", type=Path)
    args = parser.parse_args()
    from e2fsprogs_dirhash_archives import control_view
    report = compile_candidate(control_view(json.loads(args.link_report.read_bytes())), args.archive, args.scratch.resolve())
    print(json.dumps(dict(report, archive=str(args.archive), link_report_sha256=digest(args.link_report)),
                     sort_keys=True), flush=True)
