#!/usr/bin/env python3
"""Compare the bounded Zstd generator with GCC and Clang, including uninitialized output and short writes."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import measure
from build_zstd_lorem import CANONICAL, C_SHA, MODULE, substitute
from cargo_archive_pilot import verify_source_substitution
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import digest


def check(link, pilot, scratch):
    release = json.loads(link.read_bytes())
    key, = [k for k in release["source_library_sha256"] if k.endswith("/libzstd_1_5_7_normalized_audit.a")]
    parent = ROOT / key
    if digest(parent) != release["source_library_sha256"][key] or digest(CANONICAL) != C_SHA:
        raise ValueError("Zstd archive or canonical source changed")
    hashes = {}
    def collect(archive, module, checksum, data):
        if archive != Path(key) or str(module) in hashes:
            raise ValueError("unexpected compiled module")
        hashes[str(module)] = checksum.hex()
        if str(module) == MODULE:
            source = scratch / module
            source.parent.mkdir(parents=True)
            source.write_bytes(data)
    measure(release, inspect_module=collect, archive_pair=(cargo_origin(release, key), Path(key)))
    replacements, facts = substitute(scratch, hashes)
    if pilot is None:
        source = scratch / "generator.rs"
        source.write_bytes(replacements[MODULE])
        candidate = scratch / "libgenerator.a"
        subprocess.run(["rustc", "--edition=2021", "--crate-type=staticlib", "-O", source, "-o", candidate], check=True)
    else:
        row = json.loads((pilot / "pilot.json").read_bytes())
        candidate = pilot / parent.name
        if (row["archive"] != key or row["candidate_sha256"] != digest(candidate) or row["control_sha256"] != digest(parent)
                or row["control_binary_sha256"] != release["binary"]["sha256"]):
            raise ValueError("pilot differs from the linked archive selection")
        verify_source_substitution(row, hashes, facts, MODULE)
        facts = row
    builds = [("gcc", "gcc", CANONICAL), ("clang", "clang-18", CANONICAL),
              ("parent", "clang-18", parent), ("candidate", "clang-18", candidate)]
    results = {}
    drivers = [ROOT / "tests/lz4-dictionary/blocks.c", Path(__file__).with_name("long-block.c")]
    for driver in drivers:
        expected = None
        for name, cc, library in builds:
            target = scratch / (name + driver.stem)
            subprocess.run([cc, "-O2", "-Wl,--gc-sections", "-I" + str(CANONICAL.parent), driver, library,
                            "-ldl", "-lm", "-pthread", "-o", target], check=True)
            run = subprocess.run([target], capture_output=True, check=True)
            short = driver == drivers[0]
            if (run.stderr != (b"2625\n" if short else b"") or (expected is not None and run.stdout != expected)
                    or (len(run.stdout) != 647605 if short else not 10000000 < len(run.stdout) < 10100000)):
                raise ValueError(("Zstd output differs", name, driver.name, len(run.stdout), run.stderr))
            expected = run.stdout
            if not short:
                invalid = subprocess.run([target, "assert-size"], cwd=scratch, capture_output=True)
                if invalid.returncode != -signal.SIGABRT or b"size < INT_MAX" not in invalid.stderr:
                    raise ValueError(("unexpected size assertion", name, invalid.returncode, invalid.stderr))
                if name == "parent":
                    parent_diagnostic = invalid.stderr.split(b": ", 1)[-1]
                if name == "candidate" and invalid.stderr.split(b": ", 1)[-1] != parent_diagnostic:
                    raise ValueError("translated C assertion changed")
        log = scratch / "memcheck.log"
        checked = subprocess.run(["valgrind", "--leak-check=full", "--error-exitcode=91", f"--log-file={log}", target],
                                 capture_output=True, check=True)
        if checked.stdout != expected or checked.stderr != run.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("Zstd generator differs under Memcheck")
        results[driver.name] = dict(bytes=len(expected), sha256=sha256(expected).hexdigest(), driver_sha256=digest(driver))
    return dict(facts, archive_pilot=pilot is not None, replayed_sources=len(hashes), boundary_cases=2625,
                public_generators=2, memcheck_runs=2, comparisons=results)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    args = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(check(args.link, args.pilot, Path(tmp)), indent=2, sort_keys=True))
