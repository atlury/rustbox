#!/usr/bin/env python3
"""Compare GCC, Clang and Rust on the two E2fsprogs xattr hash entry points."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_e2fsprogs_xattr_hash import SOURCE, HELPER, substitute
from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import direct_receipt
from test_e2fsprogs_bitmap_bits import companion_objects, IMAGE, VOLUME

sys.path.insert(0, str(ROOT / "tests/e2fsprogs-xattr-hash"))
from xattr_image_checks import compare as compare_images

FIXTURE = ROOT / "tests/e2fsprogs-xattr-hash"
ENTRIES = ("ext2fs_ext_attr_hash_entry", "ext2fs_ext_attr_hash_entry_signed")


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def oracle(cc, tag, output):
    headers = Path("/oracle") / ("oracle-" + cc) / "lib"
    lib = SOURCE.parents[1]
    includes = ["-I" + str(p) for p in (headers, headers / "ext2fs", lib, SOURCE.parent)]
    full = output / (tag + "-upstream.o")
    live = output / (tag + "-hash.o")
    run(cc, "-O2", "-ffunction-sections", "-fdata-sections", *includes, "-c", SOURCE, "-o", full)
    # Keep precisely the two original C functions so the complete Rust archive
    # can be linked alongside both independently compiled oracles.
    run("ld", "-r", "--gc-sections", "-u", ENTRIES[0], "-u", ENTRIES[1], full, "-o", live)
    for symbol, suffix in zip(ENTRIES, ("unsigned", "signed")):
        run("objcopy", "--redefine-sym", f"{symbol}={tag}_{suffix}", live)
    defined = run("nm", "-g", "--defined-only", live, capture_output=True, text=True).stdout
    if {line.split()[-1] for line in defined.splitlines()} != {tag+"_unsigned", tag+"_signed"}:
        raise ValueError("unexpected canonical symbols in the comparison")
    return includes, live


def debugfs_images(stage, targets=None, *, multicall=None, oracle_root=Path("/oracle")):
    programs = {cc: [oracle_root / ("stage-" + cc) / "sbin/debugfs"] for cc in ("gcc", "clang-18")}
    if multicall is not None:
        alias = stage / "debugfs"
        alias.symlink_to(multicall)
        programs.update(applet=[alias], subcommand=[multicall, "debugfs"])
    for name in ("control", "candidate") if targets else ():
        dest = stage / (name + "-bin")
        dest.mkdir()
        program = dest / "debugfs"
        run("clang-18", "-O2", "-Wl,--gc-sections", "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_debugfs_main",
            ROOT / "bridges/e2fsprogs_program_main.c", *targets[name], "-lblkid", "-luuid", "-lfuse3", "-ldl",
            "-lpthread", "-lm", "-o", program)
        programs[name] = [program]
    return compare_images(stage, programs, oracle_root / "stage-gcc/sbin")


def verify(link, pilot):
    with TemporaryDirectory() as temp:
        stage = Path(temp)
        includes, gcc = oracle("gcc", "gcc", stage)
        _, clang = oracle("clang-18", "clang", stage)
        probe = stage / "probe.o"
        run("rustc", "--edition=2021", "--crate-type=lib", "--emit=obj", "-Copt-level=2", "-Cpanic=abort",
            "-Dunsafe-op-in-unsafe-fn", FIXTURE/"probe.rs", "-o", probe)
        targets = {"standalone": [probe]}
        evidence = dict(canonical_sha256=digest(SOURCE), helper_sha256=digest(HELPER),
                        driver_sha256=digest(FIXTURE/"compare.c"), oracle_sha256={"gcc":digest(gcc), "clang":digest(clang)})
        if pilot:
            release = json.loads(link.read_bytes())
            row = json.loads((pilot/"pilot.json").read_bytes())
            key = row["archive"]
            control, candidate = ROOT/key, pilot/Path(key).name
            if (row["control_binary_sha256"] != release["binary"]["sha256"]
                    or row["control_sha256"] != release["source_library_sha256"][key]
                    or (digest(control), digest(candidate)) != (row["control_sha256"], row["candidate_sha256"])
                    or row["helper_sha256"] != digest(HELPER) or row["canonical_sha256"] != digest(SOURCE)):
                raise ValueError("unrecognized archive or source inputs")
            companions = companion_objects(release)
            targets.update(control=[control,*companions], candidate=[candidate,*companions])
            evidence.update(archive=row, link_sha256=digest(link))
        reference = None
        executables = {}
        for name, objects in targets.items():
            exe = stage / name
            run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", *includes, FIXTURE/"compare.c", gcc, clang, *objects,
                "-Wl,--gc-sections", "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm", "-o", exe)
            result = run(exe, capture_output=True)
            if result.stderr or not re.fullmatch(rb"280576 hashes matched [0-9a-f]{16}\n", result.stdout):
                raise ValueError(f"unexpected {name} hash comparison: {result.stdout!r}")
            if reference is not None and reference != result.stdout:
                raise ValueError("archive hashes differ from the standalone comparison")
            reference = result.stdout
            executables[name] = digest(exe)
        tested = stage / ("candidate" if pilot else "standalone")
        log = stage / "memcheck.log"
        result = run("valgrind", "--tool=memcheck", "--leak-check=full", "--error-exitcode=99", "--log-file="+str(log),
                     tested, capture_output=True)
        if result.stdout != reference or result.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("instrumented xattr hash comparison failed")
        if pilot and Path(key).name == "libdebugfs_audit.a":
            evidence["filesystem"] = debugfs_images(stage, targets)
        return dict(evidence, comparisons=int(reference.split()[0]), fingerprint=reference.split()[-1].decode(),
                    memcheck_runs=1, executable_sha256=executables)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--canonical-images", action="store_true")
    p.add_argument("--mounted", action="store_true")
    p.add_argument("--link", type=Path)
    p.add_argument("--pilot", type=Path)
    a = p.parse_args()
    if a.canonical_images and a.pilot:
        p.error("use a separate invocation for the canonical image baseline")
    if bool(a.link) != bool(a.pilot):
        p.error("supply both --link and --pilot")
    if a.mounted:
        if a.canonical_images:
            with TemporaryDirectory() as folder:
                result = debugfs_images(Path(folder))
        else:
            result = verify(a.link, a.pilot)
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        args = ["--canonical-images"] if a.canonical_images else []
        if a.pilot:
            row = json.loads((a.pilot/"pilot.json").read_bytes())
            key = row["archive"]
            replay = direct_receipt(a.link, key, substitute)
            if dict(replay, candidate_sha256=digest(a.pilot/Path(key).name)) != row:
                raise ValueError("independent compiler input replay differs")
            args = ["--link", Path("/work")/a.link.resolve().relative_to(ROOT),
                    "--pilot", Path("/work")/a.pilot.resolve().relative_to(ROOT)]
        run("docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64", "-v", f"{ROOT}:/work:ro",
            "-v", VOLUME+":/oracle:ro", "-w", "/tmp", IMAGE, "python3", "-B", "/work/scripts/"+Path(__file__).name,
            "--mounted", *args)
