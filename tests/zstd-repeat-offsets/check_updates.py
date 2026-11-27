#!/usr/bin/env python3
"""Compare the shared updater with canonical Zstd and exercise the external and internal parsers."""
# SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
import json
from hashlib import sha256
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_checked_errno import replay
from build_zstd_rep_updates import ARCHIVE, HEADER, MODULE, NEW, UPDATE, substitute
from check_cargo_private_inlines import digest


def frames(data, count):
    pos = 0
    for _ in range(count):
        if pos + 4 > len(data):
            raise ValueError("missing compressed frame length")
        length, = struct.unpack_from("<I", data, pos)
        if not length or pos + 4 + length > len(data):
            raise ValueError("incomplete compressed frame")
        pos += 4 + length
    if pos != len(data):
        raise ValueError("excess bytes after compressed frames")
    return sha256(data).hexdigest()


def check(parent, pilot, tmp):
    def probe(crate, sources):
        changed, facts = substitute(crate, sources)
        opt = "src/lib/compress/zstd_opt.rs"
        layout = b"pub struct repcodes_s {\n    pub rep: [U32; 3],\n}"
        if (changed[MODULE].count(UPDATE) != 1 or changed[opt].count(NEW) != 1
                or layout not in changed[opt] or b"pub type Repcodes_t = repcodes_s;" not in changed[opt]):
            raise ValueError("test helper differs from selected optimal parser")
        (tmp / "probe.rs").write_bytes(b"#![allow(non_snake_case,non_camel_case_types)]\ntype U32=u32;\n#[repr(C)]\n"
            + layout + b"\ntype Repcodes_t=repcodes_s;\n#[forbid(unsafe_code)]\n" + UPDATE
            + b"\n#[forbid(unsafe_code)]\n" + NEW + b"""
#[no_mangle]
pub extern "C" fn rust_update(a:u32,b:u32,c:u32,off:u32,ll:u32) -> Repcodes_t {
    let mut rep = [a,b,c];
    ZSTD_updateRep(&mut rep,off,ll);
    repcodes_s {rep}
}
#[no_mangle]
pub extern "C" fn rust_new(a:u32,b:u32,c:u32,off:u32,ll:u32) -> Repcodes_t {
    ZSTD_newRep([a,b,c],off,ll)
}
""")
        return changed, facts

    row = replay(parent, ARCHIVE, pilot, transform=probe)
    preceding = ROOT / "evidence/zstd-repeat-offsets-archive.json"
    baseline = json.loads(preceding.read_bytes())
    if baseline["driver_sha256"]["sequences.c"] != digest(HERE / "sequences.c"):
        raise ValueError("external sequence driver changed")
    channel = tomllib.loads((ROOT / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    subprocess.run(["rustc", "+" + channel, "--edition=2021", "-O", "--crate-type=staticlib", "probe.rs", "-o", "probe.a"],
                   cwd=tmp, check=True)
    profiles = {}
    for target in ("gcc", "clang", "control", "candidate"):
        cc = "gcc" if target == "gcc" else "clang-18"
        if target in ("gcc", "clang"):
            db = ROOT / f"work/analysis/zstd-1.5.7/oracle/{target}-compile-commands.json"
            libraries = [Path(r["output"]) for r in json.loads(db.read_bytes()) if "/lib/" in r["file"]]
            if {p.name:digest(p) for p in libraries} != baseline["canonical_library_objects"][target]:
                raise ValueError("canonical Zstd objects changed")
            subprocess.run([cc, "-O2", "-I", HEADER.parent, HERE / "updates.c", "probe.a", "-o", "updates"], cwd=tmp, check=True)
            if subprocess.check_output([tmp / "updates"]).strip() != b"131072":
                raise ValueError("unexpected number of update or copy comparisons")
        else:
            libraries = [ROOT / ARCHIVE if target == "control" else pilot / Path(ARCHIVE).name]
        for name in ("sequences", "strategies"):
            exe = tmp / name
            subprocess.run([cc, "-O2", "-I", HEADER.parent.parent, HERE / (name + ".c"), *libraries,
                            "-Wl,--gc-sections", "-lpthread", "-lm", "-ldl", "-lrt", "-lutil", "-o", exe], check=True)
            variants = [(name, [], 72)]
            if name == "strategies":
                variants.append(("strategies-quick", ["--memcheck"], 6))
            for label, args, count in variants:
                output = subprocess.check_output([exe, *args])
                value = frames(output, count)
                if profiles.setdefault(label, value) != value:
                    raise ValueError(f"{target} {label} compressed bytes differ")
                if name == "sequences" and value != baseline["framed_output_sha256"]["gcc"]:
                    raise ValueError("external sequence frames differ from the preceding release")
                if target == "candidate" and label in ("sequences", "strategies-quick"):
                    log = tmp / (label + ".log")
                    checked = subprocess.check_output(["valgrind", "--error-exitcode=99", "--leak-check=full",
                        "--errors-for-leak-kinds=definite,indirect,possible", "--log-file=" + str(log), exe, *args])
                    if checked != output or "ERROR SUMMARY: 0 errors" not in log.read_text():
                        raise ValueError("Memcheck differs from the ordinary run")
    return dict(archive=row, previous_offset_receipt_sha256=digest(preceding),
                helper_inputs_per_compiler=131072, compared_helpers=["ZSTD_updateRep", "ZSTD_newRep"],
                frames_per_target={"sequences":72,"strategies":72}, framed_output_sha256=profiles,
                memcheck_runs=2, driver_sha256={n:digest(HERE/n) for n in ("updates.c","strategies.c","sequences.c","check_updates.py")})


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        print(json.dumps(check(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(tmp)), indent=2, sort_keys=True))
