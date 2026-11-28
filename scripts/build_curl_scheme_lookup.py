#!/usr/bin/env python3
"""Replace curl's private scheme parser callbacks with a bounded ASCII byte lookup."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MODULE = "src/lib/protocol.rs"
CANONICAL = ROOT / "work/upstream/curl-8.23.0/lib/protocol.c"
HELPER = ROOT / "compat/curl/schemes.rs"
MARKER = ".rustbox-curl-scheme-lookup"


def canonical_lookup():
    source = CANONICAL.read_bytes()
    lookup = source[source.index(b"static const struct Curl_scheme *two_letter_scheme("):
                    source.index(b"const struct Curl_scheme *Curl_get_scheme(")]
    if sha256(lookup).hexdigest() != "3cb1ac4c59c83cac4d32a61268b4a85bfce9eb17419ae5edd589c0ab8c067d22":
        raise ValueError("canonical scheme parser changed")
    return lookup


def substitute(crate, sources):
    if MODULE not in sources or digest(crate / MODULE) != sources[MODULE]:
        raise ValueError("missing or changed curl scheme module")
    source = (crate / MODULE).read_bytes()
    start = source.index(b'unsafe extern "C" fn two_letter_scheme(')
    end = source.index(b'#[no_mangle]\npub unsafe extern "C" fn Curl_get_scheme(', start)
    old = source[start:end]
    if sha256(old).hexdigest() != "23e50734a63f7c709d38d62a474c78bddd44dbab2365c5ad4a0dcddf7b326ec1":
        raise ValueError("unrecognized translated curl scheme parser")
    helper = HELPER.read_bytes()
    targets = sorted(re.findall(rb"return &Curl_scheme_([a-z0-9]+);", canonical_lookup()))
    mapping = sorted(re.findall(rb'b"([a-z0-9]+)" => &raw const Curl_scheme_([a-z0-9]+),', helper))
    if mapping != [(name, name) for name in targets] or len(targets) != len(set(targets)):
        raise ValueError("Rust scheme lookup differs from the canonical descriptor set")
    result = source[:start] + helper + source[end:]
    return {MODULE: result}, dict(schemes=len(mapping), helper_sha256=digest(HELPER),
                                  canonical_sha256=digest(CANONICAL), removed_callbacks=6,
                                  raw_pointer_types_removed=len(POINTER.findall(old)) - len(POINTER.findall(helper)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("mounted", "link", "output"):
        parser.add_argument("--" + field, type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = (k for k in keys if k.endswith("/libcurl_8_23_0_normalized_audit.a"))
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name, linux_scratch=True)
        replay(args.link, key, args.output, transform=substitute)
    else:
        parser.error("supply --link and --output")
