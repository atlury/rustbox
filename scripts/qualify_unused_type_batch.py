#!/usr/bin/env python3
"""Count unused C types on one compiler selection, then substitute the verified archives in one multicall link."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter
import fcntl
from hashlib import sha256
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from build_unused_c_types import replay_layer
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import (coalesce_identical_archive_members, namespace_acl_library, namespace_findutils_inputs, namespace_grep_library,
                                   namespace_kmod_library, namespace_ncurses_library, namespace_shadow_library,
                                   namespace_tar_inputs)
from preview_cargo_multicall import preview_link, qualified_inputs
from preview_curl_month_array import namespace as curl_inputs
from preview_diffutils_help_catalogs import namespace as diffutils_inputs
from preview_gawk_ctype import namespace as gawk_inputs
from prune_private_inlines import POINTER
from qualify_iproute2_combined_names import write_result
from verify_c_string_sources import syntax_tool


def simple_namespace(package, mapper):
    def namespace(path, residues, release, stage):
        archive, symbols = mapper(path, stage)
        if residues or symbols != release[package + "_namespaced_symbols"]:
            raise ValueError(f"{package} C linkage differs from the control")
        return archive, []
    return namespace


def findutils_inputs(path, residues, release, stage):
    archive, objects, symbols = namespace_findutils_inputs(path, residues, stage)
    if symbols != release["findutils_namespaced_symbols"]:
        raise ValueError("Findutils private linker symbols differ from the control")
    return archive, objects


def shadow_inputs(path, residues, release, stage):
    # The production link coalesces Shadow's shared runtime against the original
    # Procps staticlib before namespace isolation. Verify the same members here.
    inputs = release["source_library_sha256"]
    provider, = (name for name in inputs if Path(name).name == "libprocps_ng_4_0_7_normalized_audit.a")
    if residues or digest(ROOT / provider) != inputs[provider]:
        raise ValueError("Shadow runtime provider differs from the control")
    archive, members, _ = coalesce_identical_archive_members(ROOT / provider, path,
        stage / "src/.rustbox-shadow-runtime", "Shadow/Procps pinned Rust runtime")
    mapped, symbols = namespace_shadow_library(archive, stage)
    if members != release["shadow_coalesced_runtime_members"] or symbols != release["shadow_namespaced_symbols"]:
        raise ValueError("Shadow runtime or private symbols differ from the control")
    return mapped, []


def tar_inputs(path, residues, release, stage):
    archive, objects, symbols, imports = namespace_tar_inputs(path, residues, release["acl_namespaced_symbols"], stage)
    if symbols != release["tar_namespaced_symbols"] or imports != release["tar_acl_imports"]:
        raise ValueError("GNU tar private symbols or ACL imports differ from the control")
    return archive, objects


PACKAGES = {
    "acl-2.4.0": simple_namespace("acl", namespace_acl_library),
    "curl-8.23.0": curl_inputs,
    "diffutils-3.12": diffutils_inputs,
    "findutils-4.10.0": findutils_inputs,
    "gawk-5.4.0": gawk_inputs,
    "grep-3.12": simple_namespace("grep", namespace_grep_library),
    "kmod-34.3": simple_namespace("kmod", namespace_kmod_library),
    "ncurses-6.6": simple_namespace("ncurses", namespace_ncurses_library),
    "shadow-4.20.4": shadow_inputs,
    "tar-1.35": tar_inputs,
}


def plan(link, pilots, *, identical_foreign=False, extra_foreign=()):
    raw = link.read_bytes()
    release = json.loads(raw)
    rows, sources = {}, {}
    foreign_keys = set()
    directories = [(d, identical_foreign) for d in pilots] + [(d, True) for d in extra_foreign]
    for directory, foreign in directories:
        row = json.loads((directory / "pilot.json").read_bytes())
        key = row["archive"]
        if (key in rows or (not foreign and Path(key).parts[2] not in PACKAGES)
                or release["source_library_sha256"].get(key) != row["control_sha256"]
                or digest(directory / Path(key).name) != row["candidate_sha256"]
                or (row["candidate_sha256"] == row["control_sha256"]) != foreign
                or row["raw_pointer_types_removed"] <= 0):
            raise ValueError(f"unexpected cold archive for {key}")
        if foreign:
            foreign_keys.add(key)
        rows[key] = dict(directory=directory.resolve().relative_to(ROOT).as_posix(), pilot=row)
        sources[key] = {}

    if not rows:
        raise ValueError("no archives selected")
    frequency = Counter()
    pointers = {}
    with TemporaryDirectory() as tmp:
        store = Path(tmp)
        def observe(archive, module, checksum, data):
            key = str(archive)
            sha = checksum.hex()
            frequency[sha] += 1
            if sha not in pointers:
                pointers[sha] = len(POINTER.findall(data))
            if key in rows:
                if str(module) in sources[key]:
                    raise ValueError(f"duplicate compiler input in {key}")
                sources[key][str(module)] = sha
                blob = store / sha
                if not blob.exists():
                    blob.write_bytes(data)

        audit = measure(release, inspect_module=observe, include_standalone_modules=True)
        def totals():
            return dict(all=sum(n * pointers[k] for k, n in frequency.items()),
                        counting_identical_files_once=sum(pointers[k] for k, n in frequency.items() if n))
        before = totals()
        if any(before[k] != audit[k]["raw_pointer_type_tokens"] for k in before):
            raise ValueError("source enumeration differs from the control census")
        from build_current_foreign_declarations import replay_compiler_layer
        scanner = syntax_tool("unused-c-types") if set(rows) != foreign_keys else None
        for key, modules in sources.items():
            def read(module):
                return (store / modules[module]).read_bytes()
            row = rows[key]["pilot"]
            if "unused_after_foreign" in row:
                from build_cascaded_declarations import transform as cascade
                from build_scalar_ffi import replay_layer as replay_sources
                def after_foreign(crate, sources, tool):
                    return cascade(crate, sources, row["foreign_declarations"], tool)
                changes = replay_sources(modules, read, row, scanner or syntax_tool("unused-c-types"), transform=after_foreign)
            elif key in foreign_keys:
                changes = replay_compiler_layer(modules, read, row)
            elif "foreign_declarations" in row:
                from build_scalar_ffi import replay_layer as replay_sources
                from build_stacked_declarations import transform
                def stacked(crate, sources, tool):
                    return transform(crate, sources, row["unused_types"], row["foreign_declarations"], tool)
                changes = replay_sources(modules, read, row, scanner, transform=stacked)
            else:
                changes = replay_layer(modules, read, row, scanner)
            removed = 0
            for module, data in changes.items():
                old, new = modules[module], sha256(data).hexdigest()
                pointers[new] = len(POINTER.findall(data))
                removed += pointers[old] - pointers[new]
                frequency[old] -= 1
                frequency[new] += 1
            if removed != row["raw_pointer_types_removed"]:
                raise ValueError(f"source recount differs from compiler receipt for {key}")
        after = totals()
    if link.read_bytes() != raw:
        raise ValueError("link changed during source replay")
    return dict(parent_link_sha256=sha256(raw).hexdigest(), parent_binary_sha256=audit["binary_sha256"],
                counts={k: dict(before=before[k], after=after[k]) for k in before}, archives=rows)


def materialize(link, manifest):
    """Rebuild missing pinned archives in private staging and replay the full source census."""
    selection = json.loads(manifest.read_bytes())
    if digest(link) != selection["parent_link_sha256"]:
        raise ValueError("manifest belongs to a different compiler selection")
    changed, identical = [], []
    for key, item in selection["archives"].items():
        row = item["pilot"]
        relative = Path(item["directory"])
        if row["archive"] != key or relative.parts[:2] != ("work", "analysis") or ".." in relative.parts:
            raise ValueError("invalid archive or build directory in compiler selection")
        directory = (ROOT / relative).resolve()
        if not directory.is_relative_to(ROOT / "work/analysis"):
            raise ValueError("build directory must remain inside the local analysis tree")
        foreign = row["control_sha256"] == row["candidate_sha256"] and ("ranges" in row or "unused_after_foreign" in row)
        (identical if foreign else changed).append(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with directory.with_name(directory.name + ".materialize.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            def verify(stage):
                if (json.loads((stage / "pilot.json").read_bytes()) != row
                        or digest(stage / Path(key).name) != row["candidate_sha256"]):
                    raise ValueError(f"rebuilt archive or compiler inputs differ for {key}")
            if directory.exists():
                verify(directory)
            else:
                with TemporaryDirectory(dir=directory.parent) as tmp:
                    stage = Path(tmp) / "archive"
                    if "unused_after_foreign" in row:
                        from build_cascaded_declarations import trial
                        foreign_manifest = Path(tmp) / "foreign.json"
                        write_result(foreign_manifest, {"archives": {key: {"pilot": row["foreign_declarations"]}}})
                        trial(link, foreign_manifest, key, stage)
                    elif "foreign_declarations" in row:
                        from build_stacked_declarations import build
                        build(link, row["unused_types"], row["foreign_declarations"], key, stage)
                    else:
                        script = "build_current_foreign_declarations.py" if foreign else "build_unused_c_types.py"
                        subprocess.run([sys.executable, "-B", ROOT / "scripts" / script,
                                        "--link", link, "--archive", key, "--output", stage], check=True)
                    verify(stage)
                    stage.rename(directory)
    if plan(link, changed, extra_foreign=identical) != selection:
        raise ValueError("reconstructed selection differs from the committed census")
    print(f"Verified {len(changed) + len(identical)} archives and the complete compiler census", flush=True)


def relink(link, log, selection, output):
    raw = link.read_bytes()
    selected = selection.read_bytes()
    report = json.loads(selected)
    release = json.loads(raw)
    if report["parent_link_sha256"] != sha256(raw).hexdigest() or report["parent_binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("compiler selection belongs to a different control")
    stages, identical = {}, {}
    for key, item in report["archives"].items():
        directory = ROOT / item["directory"]
        row = item["pilot"]
        if row["archive"] != key or row != json.loads((directory / "pilot.json").read_bytes()):
            raise ValueError(f"cold compiler receipt changed for {key}")
        if row["control_sha256"] == row["candidate_sha256"]:
            sha = row["control_sha256"]
            if (release["source_library_sha256"].get(key) != sha or digest(ROOT / key) != sha
                    or digest(directory / Path(key).name) != sha):
                raise ValueError(f"byte-identical archive changed for {key}")
            identical[key] = sha
            continue
        stages[key] = qualified_inputs(release, directory, row, PACKAGES[Path(key).parts[2]])

    def prepare(name, stage):
        objects, changed, hashes = [], set(), dict(identical)
        for key, build in stages.items():
            files, replaced, meta = build(name, stage)
            objects.extend(files)
            changed.update(replaced)
            hashes[key] = meta["archive_sha256"]
        return objects, changed, dict(archive_sha256=hashes)

    preview_link(link, raw, log, output, prepare, lambda elf, stage: dict(selection_sha256=sha256(selected).hexdigest()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    operations = p.add_subparsers(dest="operation", required=True)
    for operation in ("plan", "identical-foreign"):
        scan = operations.add_parser(operation)
        scan.add_argument("link", type=Path)
        scan.add_argument("output", type=Path)
        scan.add_argument("pilots", type=Path, nargs="+")
    restore = operations.add_parser("materialize", help="restore pinned archives and verify their compiler inputs")
    restore.add_argument("link", type=Path)
    restore.add_argument("selection", type=Path)
    build = operations.add_parser("link")
    for name in ("link", "log", "selection", "output"):
        build.add_argument(name, type=Path)
    args = p.parse_args()
    if args.operation == "materialize":
        materialize(args.link, args.selection)
    elif args.operation != "link":
        write_result(args.output, plan(args.link, args.pilots, identical_foreign=args.operation == "identical-foreign"))
    else:
        relink(args.link, args.log, args.selection, args.output)
