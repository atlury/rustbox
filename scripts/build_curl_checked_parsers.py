#!/usr/bin/env python3
"""Compose curl's checked month, time-zone and FTP permission readers in one selected archive."""
# SPDX-License-Identifier: curl
import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import build_curl_ftp_permissions as ftp
import build_curl_month_pilot as month
from build_curl_timezone import replace_timezone
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-curl-checked-parsers"


def substitute(crate, sources):
    calendar, first = month.substitute(crate, sources)
    calendar[month.MODULE], second = replace_timezone(calendar[month.MODULE], after_month=True)
    permissions, third = ftp.substitute(crate, sources)
    changes = {**calendar, **permissions}
    removed = sum(len(POINTER.findall((crate / module).read_bytes())) - len(POINTER.findall(result))
                  for module, result in changes.items())
    if (month.MODULE == ftp.MODULE or first["candidate_module_sha256"] != second["control_module_sha256"]
            or any(digest(crate / module) != sources[module] for module in changes)
            or removed != sum(row["raw_pointer_types_removed"] for row in (first, second, third))):
        raise ValueError("overlapping curl substitutions or unexpected compiler source")
    return changes, dict(month=first, timezone=second, ftp_permissions=third, raw_pointer_types_removed=removed)


def prepare_parent(link):
    proof = json.loads((ROOT / "evidence/curl-static-array-c-string-extension.json").read_bytes())
    raw = link.read_bytes()
    parent = json.loads(raw)
    row = proof["candidate"]
    key = row["archive"]
    if (sha256(raw).hexdigest() != proof["link_report_sha256"] or parent.get("native_c_strings")
            or row["candidate_sha256"] != row["control_sha256"]
            or parent["source_library_sha256"].get(key) != row["control_sha256"]):
        raise ValueError("expected the qualified link before the curl native C strings")
    parent["native_c_strings"] = {key: row}
    return parent


def replay(link, pilot=None):
    from audit_linked_pointers import measure
    from cargo_source_parent import cargo_origin
    parent = json.loads(link.read_bytes())
    key, = [k for k in parent["source_library_sha256"] if k.endswith("/libcurl_8_23_0_normalized_audit.a")]
    native = parent["native_c_strings"][key]
    sources = {}
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        def capture(archive, module, checksum, data):
            if archive != Path(key) or str(module) in sources:
                raise ValueError("duplicate or unexpected curl compiler input")
            sources[str(module)] = checksum.hex()
            if str(module) in (month.MODULE, ftp.MODULE):
                path = crate / module
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        measure(parent, inspect_module=capture, archive_pair=(cargo_origin(parent, key), Path(key)))
        edits, facts = substitute(crate, sources)
    before = source_list_digest(sources)
    if before != native["candidate_sources_sha256"]:
        raise ValueError("expected the complete native C-string compiler inputs")
    after = source_list_digest({**sources, **{m: sha256(data).hexdigest() for m, data in edits.items()}})
    if pilot is not None:
        record = json.loads((pilot / "pilot.json").read_bytes())
        expected = dict(archive=key, control_sha256=digest(ROOT / key), control_binary_sha256=parent["binary"]["sha256"],
                        compiler_selected_sources=len(sources), parent_sources_sha256=before, candidate_sources_sha256=after,
                        candidate_sha256=digest(pilot / Path(key).name), cargo_archive=str(cargo_origin(parent, key)), **facts)
        if record != expected:
            raise ValueError("complete curl compiler or archive replay differs")
    return dict(parent_sha256=digest(link), native_literals=native["c_string_literals"],
                parent_sources_sha256=before, candidate_sources_sha256=after, **facts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("mounted", "link", "output"):
        parser.add_argument("--" + name, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--prepare-parent", action="store_true", help="emit the exact qualified native-string link on stdout")
    modes.add_argument("--replay", action="store_true", help="check the selected sources and optionally an existing archive")
    args = parser.parse_args()
    if args.prepare_parent and args.link and not args.output and not args.mounted:
        print(json.dumps(prepare_parent(args.link), sort_keys=True), end="")
    elif args.replay and args.link and not args.mounted:
        print(json.dumps(replay(args.link, args.output), sort_keys=True, indent=2))
    elif args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=False)
    elif args.link and args.output:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if k.endswith("/libcurl_8_23_0_normalized_audit.a")]
        stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
    else:
        parser.error("supply --link and --output")
