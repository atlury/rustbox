#!/usr/bin/env python3
"""Cold-build and compare the six bitmap operations across every selected E2fsprogs engine."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from build_e2fsprogs_bitmap_bits import build
from check_cargo_private_inlines import ROOT, digest


def save(path, record):
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")
    Path(f.name).replace(path)


def qualify(link, ranking, output, engines):
    original = digest(link)
    evidence = json.loads(ranking.read_bytes())
    release = json.loads(link.read_bytes())
    if evidence["link_sha256"] != original or evidence["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("expected the matching compiler-source inventory")
    output.mkdir(parents=True, exist_ok=True)
    selected = {k:v for k,v in evidence["archives"].items() if not engines or Path(k).name in engines}
    if not selected or engines - {Path(k).name for k in selected}:
        raise ValueError("unknown bitmap engine")
    rows = {}
    for key, expected in sorted(selected.items()):
        directory = output / Path(key).stem
        with directory.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not directory.exists():
                build(link, key, directory)
            # Recheck the current archive, compiler-selected source bytes and native oracles.
            cmd = [sys.executable, "-B", ROOT/"scripts/test_e2fsprogs_bitmap_bits.py",
                   "--link", link, "--pilot", directory]
            row = json.loads(subprocess.check_output(cmd))
            archive = row["archive"]
            if (archive["archive"] != key or archive["control_sha256"] != expected["archive_sha256"]
                    or any(archive[k] != v for k,v in expected.items() if k != "archive_sha256")
                    or row["comparisons"] != 393260 or row["memcheck_runs"] != 1):
                raise ValueError(f"behavior or source substitution differs for {key}")
            save(directory/"comparison.json", row)
            rows[key] = row
            print(f'{Path(key).name} passed both canonical compilers and Memcheck', file=sys.stderr, flush=True)
    if digest(link) != original:
        raise ValueError("compiler release changed during bitmap qualification")
    return dict(link_sha256=original, inventory_sha256=digest(ranking), archived_results=rows,
                raw_pointer_types_removed=sum(r["archive"]["raw_pointer_types_removed"] for r in rows.values()),
                comparisons=sum(r["comparisons"] for r in rows.values()), memcheck_runs=len(rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("inventory", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--archive", action="append", default=[], help="limit qualification to this archive basename")
    a = p.parse_args()
    print(json.dumps(qualify(a.link,a.inventory,a.output,set(a.archive)),indent=2,sort_keys=True))
