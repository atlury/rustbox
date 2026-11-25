#!/usr/bin/env python3
"""Replace Zstd's sequential lorem generator with a bounded writer and packed immutable word table."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from build_lz4_dictionary_pilot import dictionary
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

CANONICAL = ROOT / "work/upstream/zstd-1.5.7/programs/lorem.c"
C_SHA = "d0f7bfbc9dc4f906532e71cbe7500324e02d8947eb8d4d99ae9ad3638e86b5d5"
MODULE = "src/programs/lorem.rs"
HELPER = ROOT / "compat/zstd/lorem.rs"
MARKER = ".rustbox-zstd-lorem"


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    original = sha256(data).hexdigest()
    if MODULE not in sources or original != "d6acfb1c1ed89112136101faaf9236000e1fb8f8a3ebd91d34b2cea78f912791" or digest(CANONICAL) != C_SHA:
        raise ValueError("unknown compiled Zstd generator or canonical source")
    canonical = CANONICAL.read_bytes().split(b'static const char* kWords[] = {', 1)[1].split(b'\n};', 1)[0]
    words = re.findall(rb'"([a-z]+)"', canonical)
    translated = data.split(b"static mut kWords:", 1)[1].split(b"\n];", 1)[0]
    if words != re.findall(rb'b"([a-z]+)\\0"', translated):
        raise ValueError("canonical and generated Zstd words differ")
    # Preserve the configured C assertion and both exported signatures exactly.
    assertion = data[data.index(b"    '_c2rust_label: {", data.index(b'fn LOREM_genBlock(')):data.index(b"    g_maxChars = size;")]
    prefix = data[:data.index(b"    fn memcpy(")] + b"}\npub type size_t = usize;\n"
    start = data.index(b'#[no_mangle]\npub unsafe extern "C" fn LOREM_genBlock')
    signature = data[start:data.index(b'    g_ptr = buffer', start)]
    wrapper = data[data.index(b'#[no_mangle]\npub unsafe extern "C" fn LOREM_genBuffer'):data.index(b'unsafe extern "C" fn run_static_initializers')]
    result = prefix + dictionary(words) + HELPER.read_bytes() + signature + assertion + b"""
    // The C API accepts an uninitialized writable buffer. A zero-length call
    // may supply NULL and never needs a Rust reference to the caller's storage.
    let output = if size == 0 { &mut [][..] } else {
        core::slice::from_raw_parts_mut(buffer.cast::<core::mem::MaybeUninit<u8>>(), size)
    };
    generator::block(output, seed, first != 0, fill != 0)
}
""" + wrapper
    return {MODULE: result}, dict(module=MODULE, words=len(words), packed_bytes=sum(map(len, words)), canonical_sha256=C_SHA,
               helper_sha256=digest(HELPER), control_module_sha256=original, candidate_module_sha256=sha256(result).hexdigest(),
               raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(result)),
               mutable_statics_removed=data.count(b"static mut ")-result.count(b"static mut "))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("mounted", "link", "output"):
        p.add_argument("--" + name, type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        key, = [key for key in json.loads(args.link.read_bytes())["source_library_sha256"]
                if key.endswith("/libzstd_1_5_7_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        p.error("supply --link and --output")
