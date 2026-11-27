#!/usr/bin/env python3
"""Check Zstd's private repeat-offset selector and all three external sequence encoders on Linux."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import json
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_checked_errno import replay
from build_zstd_rep_offsets import ARCHIVE, CANONICAL, MODULE, substitute
from check_cargo_private_inlines import digest


def compare(parent, pilot, tmp):
    def probe(crate, sources):
        changed, facts = substitute(crate, sources)
        data = changed[MODULE]
        start = data.index(b"fn ZSTD_finalizeOffBase(")
        helper = data[start:data.index(b"\n}", start) + 2]
        if sha256(helper).hexdigest() != facts["helper_sha256"]:
            raise ValueError("Rust helper differs from the compiled archive selection")
        constants = [re.search(rb"^pub const " + name + rb":.*?;$", data, re.M)[0] for name in
                     (b"ZSTD_REP_NUM", b"REPCODE1_TO_OFFBASE", b"REPCODE3_TO_OFFBASE")]
        (tmp / "probe.rs").write_bytes(b"#![allow(non_snake_case,unused_mut)]\ntype U32 = u32;\n"
            + b"\n".join(constants) + b"\n#[forbid(unsafe_code)]\n" + helper + b"""
#[no_mangle]
pub extern "C" fn rust_repeat_offset(raw: u32, a: u32, b: u32, c: u32, ll: u32) -> u32 {
    ZSTD_finalizeOffBase(raw, &[a,b,c], ll)
}
""")
        return changed, facts

    row = replay(parent, ARCHIVE, pilot, transform=probe)
    channel = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    subprocess.run(["rustc", "+" + channel, "--edition=2021", "-O", "--crate-type=staticlib",
                    "probe.rs", "-o", "probe.a"], cwd=tmp, check=True)
    observed = {}
    objects = {}
    reference = None
    for target in ("gcc", "clang", "control", "candidate"):
        cc = "gcc" if target == "gcc" else "clang-18"
        if target in ("gcc", "clang"):
            oracle = ROOT / f"work/analysis/zstd-1.5.7/oracle/{target}-compile-commands.json"
            library = [Path(r["output"]) for r in json.loads(oracle.read_bytes()) if "/lib/" in r["file"]]
            if not library or len(library) != len(set(library)):
                raise ValueError("incomplete Zstd compile database")
            objects[target] = {p.name: digest(p) for p in library}
            subprocess.run([cc, "-O2", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                            "-I", CANONICAL.parent, HERE / "helper.c", "probe.a", "-o", "helper"], cwd=tmp, check=True)
            if subprocess.check_output([tmp / "helper"]).strip() != b"131072":
                raise ValueError("unexpected number of repeat-offset combinations")
        else:
            library = [ROOT / ARCHIVE if target == "control" else pilot / Path(ARCHIVE).name]
        exe = tmp / target
        subprocess.run([cc, "-O2", "-I", CANONICAL.parent.parent, HERE / "sequences.c", *library,
                        "-Wl,--gc-sections", "-lpthread", "-lm", "-ldl", "-lrt", "-lutil", "-o", exe], check=True)
        output = subprocess.check_output([exe])
        if target == "gcc":
            reference = output
        if output != reference:
            raise ValueError(f"{target} produced different compressed frames")
        offset = 0
        for _ in range(72):
            n = int.from_bytes(output[offset:offset+4], "little")
            if n == 0 or offset + 4 + n > len(output):
                raise ValueError("truncated sequence test output")
            offset += 4 + n
        if offset != len(output):
            raise ValueError("wrong compressed frame count")
        observed[target] = sha256(output).hexdigest()
    memlog = tmp / "memcheck.log"
    checked = subprocess.check_output(["valgrind", "--error-exitcode=99", "--leak-check=full",
        "--errors-for-leak-kinds=definite,indirect,possible", "--log-file=" + str(memlog), tmp / "candidate"])
    if checked != reference or "ERROR SUMMARY: 0 errors" not in memlog.read_text():
        raise ValueError("instrumented candidate differs")
    return dict(archive=row, helper_comparisons_per_compiler=131072, sequence_frames_per_target=72,
                framed_output_sha256=observed, canonical_library_objects=objects, candidate_memcheck_runs=1,
                driver_sha256={name:digest(HERE / name) for name in ("helper.c", "sequences.c", "compare.py")})


if __name__ == "__main__":
    with TemporaryDirectory() as scratch:
        print(json.dumps(compare(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(scratch)),
                         indent=2, sort_keys=True))
