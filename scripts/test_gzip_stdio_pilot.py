#!/usr/bin/env python3
"""Compare a complete gzip archive with GNU gzip and check glibc ABI for layout candidates."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest, layout
from share_stdio_layout import ALIASES, GZIP_OWNER, declarations


def abi_probe(owner, tmp):
    defs = declarations(owner.read_bytes())
    fields = re.findall(rb"^    pub (\w+): (.*),$", defs["_IO_FILE"][0], re.M)
    c = ["#include <stddef.h>", "#include <stdio.h>", "int main(void) {",
         'printf("%zu %zu\\n", sizeof(FILE), _Alignof(FILE));']
    rust = [s.decode() for s in ALIASES] + [s[0].decode() for s in defs.values()]
    rust += ["use std::mem::{align_of,offset_of,size_of};", "fn main(){",
             'println!("{} {}", size_of::<_IO_FILE>(), align_of::<_IO_FILE>());']
    for key, value in fields:
        field, typ = key.decode(), value.decode()
        c.append(f'printf("{field} %zu %zu\\n", offsetof(FILE, {field}), sizeof(((FILE*)0)->{field}));')
        rust.append(f'println!("{field} {{}} {{}}", offset_of!(_IO_FILE, {field}), size_of::<{typ}>());')
    (tmp / "layout.c").write_text("\n".join([*c, "}"]))
    (tmp / "layout.rs").write_text("\n".join([*rust, "}"]))
    subprocess.run(["cc", "layout.c", "-o", "c-layout"], cwd=tmp, check=True)
    subprocess.run(["rustc", "+1.99.0", "--edition=2021", "-Awarnings", "layout.rs", "-o", "rs-layout"], cwd=tmp, check=True)
    canonical = subprocess.check_output([tmp / "c-layout"])
    if canonical != subprocess.check_output([tmp / "rs-layout"]) or len(canonical.splitlines()) != 1 + len(fields):
        raise ValueError("glibc FILE and Rust differ in size, alignment or field offsets and widths")
    return dict(fields=len(fields), bytes=int(canonical.split()[0]), alignment=int(canonical.split()[1]),
                sha256=hashlib.sha256(canonical).hexdigest())


def compare(pilot, link):
    row = json.loads((pilot / "pilot.json").read_bytes())
    archive = Path(row["archive"])
    src, _ = layout(archive)
    release = json.loads(link.read_bytes())
    if (release["binary"]["sha256"] != row["control_binary_sha256"]
            or release["source_library_sha256"][str(archive)] != row["control_sha256"]
            or digest(ROOT / archive) != row["control_sha256"] or digest(pilot / archive.name) != row["candidate_sha256"]):
        raise ValueError("unexpected parent link, control archive or candidate")
    with TemporaryDirectory() as temp:
        tmp = Path(temp)
        extra = {}
        if "reexporting_modules" in row:
            extra["glibc_file"] = abi_probe(ROOT / src / GZIP_OWNER, tmp)
        elif (row["c_string_literals"] != sum(row["modules"].values())
              or row["raw_pointer_types_removed"] != 2 * row["c_string_literals"]
              or row["raw_ffi_pointer_extractions"] != row["c_string_literals"]):
            raise ValueError("unexpected C-string pilot receipt")
        canonical = Path("/rustbox-gzip/normalized-install-gcc/usr/bin")
        support = Path("/rustbox-gzip/normalized-clang/lib/libgzip.a")
        variants = []
        binaries = {}
        for name, lib in (("parent", ROOT / archive), ("candidate", pilot / archive.name)):
            folder = tmp / name
            shutil.copytree(canonical, folder, symlinks=True)
            binary = folder / "gzip"
            binary.unlink()
            subprocess.run(["clang-18", "-O2", "-g", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                            "-o", binary, ROOT / "bridges/gzip_main.c", lib, support, "-ldl", "-lpthread", "-lm"], check=True)
            binaries[name] = digest(binary)
            variants.append(folder)
        harness = runpy.run_path(str(ROOT / "tests/gzip-oracle-differential.py"))
        cases = harness["cases"]()
        comparisons = tmp / "public"
        comparisons.mkdir()
        for case in cases:
            # gzexe and shell wrappers can print the temporary command path.
            # Compare all executables in one reproducibly reset directory.
            expected = harness["invoke"](canonical, case, comparisons)
            for folder in variants:
                if harness["invoke"](folder, case, comparisons) != expected:
                    raise ValueError(f"{folder.name} differs from canonical gzip for {case.name}")
        payload = bytes(range(256)) * 1024
        compressed = subprocess.check_output([canonical / "gzip", "-n", "-9c"], input=payload)
        checks = 0
        for flags, content, expected in [(["-n", "-9c"], payload, compressed), (["-dc"], compressed, payload)]:
            report = tmp / "memcheck"
            actual = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=full", f"--log-file={report}",
                                     tmp / "candidate/gzip", *flags], input=content, capture_output=True, check=True)
            log = report.read_text()
            if actual.stdout != expected or actual.stderr or "ERROR SUMMARY: 0 errors" not in log or "All heap blocks were freed" not in log:
                raise ValueError("candidate Memcheck or stdout differed from canonical gzip")
            checks += 1
        return dict(row, **extra, standalone_sha256=binaries, memcheck_runs=checks,
                    public_cases=len(cases), case_names=[case.name for case in cases],
                    differential_driver_sha256=digest(ROOT / "tests/gzip-oracle-differential.py"),
                    gcc_gzip_sha256=digest(canonical / "gzip"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("link", type=Path)
    parser.add_argument("--mounted", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        print(json.dumps(compare(args.pilot, args.link), indent=2, sort_keys=True))
    else:
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{args.pilot.resolve(strict=True)}:/pilot:ro",
                        "-v", f"{args.link.resolve(strict=True)}:/parent.json:ro", "-v", "rustbox-gzip-1.14:/rustbox-gzip:ro",
                        "-e", "LC_ALL=C", "-e", "TZ=UTC", "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/test_gzip_stdio_pilot.py", "--mounted", "/pilot", "/parent.json"], check=True)
