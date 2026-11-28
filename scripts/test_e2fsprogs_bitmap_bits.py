#!/usr/bin/env python3
"""Compare portable bitmap operations with GCC/Clang E2fsprogs and the selected e2fsck engine."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_e2fsprogs_bitmap_bits import HELPER, SOURCE, substitute
from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import direct_receipt

TEST = ROOT / "tests/e2fsprogs-bitmap-bits/compare.c"
IMAGE = "rustbox-e2fsprogs:2026-11-24"
VOLUME = "rustbox-e2fsprogs-1.47.4"


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def verify(link=None, pilot=None):
    lib = SOURCE.parents[1]
    row = {}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        targets = {}
        for cc in ("gcc", "clang-18"):
            obj = root / (cc+".o")
            includes = Path("/oracle") / ("oracle-"+cc) / "lib"
            run(cc, "-O2", "-DOMIT_COM_ERR", *["-I"+str(p) for p in (includes, includes/"ext2fs", lib, SOURCE.parent)],
                "-c", SOURCE, "-o", obj)
            targets[cc] = obj
        obj = root / "helper.o"
        run("rustc", "--crate-type=lib", "--edition=2021", "--emit=obj", "-Dunsafe-op-in-unsafe-fn", "-Copt-level=2",
            "-Cpanic=abort", HELPER, "-o", obj)
        targets["standalone"] = obj
        library_flags = ["-Wl,--gc-sections", "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm"]
        if pilot:
            row = json.loads((pilot / "pilot.json").read_bytes())
            key = row["archive"]
            record = json.loads(link.read_bytes())
            if (record["source_library_sha256"][key] != row["control_sha256"] or record["binary"]["sha256"] != row["control_binary_sha256"]
                    or digest(ROOT/key) != row["control_sha256"] or digest(pilot/Path(key).name) != row["candidate_sha256"]
                    or row["helper_sha256"] != digest(HELPER) or row["canonical_sha256"] != digest(SOURCE)):
                raise ValueError("bitmap archive, source, or parent ELF changed")
            targets.update(control=ROOT/key, candidate=pilot/Path(key).name)
        expected = None
        executable_hashes = {}
        for label, obj in targets.items():
            exe = root / (label+"-compare")
            run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", TEST, obj, *library_flags, "-o", exe)
            output = run(exe, capture_output=True)
            if output.stderr or not re.fullmatch(rb"393260 bitmap calls passed\n", output.stdout):
                raise ValueError((label, output.stdout, output.stderr))
            if expected is not None and expected != output.stdout:
                raise ValueError("bitmap call results differed")
            expected = output.stdout
            executable_hashes[label] = digest(exe)
        name = "candidate" if pilot else "standalone"
        log = root/"memcheck.log"
        checked = run("valgrind", "--error-exitcode=99", "--leak-check=full", "--log-file="+str(log),
                      root/(name+"-compare"), capture_output=True)
        if checked.stdout != expected or checked.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("bitmap comparison failed Memcheck")
        report = dict(comparisons=int(expected.split()[0]), memcheck_runs=1, executable_sha256=executable_hashes,
                      driver_sha256=digest(TEST), helper_sha256=digest(HELPER), canonical_sha256=digest(SOURCE))
        if pilot:
            report["archive"] = row
            if Path(key).name == "libe2fsck_audit.a":
                report["filesystem"] = compare_e2fsck(root, targets, record, library_flags)
        return report


def compare_e2fsck(root, targets, link, flags):
    canon = Path("/oracle/stage-gcc/sbin")
    tools = {"gcc": canon/"e2fsck", "clang": Path("/oracle/stage-clang-18/sbin/e2fsck")}
    shared = ROOT/"work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared"
    objects = [shared/n for n in ("crc16.o","crc32.o","bitcount.o")]
    for obj in objects:
        if digest(obj) != link["source_library_sha256"][str(obj.relative_to(ROOT))]:
            raise ValueError(f"changed E2fsprogs companion object {obj.name}")
    for label in ("control","candidate"):
        directory = root/label
        directory.mkdir()
        exe = directory/"e2fsck"
        run("clang-18", "-O2", "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_e2fsck_main",
            ROOT/"bridges/e2fsprogs_program_main.c", targets[label], *objects, *flags, "-o", exe)
        tools[label] = exe
    env = dict(os.environ, LC_ALL="C", TZ="UTC", E2FSCK_TIME="1700000000", E2FSPROGS_FAKE_TIME="1700000000")
    image = root/"original.img"
    with image.open("wb") as f:
        f.truncate(16*1024*1024)
    run(canon/"mke2fs", "-Fq", "-t", "ext4", "-U", "8b4a3c52-57f9-48bd-a3fc-ad988f081b0c", "-b", "1024",
        "-E", "lazy_itable_init=0,lazy_journal_init=0", image, env=env)
    expected = None
    for label, tool in tools.items():
        copy = root/("fs-"+label)
        copy.mkdir()
        shutil.copyfile(image, copy/"fs.img")
        proc = run(tool, "-fn", "fs.img", env=env, cwd=copy, capture_output=True)
        result = (proc.stdout, proc.stderr, digest(copy/"fs.img"))
        if expected is not None and expected != result:
            raise ValueError(f"{label} differed on the read-only ext4 check")
        expected = result
    if expected[2] != digest(image):
        raise ValueError("filesystem image changed during read-only check")
    return dict(compared=sorted(tools), image_unchanged=True, commands_per_program=1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", action="store_true")
    p.add_argument("--link", type=Path)
    p.add_argument("--pilot", type=Path)
    a = p.parse_args()
    if bool(a.link) != bool(a.pilot):
        p.error("supply both the compiler selection and the cold-built pilot")
    if a.mounted:
        print(json.dumps(verify(a.link,a.pilot), indent=2, sort_keys=True))
    else:
        args = []
        if a.pilot:
            row = json.loads((a.pilot/"pilot.json").read_bytes())
            reproduced = direct_receipt(a.link,row["archive"],substitute)
            if dict(reproduced,candidate_sha256=digest(a.pilot/Path(row["archive"]).name)) != row:
                raise ValueError("independent bitmap compiler replay differs")
            args = ["--link", Path("/work")/a.link.resolve().relative_to(ROOT),
                    "--pilot", Path("/work")/a.pilot.resolve().relative_to(ROOT)]
        run("docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "-v", f"{ROOT}:/work:ro", "-v", VOLUME+":/oracle:ro", "-w", "/tmp", IMAGE,
            "python3", "-B", "/work/scripts/test_e2fsprogs_bitmap_bits.py", "--mounted", *args)
