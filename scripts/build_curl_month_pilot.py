#!/usr/bin/env python3
"""Replace curl's three-letter month recognizer with checked Rust byte-array matching."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER

MODULE = "src/lib/parsedate.rs"
MARKER = ".rustbox-curl-month-pilot"
CALL = b"            (*w).mon = checkmonth(*datep, len);"
BOUNDED_CALL = b"""            (*w).mon = if len == 3 {
                // The loop above counted three readable ASCII letters at *datep.
                checkmonth((*datep).cast::<[u8; 3]>().read())
            } else {
                -1
            };"""


def function(source, name, expected):
    begin = source.index(b'unsafe extern "C" fn ' + name + b'(')
    end = source.index(b"\n}\n", begin) + 3
    body = source[begin:end]
    if sha256(body).hexdigest() != expected:
        raise ValueError(f"unexpected generated curl function {name!r}")
    return body


def substitute(crate, sources):
    if MODULE not in sources:
        raise ValueError("curl calendar module outside the selected inputs")
    source = (crate / MODULE).read_bytes()
    old = function(source, b"checkmonth", "30bcfcc5d412a1c089f77b24d8bfb2238687cafd9875e7e22e061df23c55d078")
    caller = function(source, b"datestring", "518ae37ab865d0bd9e06da3953b2f3a94262aa4a738b64f7168a01f2b231824d")
    if old.count(b".offset(") != 23 or source.count(b"checkmonth(") != 2 or caller.count(CALL) != 1:
        raise ValueError("curl month access or caller set differs")
    new = (ROOT / "compat/curl/month.rs").read_bytes()
    data = source.replace(old, new).replace(caller, caller.replace(CALL, BOUNDED_CALL))
    return {MODULE: data}, dict(module=MODULE, safe_helpers=1, raw_offset_accesses_replaced=23, bounded_array_reads=1,
        raw_pointer_types_removed=len(POINTER.findall(source))-len(POINTER.findall(data)),
        control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(data).hexdigest(),
        checked_helper_sha256=sha256(new).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if k.endswith("/libcurl_8_23_0_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("--link and --output are required")
