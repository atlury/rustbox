#!/usr/bin/env python3
"""Cold-build a Cargo archive after removing closed groups of compiler-dead private inline helpers."""
# SPDX-License-Identifier: 0BSD
import argparse
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
SOURCE = ROOT / "tools/private-inlines/src/bin" / (SCANNER + ".rs")


def record_site(sites, sources, msg):
    if (msg.get("code") or {}).get("code") != "dead_code":
        return
    name = re.fullmatch(r"function `([^ `]+)` is never used", msg["message"])
    if not name:
        return
    for span in msg["spans"]:
        module = span["file_name"]
        if span["is_primary"] and span["expansion"] is None and module in sources:
            entries = sites.setdefault(module,{})
            old = entries.setdefault(name[1],span["byte_start"])
            if old != span["byte_start"]:
                raise ValueError("ambiguous dead function diagnostic in " + module)


def direct_substitution(crate, sources, rustc, scratch):
    diagnostics = scratch / "closed-inline-diagnostics.jsonl"
    with diagnostics.open("w") as output:
        subprocess.run([*rustc, "--emit=metadata", "-A", "warnings", "--force-warn", "dead_code",
                        "--error-format=json", "lib.rs", "-o", scratch/"dead.rmeta"], cwd=crate, stderr=output, check=True)
    sites = {}
    with diagnostics.open() as stream:
        for line in stream:
            record_site(sites, sources, json.loads(line))
    return substitution(crate, sources, sites, ROOT/"work/analysis/private-inlines-linux/release"/SCANNER)


def compiler_sites(crate, sources, target):
    import tomllib
    toolchain = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    cmd = ["cargo","rustc","--locked","--offline","--release","--lib","--message-format=json",
           "--","-A","warnings","--force-warn","dead_code"]
    sites = {}
    with subprocess.Popen(cmd, cwd=crate, env=dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=toolchain),
                          stdout=subprocess.PIPE, text=True) as child:
        for line in child.stdout:
            note = json.loads(line)
            if note.get("reason") != "compiler-message" or note["target"]["src_path"] != str(crate / "lib.rs"):
                continue
            record_site(sites, sources, note["message"])
        if child.wait():
            raise ValueError("rustc failed while collecting private helper diagnostics")
    return sites


def substitution(crate, sources, sites, scanner):
    if not sites or not sites.keys() <= sources.keys():
        raise ValueError("expected dead-code diagnostics from compiler-selected modules")
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
    if not changed:
        raise ValueError("these compiler-dead groups contain no raw pointer types")
    return changed, dict(dead_sites=selected, raw_pointer_types_removed=pointers, private_helpers_removed=functions,
                         referenced_pointer_types_removed=referenced_pointers, referenced_helpers_removed=referenced_functions,
                         scanner_source_sha256=digest(SOURCE))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link",type=Path)
    p.add_argument("--archive")
    p.add_argument("--output",type=Path)
    p.add_argument("--replay",type=Path)
    p.add_argument("--mounted",type=Path)
    args = p.parse_args()
    if args.mounted:
        scanner = ROOT / "work/analysis/private-inlines-linux/release" / SCANNER
        _,target = layout(args.mounted)
        def apply(crate,sources):
            return substitution(crate,sources,compiler_sites(crate,sources,ROOT/target),scanner)
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
        origin = cargo_origin(json.loads(args.link.read_bytes()), args.archive)
        if direct_crate(origin) is not None:
            from build_staged_c_strings import build
            build(args.link, args.output, args.archive, closed_inlines=True)
        else:
            stage_selected_archive(args.link,args.output,args.archive,MARKER,Path(__file__).name)
    else:
        p.error("provide --link with --archive and --output, or --link with --replay")
