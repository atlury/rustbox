#!/usr/bin/env python3
"""Compare E2fsprogs error names, caller-visible errno and returned storage against canonical C."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "work/analysis/e2fsprogs-1.47.4"
ENGINES = ("debugfs", "dumpe2fs", "tune2fs")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check(link, batch, stage):
    release = json.loads(link.read_bytes())
    driver = Path(__file__).with_name("compare.c")
    sources = {}
    objects = {}
    for cc in ("gcc", "clang-18"):
        db = json.loads((PACKAGE / f"oracle/{cc}-compile-commands.json").read_bytes())
        row, = [r for r in db if r["file"].endswith("/lib/e2p/errcode.c")]
        source = Path(row["file"])
        if digest(source) != "c0a5a9e6690e0686b2d06ea4960eadcebb89ee61c5a77c7df136b3fe8c1836a4":
            raise ValueError("canonical E2fsprogs source differs")
        flags = row["arguments"].copy()
        obj = stage / (cc + ".o")
        flags[flags.index("-o") + 1] = str(obj)
        subprocess.run(flags, cwd=row["directory"], check=True)
        objects[cc] = obj
        sources[cc] = digest(source)
    selection = {}
    for engine in ENGINES:
        key, = [k for k in release["source_library_sha256"] if Path(k).name == f"lib{engine}_audit.a"]
        parent = ROOT / key
        if digest(parent) != release["source_library_sha256"][key]:
            raise ValueError(f"selected {engine} archive differs")
        objects[engine + "-parent"] = parent
        if batch:
            row = json.loads((batch / engine / "pilot.json").read_bytes())
            candidate = batch / engine / parent.name
            if (row["archive"] != key or row["candidate_sha256"] != digest(candidate)
                    or row["control_sha256"] != digest(parent) or row["control_binary_sha256"] != release["binary"]["sha256"]):
                raise ValueError(f"unexpected {engine} candidate")
            objects[engine + "-candidate"] = candidate
            selection[engine] = row

    hashes = {}
    outputs = {}
    for name, obj in objects.items():
        program = stage / name
        shared = PACKAGE / "program-translations/rustbox-e2fsprogs-shared"
        support = ([shared / n for n in ("crc16.o", "crc32.o", "bitcount.o")] + ["-lblkid", "-luuid", "-lfuse3"]
                   if obj.suffix == ".a" else [])
        subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-Wl,--gc-sections",
                        driver, obj, *support, "-lm", "-ldl", "-lpthread", "-o", program], check=True)
        log = stage / (name + ".memcheck")
        result = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect",
                                 "--log-file=" + str(log), program], capture_output=True, check=True, timeout=180)
        lines = result.stdout.splitlines()
        if (result.stderr or len(lines) != 18 + 4096 + 18 or lines[:18] != lines[-18:]
                or lines[:3] != [b"", b"UNKNOWN", b"EIO"] or "ERROR SUMMARY: 0 errors" not in log.read_text()):
            raise ValueError(f"incorrect error strings or memory behavior for {name}")
        outputs[name] = sha256(result.stdout).hexdigest()
        hashes[name] = digest(obj)
    if len(set(outputs.values())) != 1:
        raise ValueError("error-code output differs between compilers or archives")
    return dict(canonical_sources=sources, archive_checks=selection, input_sha256=hashes, stdout_sha256=outputs["gcc"],
                driver_sha256=digest(driver), defined_codes_per_build=18, fallback_calls_per_build=4096, memcheck_runs=len(objects))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("batch", type=Path, nargs="?")
    a = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(check(a.link, a.batch, Path(tmp)), indent=2, sort_keys=True))
