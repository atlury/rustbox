#!/usr/bin/env python3
"""Replace curl's private time-zone lookup with a checked slice and immutable canonical tables."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_curl_month_pilot import MODULE, function
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-curl-timezone"
HELPER = ROOT / "compat/curl/timezone.rs"
CANONICAL = ROOT / "work/upstream/curl-8.23.0/lib/parsedate.c"
TABLES_SHA = "7f6dcc78f9219637bdf26d7bb038a031b2aff2d971b6b1fc360677318825f064"
CALL = b"            (*w).tzoff = checktz(*datep, len);"
BOUND = b"""            // datestring counted len readable ASCII letters starting at *datep.
            let word = core::slice::from_raw_parts((*datep).cast::<u8>(), len as usize);
            (*w).tzoff = checktz(word);"""


def replace_timezone(data, *, after_month=False):
    if digest(CANONICAL) != "ad58e5aed9b7c9f334186bab69e423bf37c2b941aa2e5b0a93536bfd4aca0881":
        raise ValueError("unexpected curl date parser")
    caller_sha = ("0f9d0c84920c2320c26884613742915afdb77ab8dd3cf2863aa68c1290aa0463" if after_month else
                  "518ae37ab865d0bd9e06da3953b2f3a94262aa4a738b64f7168a01f2b231824d")
    caller = function(data, b"datestring", caller_sha)
    old = function(data, b"checktz", "e702c19ab72520b014a62a2795dbbaf5336becb0e3c41db137df3a647717fa6f")
    compare = function(data, b"tzcompare", "5518529ab252585250e920b519fac41a8a4e86c2abe1eb57bcc216cf32e32aa9")
    search = b"#[inline]\n" + function(data, b"bsearch", "b9bcda5f35cb13592c73cb0b797e9326c09236a360ec3e5cf659bc4ffb92ab2a")
    tables = data[data.index(b"static mut tzone:"):data.index(b'unsafe extern "C" fn checkday(')]
    if (sha256(tables).hexdigest() != TABLES_SHA or caller.count(CALL) != 1 or data.count(b"checktz(") != 2
            or data.count(search) != 1 or data.count(b"bsearch(") != 3 or data.count(b"tzcompare") != 3):
        raise ValueError("generated curl time-zone tables or callers changed")
    helper = HELPER.read_bytes()
    result = data.replace(search, b"").replace(compare, b"").replace(old, helper).replace(CALL, BOUND)
    result = result.replace(tables, tables.replace(b"static mut ", b"static "))
    return result, dict(module=MODULE, canonical_sha256=digest(CANONICAL), helper_sha256=sha256(helper).hexdigest(),
                                  tables_sha256=TABLES_SHA, control_module_sha256=sha256(data).hexdigest(),
                                  candidate_module_sha256=sha256(result).hexdigest(), mutable_tables_removed=3,
                                  raw_pointer_types_removed=len(POINTER.findall(data)) - len(POINTER.findall(result)))


def substitute(crate, sources):
    if MODULE not in sources:
        raise ValueError("curl date parser outside the selected compiler inputs")
    result, facts = replace_timezone((crate / MODULE).read_bytes())
    return {MODULE: result}, facts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("mounted", "link", "output"):
        parser.add_argument("--" + arg, type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if k.endswith("/libcurl_8_23_0_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("supply --link and --output")
