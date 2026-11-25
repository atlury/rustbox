#!/usr/bin/env python3
"""Pack LZ4's benchmark dictionary into immutable bytes with checked offset slices."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
from pathlib import Path
import re

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-lz4-dictionary-pilot"
MODULE = "src/programs/lorem.rs"
CANONICAL = ROOT / "work/upstream/lz4-1.11.1/programs/lorem.c"
C_SHA = "c011156be5b6b0f2ab045cb68354cc0907d5f1c7d3f7fd3a32eb5fece2285105"
INPUTS = {
    "61cc17d6ad7436120ac7eaa171fe8d8de9ffc0ac93577021ad0cae5e381077c0",
    "f9cf735655ad0acd151279347f0a9ed5c4d3c3fe19ec96a21b19ad29ec90e653",
}


def dictionary(words):
    offsets = [0]
    for word in words:
        offsets.append(offsets[-1] + len(word))
    if len(words) != 255 or max(map(len, words)) > 16 or offsets[-1] >= 2**16:
        raise ValueError("unexpected LZ4 dictionary dimensions")
    def lines(items, width):
        return "\n".join("        " + ", ".join(items[i:i + width]) + "," for i in range(0, len(items), width))
    chunks = ['"' + b"".join(words[i:i + 12]).decode("ascii") + '"' for i in range(0, len(words), 12)]
    return ("""#[forbid(unsafe_code)]
mod dictionary {
    pub const COUNT: usize = 255;
    static BYTES: &[u8] = concat!(
""" + lines(chunks, 1) + """
    ).as_bytes();
    const OFFSETS: [u16; COUNT + 1] = [
""" + lines(list(map(str, offsets)), 12) + """
    ];
    pub static LENGTHS: [u32; COUNT] = {
        let mut lengths = [0; COUNT];
        let mut i = 0;
        while i < COUNT {
            lengths[i] = (OFFSETS[i + 1] - OFFSETS[i]) as u32;
            i += 1;
        }
        lengths
    };

    pub fn word(i: usize) -> &'static [u8] {
        &BYTES[usize::from(OFFSETS[i])..usize::from(OFFSETS[i + 1])]
    }
}
pub const KNBWORDS: usize = dictionary::COUNT;
""").encode("ascii")


def transform(data):
    before = sha256(data).hexdigest()
    if before not in INPUTS or digest(CANONICAL) != C_SHA:
        raise ValueError("unrecognized LZ4 compiler input or canonical dictionary")
    source = CANONICAL.read_bytes()
    c_table = source.split(b"static const char* kWords[] = {\n", 1)[1].split(b"\n};", 1)[0]
    words = re.findall(rb'"([a-z]+)"', c_table)
    start = data.index(b"static mut kWords:")
    end = data.index(b"static mut kNbWords:", start)
    entries = data[start:data.index(b"\n];", start)].splitlines()[1:]
    spelling = re.compile(rb'    (?:b"([a-z]+)\\0" as \*const u8 as \*const ::core::ffi::c_char|c"([a-z]+)"\.as_ptr\(\)),')
    names = []
    for entry in entries:
        match = spelling.fullmatch(entry)
        if match is None:
            raise ValueError("unrecognized generated dictionary entry")
        names.append(match[1] or match[2])
    if names != words:
        raise ValueError("canonical and translated dictionary bytes or order differ")
    result = data[:start] + dictionary(words) + data[end:]
    for first, following in ((b"static mut g_wordLen:", b"static mut g_wordBuffer:"),
                             (b'unsafe extern "C" fn init_word_len(', b'unsafe extern "C" fn sumLen('),
                             (b"        init_word_len(\n", b"        init_word_buffer();")):
        start = result.index(first)
        result = result[:start] + result[result.index(following, start):]
    for old, new in (
        (b"&raw mut g_wordLen as *mut ::core::ffi::c_uint as *const ::core::ffi::c_uint", b"dictionary::LENGTHS.as_ptr()"),
        (b"&raw mut g_wordLen as *mut ::core::ffi::c_uint", b"dictionary::LENGTHS.as_ptr()"),
        (b"kWords[n as usize] as *const ::core::ffi::c_void", b"dictionary::word(n as usize).as_ptr().cast()"),
    ):
        if result.count(old) != 1:
            raise ValueError(f"unexpected dictionary consumer: {old!r}")
        result = result.replace(old, new)
    result = result.replace(b"g_wordLen[", b"dictionary::LENGTHS[")
    if any(token in result for token in (b"kWords", b"g_wordLen", b"init_word_len")):
        raise ValueError("unconverted mutable dictionary or length reader")
    return result, dict(module=MODULE, words=len(words), packed_bytes=sum(map(len, words)), canonical_sha256=C_SHA,
                        control_module_sha256=before, candidate_module_sha256=sha256(result).hexdigest(),
                        raw_pointer_types_removed=len(POINTER.findall(data)) - len(POINTER.findall(result)))


def substitute(crate, sources):
    if MODULE not in sources:
        raise ValueError("dictionary module outside compiler inputs")
    updated, row = transform((crate / MODULE).read_bytes())
    return {MODULE: updated}, row


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.archive and args.output:
        stage_selected_archive(args.link, args.output, args.archive, MARKER, Path(__file__).name)
    else:
        parser.error("--link, --archive and --output are required")
