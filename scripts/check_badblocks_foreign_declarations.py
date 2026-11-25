#!/usr/bin/env python3
"""Trial compiler-selected foreign declaration removal on the linked badblocks source."""
# SPDX-License-Identifier: 0BSD
import argparse
import contextlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from audit_linked_pointers import ROOT, crate_for
from check_cargo_private_inlines import digest
from check_e2fsprogs_private_inlines import compiler, verify_badblocks
from check_next_inline_layer import apply_receipt, read_second_layer
from inline_source_layout import pad_removed_items
from prune_private_inlines import replay


def trial(link_path, scratch):
    link = json.loads(link_path.read_bytes())
    relative, = (Path(name) for name in link["source_library_sha256"]
                 if name.endswith("/rustbox-e2fsprogs-shared/badblocks/libbadblocks_audit.a"))
    archive = ROOT / relative
    expected = link["source_library_sha256"][str(relative)]
    manifest = json.loads(archive.with_suffix(".sources.json").read_bytes())
    if digest(archive) != expected or manifest["archive_sha256"] != expected:
        raise ValueError("badblocks archive differs from the selected link")
    source = crate_for(archive, scratch)
    inputs = set(manifest["sources"])
    if any(digest(source / name) != sha for name, sha in manifest["sources"].items()):
        raise ValueError("staged input differs from the compiler manifest")
    parent = link["linked_private_inline_proofs"][str(relative)]
    receipt = archive.with_name(parent["file"])
    if digest(receipt) != parent["sha256"]:
        raise ValueError("badblocks parent receipt differs from the selected link")
    apply_receipt(source, json.loads(receipt.read_bytes()), inputs)
    if second := link.get("linked_second_inline_proofs", {}).get(str(relative)):
        record = read_second_layer(archive, relative, second, parent, expected)
        apply_receipt(source, record["second_layer"], inputs)

    deps = archive.parents[2] / "cargo-target/badblocks/release/deps"
    rustc = [*compiler(source, deps, scratch, "/rustbox-e2fsprogs"), "--crate-type=staticlib"]
    staged = scratch / archive.name
    depfile = scratch / "compiler.d"

    def build():
        subprocess.run([*rustc, "--cap-lints=allow", f"--emit=link,dep-info={depfile}",
                        "lib.rs", "-o", staged], cwd=source, check=True)
        rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
        if {p for p in shlex.split(rule) if p.endswith(".rs")} != inputs:
            raise ValueError("compiler-selected input list changed")
        return digest(staged)

    if build() != expected:
        raise ValueError("control build differs from the released badblocks archive")
    diagnostics = scratch / "rustc.jsonl"
    with diagnostics.open("wb") as stream:
        subprocess.run([*rustc, "--emit=metadata", "-A", "warnings", "--force-warn", "dead_code",
                        "--error-format=json", "lib.rs", "-o", scratch / "badblocks.rmeta"],
                       cwd=source, stderr=stream, check=True)
    selector = ROOT / "work/analysis/private-inlines-linux/release/foreign-declarations"
    with diagnostics.open("rb") as stream:
        ranges = json.loads(subprocess.check_output([selector], cwd=source, stdin=stream))
    if not ranges or not ranges.keys() <= inputs:
        raise ValueError("expected declarations in compiler-selected files")
    originals = {name: (source / name).read_bytes() for name in ranges}
    removed = replay(source, ranges)
    layout = "lines"
    if build() != expected:
        pad_removed_items(source, ranges, originals)
        layout = "byte_offsets"
        if build() != expected:
            raise ValueError("declaration removal changed the archive")
    objects = [archive.parents[1] / f"{name}.o" for name in ("crc16", "crc32", "bitcount")]
    for obj in objects:
        if digest(obj) != link["source_library_sha256"][str(obj.relative_to(ROOT))]:
            raise ValueError(f"shared object differs from release: {obj}")
    for name, library in (("original", archive), ("trimmed", staged)):
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections",
                        "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_badblocks_main",
                        ROOT / "bridges/e2fsprogs_program_main.c", library, *objects,
                        "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm",
                        "-o", scratch / name], check=True)
    with contextlib.redirect_stdout(sys.stderr):
        verify_badblocks(scratch)
    return {"archive": str(relative), "archive_sha256": expected, "link_report_sha256": digest(link_path),
            "selector_sha256": digest(selector), "source_layout": layout, "changed_files": len(ranges),
            "declarations_removed": sum(map(len, ranges.values())), "raw_pointer_type_tokens_removed": removed,
            "source_bytes_removed": sum(len(data) - (source / n).stat().st_size for n, data in originals.items()),
            "canonical_comparisons_passed": 4}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(trial(args.link_report, Path(tmp)), indent=2, sort_keys=True))
