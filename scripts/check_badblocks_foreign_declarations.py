#!/usr/bin/env python3
"""Trial compiler-selected foreign declaration removal on the linked badblocks source."""
# SPDX-License-Identifier: 0BSD
import argparse
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_private_inlines import verify_badblocks
from e2fsprogs_foreign_declarations import prove


def trial(link_path, scratch):
    link = json.loads(link_path.read_bytes())
    relative, = (Path(name) for name in link["source_library_sha256"]
                 if name.endswith("/rustbox-e2fsprogs-shared/badblocks/libbadblocks_audit.a"))
    archive = ROOT / relative
    report, staged = prove(link, relative, scratch)
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
    return {key: report[key] for key in ("archive", "archive_sha256", "selector_sha256", "declarations_removed",
                                          "raw_pointer_type_tokens_removed", "source_bytes_removed")} | {
        "link_report_sha256": digest(link_path), "source_layout": report["declarations"]["source_layout"],
        "changed_files": len(report["declarations"]["sources"]), "canonical_comparisons_passed": 4}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(trial(args.link_report, Path(tmp)), indent=2, sort_keys=True))
