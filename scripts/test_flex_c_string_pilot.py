#!/usr/bin/env python3
"""Exercise the Flex archive with checked C literals through canonical scanner and frontend tests."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest


def compare(pilot, parent):
    release = json.loads(parent.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = Path(row["archive"])
    reference = Path("/rustbox-flex/normalized-gcc/src/flex")
    source = Path("/rustbox-flex/normalized-source")
    if (row["control_binary_sha256"] != release["binary"]["sha256"] or row["control_sha256"] != release["source_library_sha256"][str(key)]
            or digest(ROOT / key) != row["control_sha256"] or digest(pilot / key.name) != row["candidate_sha256"]
            or row["c_string_literals"] != sum(row["modules"].values()) or row["raw_pointer_types_removed"] != 2 * row["c_string_literals"]):
        raise ValueError("unexpected Flex archives, compiler receipt or parent release")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        binary_sha = {}
        for variant, archive in (("parent", ROOT / key), ("candidate", pilot / key.name)):
            folder = root / variant
            folder.mkdir()
            binary = folder / "flex"
            subprocess.run(["clang-18", "-O2", "-g", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                            "-o", binary, ROOT / "bridges/flex_main.c", archive, "-ldl", "-lpthread", "-lm"], check=True)
            for alias in ("flex++", "lex"):
                (folder / alias).symlink_to(binary.name)
            binary_sha[variant] = digest(binary)
        reports = {}
        for name, script, args in (("scanners", "flex-oracle-differential.py", ["--gcc", reference, "--clang", binary]),
                                   ("frontends", "flex-hybrid-frontends.py", ["--canonical", reference, "--hybrid", binary])):
            output = root / (name + ".json")
            subprocess.run(["python3", ROOT / "tests" / script, *args, "--source", source, "--output", output],
                           check=True, stdout=subprocess.DEVNULL)
            result = json.loads(output.read_bytes())
            if result["passed"] != result["cases"] or result["cases"] == 0:
                raise ValueError(f"incomplete Flex {name} comparison")
            reports[name] = {k: result[k] for k in ("passed", "cases", "generated_scanners") if k in result}
            reports[name]["driver_sha256"] = digest(ROOT / "tests" / script)
            reports[name]["results_sha256"] = digest(output)
        spec = b"%option noyywrap\n%%\n[[:alpha:]]+ ECHO;\n\\n ECHO;\n%%\n"
        cases = [(["--help"], b""), (["--version"], b""), (["--definitely-invalid"], b""), (["-t"], spec)]
        for args, stdin in cases:
            # Keep argv[0] identical for command diagnostics.
            expected = subprocess.run(["flex", *args], executable=reference, input=stdin, capture_output=True, cwd=root)
            actual = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=no", "--log-file=check.log",
                                     "flex", *args], input=stdin, capture_output=True, cwd=root,
                                    env=dict(os.environ, PATH=str(binary.parent) + os.pathsep + os.environ["PATH"]))
            if ((actual.returncode, actual.stdout) != (expected.returncode, expected.stdout)
                    or b"ERROR SUMMARY: 0 errors" not in (root / "check.log").read_bytes()):
                raise ValueError(f"Flex Memcheck or public output mismatch for {args}")
            if actual.stderr != expected.stderr:
                raise ValueError(f"Flex diagnostic mismatch for {args}")
        return dict(row, standalone_sha256=binary_sha, gcc_flex_sha256=digest(reference), memcheck_runs=len(cases), **reports)


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
                        "-v", f"{args.link.resolve(strict=True)}:/parent.json:ro", "-v", "rustbox-flex-2.6.4:/rustbox-flex:ro",
                        "-e", "LC_ALL=C", "-e", "TZ=UTC", "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/test_flex_c_string_pilot.py", "--mounted", "/pilot", "/parent.json"], check=True)
