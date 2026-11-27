#!/usr/bin/env python3
"""Cold-build a Cargo archive after removing closed groups of compiler-dead private inline helpers."""
# SPDX-License-Identifier: 0BSD
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest, layout
from inline_source_layout import WHITESPACE
from prune_private_inlines import POINTER

MARKER = ".rustbox-closed-inline-pilot"
SCANNER = "closed-inlines"
MODULES_FILE = ".rustbox-closed-inline-modules.json"
SOURCE = ROOT / "tools/private-inlines/src/bin" / (SCANNER + ".rs")


PROBE = "rustbox_closed_inline_diagnostic_probe"


@contextmanager
def probe_source(crate, sources, sites):
    # A fresh private definition proves the diagnostic pass actually inspected this crate,
    # including when no other eligible unused function exists.
    root = crate / "lib.rs"
    original = root.read_bytes()
    if digest(root) != sources["lib.rs"] or PROBE.encode() in original:
        raise ValueError("unexpected crate root for diagnostic probe")
    prefix = b"\nfn "
    try:
        root.write_bytes(original + prefix + PROBE.encode() + b"() {}\n")
        yield
    finally:
        root.write_bytes(original)
    records = sites.get("lib.rs", {})
    if records.pop(PROBE, None) != len(original) + len(prefix):
        raise ValueError("rustc did not report the expected diagnostic probe at the crate root")
    if not records:
        sites.pop("lib.rs", None)


def record_site(sites, sources, msg, crate):
    if (msg.get("code") or {}).get("code") != "dead_code":
        return
    name = re.fullmatch(r"function `([^ `]+)` is never used", msg["message"])
    if not name:
        return
    for span in msg["spans"]:
        filename = Path(span["file_name"])
        if filename.is_absolute():
            if not filename.is_relative_to(crate):
                continue
            filename = filename.relative_to(crate)
        module = filename.as_posix()
        if span["is_primary"] and span["expansion"] is None and module in sources:
            entries = sites.setdefault(module,{})
            old = entries.setdefault(name[1],span["byte_start"])
            if old != span["byte_start"]:
                raise ValueError("ambiguous dead function diagnostic in " + module)


def direct_substitution(crate, sources, rustc, scratch, modules=None):
    diagnostics = scratch / "closed-inline-diagnostics.jsonl"
    sites = {}
    with probe_source(crate, sources, sites):
        with diagnostics.open("w") as output:
            subprocess.run([*rustc, "--emit=metadata", "-A", "warnings", "--force-warn", "dead_code",
                            "--error-format=json", "lib.rs", "-o", scratch/"dead.rmeta"], cwd=crate, stderr=output, check=True)
        with diagnostics.open() as stream:
            for line in stream:
                record_site(sites, sources, json.loads(line), crate)
    return substitution(crate, sources, sites, ROOT/"work/analysis/private-inlines-linux/release"/SCANNER, modules)


def compiler_sites(crate, sources, target):
    import tomllib
    toolchain = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    cmd = ["cargo","rustc","--locked","--offline","--release","--lib","--message-format=json",
           "--","-A","warnings","--force-warn","dead_code"]
    sites = {}
    with probe_source(crate, sources, sites):
        with subprocess.Popen(cmd, cwd=crate, env=dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=toolchain),
                              stdout=subprocess.PIPE, text=True) as child:
            for line in child.stdout:
                note = json.loads(line)
                if note.get("reason") != "compiler-message" or Path(note["target"]["src_path"]).resolve() != (crate / "lib.rs").resolve():
                    continue
                record_site(sites, sources, note["message"], crate)
            if child.wait():
                raise ValueError("rustc failed while collecting private helper diagnostics")
    return sites


def substitution(crate, sources, sites, scanner, modules=None):
    if not sites:
        raise ValueError("these compiler-dead groups contain no raw pointer types")
    if not sites.keys() <= sources.keys():
        raise ValueError("expected dead-code diagnostics from compiler-selected modules")
    if modules is not None:
        if not modules or len(set(modules)) != len(modules) or not set(modules) <= sites.keys():
            raise ValueError("subset must contain distinct modules with compiler diagnostics")
        sites = {name: sites[name] for name in modules}
    plan = json.loads(subprocess.check_output([scanner,crate],input=json.dumps(sites).encode()))
    changed, selected = {}, {}
    functions = pointers = referenced_pointers = referenced_functions = 0
    for module, helpers in plan.items():
        data = (crate / module).read_bytes()
        spans = sorted((lo,hi,name,referenced) for name,((lo,hi),referenced) in helpers.items())
        candidate = bytearray(data)
        last = local = local_referenced = 0
        for lo, hi, name, referenced in spans:
            if not last <= lo <= sites[module][name] < hi <= len(data):
                raise ValueError("invalid closed helper range in " + module)
            last = hi
            count = len(POINTER.findall(data[lo:hi]))
            candidate[lo:hi] = data[lo:hi].translate(WHITESPACE)
            local += count
            if referenced:
                local_referenced += count
        if not local:
            continue
        changed[module] = bytes(candidate)
        selected[module] = {name:sites[module][name] for name in helpers}
        functions += len(helpers)
        pointers += local
        referenced_pointers += local_referenced
        referenced_functions += sum(referenced for _,_,_,referenced in spans)
    if modules is not None and set(modules) != changed.keys():
        raise ValueError("requested module contains no closed pointer-bearing group")
    if not changed:
        raise ValueError("these compiler-dead groups contain no raw pointer types")
    return changed, dict(dead_sites=selected, raw_pointer_types_removed=pointers, private_helpers_removed=functions,
                         referenced_pointer_types_removed=referenced_pointers, referenced_helpers_removed=referenced_functions,
                         scanner_source_sha256=digest(SOURCE))


