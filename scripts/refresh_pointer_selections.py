#!/usr/bin/env python3
"""Carry byte-identical selections forward and cold-build archives whose parent sources changed."""
# SPDX-License-Identifier: 0BSD
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from audit_linked_pointers import check_identical_layer, measure
from build_va_list_layout_batch import archive_folder
from cargo_source_parent import archives_by_origin, row_origin
from check_cargo_private_inlines import ROOT, digest
from prepare_identical_archives import enroll, prepare, selected_receipts, validate_link


DRIVERS = {
    "closed_inline_groups": "build_closed_inlines.py",
    "shared_scalar_ffi": "build_scalar_ffi.py",
    "shared_variadic_ffi": "build_variadic_ffi.py",
    "shared_va_list_layouts": "build_va_list_layout_pilot.py",
}


def refresh(link, source_manifest, output, workspace, layer, jobs):
    raw = link.read_bytes()
    parent = json.loads(raw)
    original = source_manifest.read_bytes()
    prior = json.loads(original)
    if layer in parent or output.resolve() in (source_manifest.resolve(), link.resolve()):
        raise ValueError("expected a separate manifest and a parent without this selection")
    if not prior or layer not in DRIVERS:
        raise ValueError("expected a populated pointer source selection")
    workspace.mkdir(parents=True, exist_ok=True)
    # Include release and source-manifest identity in the directory used by resumable builds.
    cache = workspace / (sha256(raw).hexdigest() + "-" + sha256(original).hexdigest())
    cache.mkdir(exist_ok=True)
    by_origin = archives_by_origin(parent)
    kept, rebuild, pending = {}, {}, {}
    driver = ROOT / "scripts" / DRIVERS[layer]
    for old, item in prior.items():
        row = item["pilot"]
        if row["archive"] != old or row["candidate_sha256"] != row["control_sha256"]:
            raise ValueError("previous selection does not describe a byte-identical archive")
        key = by_origin.get(row_origin(row))
        if key is None:
            pending[old] = "archive origin absent from new release"
        elif layer == "shared_va_list_layouts" and any(key in parent.get(later, {}) for later in
                                                       ("shared_ncurses_termtypes", "closed_inline_groups", "shared_scalar_ffi")):
            pending[key] = "a later source selection requires a joint rebuild"
        elif (key == old and parent["source_library_sha256"][key] == row["candidate_sha256"]
                and selected_receipts(parent, key, layer) == item["parent_receipts"]):
            kept[key] = item
        else:
            rebuild[key] = row

    def cold(key):
        folder = archive_folder(cache, key)
        selection = ["--modules", *sorted(rebuild[key]["dead_sites"])] if layer == "closed_inline_groups" else []
        if layer == "shared_va_list_layouts":
            selection = ["--modules", *rebuild[key]["reexporting_modules"]]
        if rebuild[key].get("all_scalar_interfaces"):
            selection = ["--all-interfaces"]
        cmd = [sys.executable, "-B", driver, "--link", link]
        with folder.with_suffix(".lock").open("a") as lock, folder.with_suffix(".log").open("ab") as log:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not folder.exists():
                subprocess.run([*cmd, "--archive", key, "--output", folder, *selection], stdout=log, stderr=subprocess.STDOUT, check=True)
            replay = (["--archive", key, "--output", folder, "--replay"] if layer == "shared_variadic_ffi"
                      else ["--replay", folder])
            subprocess.run([*cmd, *replay], stdout=log, stderr=subprocess.STDOUT, check=True)
        row = json.loads((folder / "pilot.json").read_bytes())
        if row["archive"] != key or row["control_binary_sha256"] != parent["binary"]["sha256"]:
            raise ValueError("fresh compiler receipt does not belong to this release")
        if layer == "shared_va_list_layouts" and any(row[field] != rebuild[key][field] for field in
                                                    ("declaration_sha256", "provider", "provider_namespace", "reexporting_modules",
                                                     "raw_pointer_types_removed")):
            raise ValueError("variadic layout rebuild changed the selected provider or consumers")
        return folder if row["candidate_sha256"] == row["control_sha256"] else None

    new = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {key: pool.submit(cold, key) for key in sorted(rebuild)}
        for key, future in futures.items():
            try:
                folder = future.result()
                if folder is None:
                    pending[key] = "new cold build changed archive bytes"
                else:
                    new.append(folder)
            except subprocess.CalledProcessError as exc:
                pending[key] = f"compiler or source replay exited {exc.returncode}; see {archive_folder(cache,key).name}.log"
    manifest = dict(kept)
    if new:
        partial = cache / "new-manifest.json"
        enroll(link, partial, new, layer)
        manifest.update(json.loads(partial.read_bytes()))
    if not manifest:
        raise ValueError(f"no byte-identical selections qualified: {pending}")
    prepare(manifest, layer)
    rows = validate_link(manifest, parent["source_library_sha256"], parent, layer)
    selected = {**parent, layer: rows}
    before, after = measure(parent), measure(selected)
    check_identical_layer(parent, selected, before, after, layer)
    if raw != link.read_bytes() or original != source_manifest.read_bytes():
        raise ValueError("parent release or input manifest changed during verification")
    with TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / "manifest.json"
        staged.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        staged.replace(output)
    return dict(parent_link_sha256=sha256(raw).hexdigest(), manifest_sha256=digest(output), reused=len(kept),
                rebuilt_identical=len(new), deferred=pending,
                counts={k:{"before":before[k]["raw_pointer_type_tokens"], "after":after[k]["raw_pointer_type_tokens"]}
                        for k in ("all", "counting_identical_files_once")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--layer", required=True, choices=sorted(DRIVERS))
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    print(json.dumps(refresh(args.link, args.source_manifest, args.output, args.workspace, args.layer, args.jobs),
                     sort_keys=True, indent=2))
