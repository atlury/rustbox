#!/usr/bin/env python3
"""Classify parsed raw-pointer types in the exact Rust source files selected by a multicall build."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import METRICS, measure
from check_cargo_private_inlines import ROOT, digest
from verify_c_string_sources import syntax_tool


def summarize(frequencies, profiles, lexical):
    groups = defaultdict(Counter)
    textual = spaced = 0
    for key, copies in frequencies.items():
        row = profiles[key]
        for context, (const, mutable) in row["groups"].items():
            groups[context]["const"] += copies * const
            groups[context]["mut"] += copies * mutable
        spaced += copies * row["spaced"]
        textual += copies * lexical[key]
    parsed = sum(sum(pair.values()) for pair in groups.values())
    outside = textual - (parsed - spaced)
    if outside < 0:
        raise ValueError("parsed compact spellings exceed the source inventory")
    return dict(files=sum(frequencies.values()), parsed_types=parsed, lexical_occurrences=textual,
                spaced_parsed_types=spaced, lexical_outside_parsed_types=outside, contexts=dict(groups))


def scan(link, jobs):
    raw = link.read_bytes()
    binary = syntax_tool("pointer-contexts", rebuild=True)
    frequencies = defaultdict(Counter)
    lexical = {}
    with TemporaryDirectory() as temp:
        folder = Path(temp)

        def collect(archive, module, checksum, data):
            key = checksum.hex()
            package = archive.relative_to("work/analysis").parts[0]
            frequencies[package][key] += 1
            if key not in lexical:
                if sha256(data).hexdigest() != key:
                    raise ValueError(f"unrecognized compiler input {archive}/{module}")
                lexical[key] = len(METRICS["raw_pointer_type_tokens"].findall(data))
                (folder / key).write_bytes(data)

        inventory = measure(json.loads(raw), inspect_module=collect, include_standalone_modules=True)

        def examine(keys):
            output = subprocess.check_output([binary, folder], input=json.dumps(keys).encode())
            rows = json.loads(output)
            if rows.keys() != set(keys):
                raise ValueError("parser missed a source file")
            return rows

        keys = sorted(lexical)
        batches = [keys[start:start+32] for start in range(0,len(keys),32)]
        profiles = {}
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for rows in pool.map(examine, batches):
                profiles.update(rows)

    all_copies = Counter()
    packages = {}
    for name, copies in frequencies.items():
        packages[name] = summarize(copies, profiles, lexical)
        all_copies.update(copies)
        if packages[name]["lexical_occurrences"] != inventory["packages"][name]["raw_pointer_type_tokens"]:
            raise ValueError("package token inventory differs for " + name)
    total = summarize(all_copies, profiles, lexical)
    unique = summarize(dict.fromkeys(all_copies, 1), profiles, lexical)
    if (total["lexical_occurrences"] != inventory["all"]["raw_pointer_type_tokens"]
            or unique["lexical_occurrences"] != inventory["counting_identical_files_once"]["raw_pointer_type_tokens"]
            or total["files"] != inventory["all"]["files"] or unique["files"] != inventory["unique_files"]
            or link.read_bytes() != raw):
        raise ValueError("syntax inventory and release source inventory differ")
    return dict(binary_sha256=inventory["binary_sha256"], link_report_sha256=sha256(raw).hexdigest(),
                syntax_source_sha256=digest(ROOT / "tools/private-inlines/src/bin/pointer-contexts.rs"),
                all=total, counting_identical_files_once=unique, packages=packages)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("--jobs", type=int, default=4)
    args = p.parse_args()
    if args.jobs <= 0:
        p.error("--jobs must be positive")
    print(json.dumps(scan(args.link,args.jobs),sort_keys=True,indent=2))