def build(link, key, output, modules=None):
    origin = cargo_origin(json.loads(link.read_bytes()), key)
    if direct_crate(origin) is not None:
        from build_staged_c_strings import build as build_direct
        build_direct(link, output, key, modules, closed_inlines=True)
    else:
        def select(crate):
            if (crate / MODULES_FILE).exists():
                raise ValueError("unexpected existing private helper module selector")
            if modules is not None:
                (crate / MODULES_FILE).write_text(json.dumps(modules))
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name, select)


def replay_layer(parent, read_parent, row, scanner):
    from hashlib import sha256
    from tempfile import TemporaryDirectory
    from check_e2fsprogs_dirhash_arrays import source_list_digest

    if (len(parent) != row["compiler_selected_sources"]
            or source_list_digest(parent) != row["parent_sources_sha256"]
            or not row["dead_sites"].keys() <= parent.keys()):
        raise ValueError("private helper group parent sources differ from cold build")
    with TemporaryDirectory() as temp:
        crate = Path(temp)
        for module in row["dead_sites"]:
            path = crate / module
            if Path(module).is_absolute() or ".." in Path(module).parts:
                raise ValueError("invalid compiler input path")
            path.parent.mkdir(parents=True, exist_ok=True)
            data = read_parent(module)
            if sha256(data).hexdigest() != parent[module]:
                raise ValueError("private helper module differs from the parent inputs")
            path.write_bytes(data)
        changes, facts = substitution(crate, parent, row["dead_sites"], scanner)
    updated = {**parent, **{k: sha256(v).hexdigest() for k, v in changes.items()}}
    if (any(row.get(k) != v for k, v in facts.items())
            or source_list_digest(updated) != row["candidate_sources_sha256"]):
        raise ValueError("private helper replay differs from the cold compiler receipt")
    return changes


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link",type=Path)
    p.add_argument("--archive")
    p.add_argument("--modules", nargs="+")
    p.add_argument("--output",type=Path)
    p.add_argument("--replay",type=Path)
    p.add_argument("--mounted",type=Path)
    args = p.parse_args()
    if args.mounted:
        scanner = ROOT / "work/analysis/private-inlines-linux/release" / SCANNER
        _,target = layout(args.mounted)
        def apply(crate,sources):
            selector = crate / MODULES_FILE
            modules = json.loads(selector.read_bytes()) if selector.exists() else None
            return substitution(crate, sources, compiler_sites(crate, sources, ROOT / target), scanner, modules)
        compile_mounted_sources(args.mounted,apply,MARKER,allow_identical=True)
    elif args.link and args.replay:
        row = json.loads((args.replay/"pilot.json").read_bytes())
        native = ROOT / "work/analysis/syntax-tools-native"
        subprocess.run(["cargo","build","--locked","--offline","--release","--manifest-path",ROOT/"tools/private-inlines/Cargo.toml",
                        "--target-dir",native,"--bin",SCANNER],check=True)
        def apply(crate,sources):
            return substitution(crate,sources,row["dead_sites"],native/"release"/SCANNER)
        actual = replay(args.link,row["archive"],transform=apply)
        origin = cargo_origin(json.loads(args.link.read_bytes()), row["archive"])
        if direct_crate(origin) is not None:
            actual.pop("cargo_archive", None)
            actual["rustc_archive"] = str(origin)
        actual["candidate_sha256"] = digest(args.replay / Path(row["archive"]).name)
        if actual != row:
            raise ValueError("archive or compiler sources differ from the independent replay")
        print(f"Replayed {row['private_helpers_removed']} helpers and {row['raw_pointer_types_removed']} raw pointer types.")
    elif args.link and args.archive and args.output:
        build(args.link, args.archive, args.output, args.modules)
    else:
        p.error("provide --link with --archive and --output, or --link with --replay")
