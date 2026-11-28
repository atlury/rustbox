#!/usr/bin/env python3
"""Compare translated public libcurl record sizes, alignments and field layouts with curl 8.23.0 headers."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest
from rank_leaf_c_layouts import ALIAS, leaf_declarations

PUBLIC = {"curl_slist", "curl_header", "curl_tlssessioninfo", "curl_blob", "curl_version_info_data"}
CRATE = ROOT / "work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable"
HEADERS = ROOT / "work/upstream/curl-8.23.0/include"


def check(link, ranking):
    rank = json.loads(ranking.read_bytes())
    if rank["link_report_sha256"] != digest(link):
        raise ValueError("expected the layout ranking for the supplied release")
    key, = (k for k in json.loads(link.read_bytes())["source_library_sha256"] if k.endswith("/libcurl_8_23_0_normalized_audit.a"))
    expected = {row["name"]: row["declaration_and_field_types_sha256"]
                for row in rank["layouts"] if row["name"] in PUBLIC and key in row["archives"]}
    if expected.keys() != PUBLIC:
        raise ValueError("missing a ranked public curl layout")
    definitions, aliases, records = [], {}, {}
    cmain, rustmain = [], []
    for module in ["altsvc", "version"]:
        source = CRATE / "src/lib" / (module + ".rs")
        data = source.read_bytes()
        local = dict(ALIAS.findall(data))
        for declaration, fingerprint, _ in leaf_declarations(data):
            name = declaration[1].decode()
            if name in records or fingerprint != expected.get(name):
                continue
            definitions.append(declaration[0].decode())
            fields = re.findall(rb"^    pub (\w+): (.+),$", declaration[2], re.M)
            cexpr = [f"sizeof(struct {name})", f"_Alignof(struct {name})"]
            rexpr = [f"size_of::<{name}>()", f"align_of::<{name}>()"]
            for raw_field, raw_type in fields:
                for ident in re.findall(rb"\b\w+\b", raw_type):
                    if ident in local and aliases.setdefault(ident, local[ident]) != local[ident]:
                        raise ValueError("field alias differs across translation units")
                field, ty = raw_field.decode(), raw_type.decode()
                cexpr.extend([f"offsetof(struct {name}, {field})", f"sizeof(((struct {name}*)0)->{field})"])
                rexpr.extend([f"offset_of!({name}, {field})", f"size_of::<{ty}>()"])
            cmain.append('printf("' + name + ' %zu' * len(cexpr) + '\\n", ' + ", ".join(cexpr) + ");")
            rustmain.append('println!("' + name + ' {}' * len(rexpr) + '", ' + ", ".join(rexpr) + ');')
            records[name] = dict(fields=[n.decode() for n, _ in fields], fingerprint=fingerprint)
    if records.keys() != PUBLIC:
        raise ValueError("public definitions differ from the ranked compiler inputs")
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        rust = ["#![allow(non_camel_case_types)]", "use core::mem::{size_of, align_of, offset_of};"]
        rust += [f"pub type {k.decode()} = {v.decode()};" for k, v in aliases.items()]
        (work / "probe.rs").write_text("\n".join([*rust, *definitions, "fn main() {", *rustmain, "}"]))
        (work / "probe.c").write_text("\n".join(["#include <curl/curl.h>", "#include <stddef.h>", "#include <stdio.h>",
                                                "int main(void) {", *cmain, "return 0;", "}"]))
        subprocess.run(["rustc", "+1.99.0", "--edition=2021", "-O", "-Dwarnings", "probe.rs", "-o", "rust"], cwd=work, check=True)
        rust_result = subprocess.check_output([work/"rust"])
        tree = json.loads(subprocess.check_output(["clang-18", "-std=c11", "-I", HEADERS, "-fsyntax-only",
                                                   "-Xclang", "-ast-dump=json", "probe.c"], cwd=work))
        declared = {}
        for item in tree["inner"]:
            name = item.get("name")
            if item["kind"] == "RecordDecl" and item.get("completeDefinition") and name in PUBLIC:
                if name in declared:
                    raise ValueError(f"duplicate public C record {name}")
                declared[name] = [field["name"] for field in item["inner"] if field["kind"] == "FieldDecl"]
        if declared != {name: data["fields"] for name, data in records.items()}:
            raise ValueError("canonical C and translated Rust field lists differ")
        for cc in ("gcc", "clang-18"):
            subprocess.run([cc, "-std=c11", "-O2", "-Werror", "-I", HEADERS, "probe.c", "-o", cc], cwd=work, check=True)
            if subprocess.check_output([work/cc]) != rust_result:
                raise ValueError(f"{cc} and Rust disagree on a libcurl layout")
        for line in rust_result.decode().splitlines():
            name, *values = line.split()
            size, align, *measurements = map(int, values)
            fields = records[name].pop("fields")
            if len(measurements) != len(fields) * 2:
                raise ValueError("incomplete field measurements")
            records[name].update(size=size, alignment=align,
                                 fields={f: dict(offset=offset, bytes=n) for f, offset, n in zip(fields, measurements[::2], measurements[1::2])})
    return dict(link_sha256=digest(link), ranking_sha256=digest(ranking), compilers=["gcc", "clang-18", "rustc 1.99.0"],
                public_headers={p.name: digest(p) for p in sorted((HEADERS/"curl").glob("*.h"))}, records=records)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("ranking", type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.link, args.ranking), indent=2, sort_keys=True))
