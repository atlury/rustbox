#!/usr/bin/env python3
"""Replace curl's private FTP mode reader with a checked nine-byte Rust decoder."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_curl_month_pilot import function
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

MODULE = "src/lib/ftplistparser.rs"
HELPER = ROOT / "compat/curl/ftp_permissions.rs"
CANONICAL = ROOT / "work/upstream/curl-8.23.0/lib/ftplistparser.c"
MARKER = ".rustbox-curl-ftp-permissions"
CALL = b"        perm = ftp_pl_get_permission(mem.offset((*parser).item_offset as isize));"
BOUNDED = b"""        // The parser has consumed nine permission bytes followed by a space.
        let offset = (*parser).item_offset as usize;
        let len = curlx_dyn_len(&raw mut (*infop).buf) as usize;
        if offset > len || len - offset < 9 {
            return CURLE_FTP_BAD_FILE_LIST;
        }
        perm = ftp_pl_get_permission(mem.add(offset).cast::<[u8; 9]>().read());"""


def substitute(crate, sources):
    if MODULE not in sources or digest(CANONICAL) != "abda2491568be631d71d699410aeeaeadd338705da3429b64b0909953dda7b42":
        raise ValueError("unexpected curl FTP parser")
    source = (crate / MODULE).read_bytes()
    old = function(source, b"ftp_pl_get_permission", "34cd0f2b68b4dc43220f8fc77b1047a4a1c83c8e5ca75c8200bfc962e1afe0b3")
    caller = function(source, b"parse_unix_permission", "4e0631df17b165dbb759011b3d29ea66deeebd9fd21d6b71591e14d0a19cccff")
    if source.count(b"ftp_pl_get_permission(") != 2 or caller.count(CALL) != 1 or old.count(b".offset(") != 24:
        raise ValueError("unexpected generated permission decoder or caller")
    helper = HELPER.read_bytes()
    data = source.replace(old, helper).replace(CALL, BOUNDED)
    return {MODULE: data}, dict(module=MODULE, canonical_sha256=digest(CANONICAL), checked_helper_sha256=digest(HELPER),
                                control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(data).hexdigest(),
                                raw_pointer_types_removed=len(POINTER.findall(source))-len(POINTER.findall(data)),
                                decoder_raw_offsets_removed=24, bounded_array_reads=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("mounted", "link", "output"):
        parser.add_argument("--" + arg, type=Path)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link and args.output:
        key, = [key for key in json.loads(args.link.read_bytes())["source_library_sha256"]
                if key.endswith("/libcurl_8_23_0_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("supply --link and --output")
