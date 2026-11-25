#!/usr/bin/env python3
"""Compare a rebuilt Bison engine to both canonical C compilers, including generated parsers."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest


def compare_parsers(work, pkg, bison, yacc_binary, *, embedded=False, bare_name=False):
    embed_bison = ["--right-embedded"] if embedded else []
    if bare_name:
        embed_bison.append("--bare-program-name")
    embed_yacc = ["--hybrid-embedded"] if embedded else []
    data = pkg / "normalized/clang-root/usr/share/bison"
    comparisons = {}
    for compiler in ("gcc", "clang"):
        oracle = pkg / "oracle" / (compiler + "-root") / "usr"
        result = work / (compiler + ".json")
        subprocess.run(["python3", ROOT / "tests/bison-oracle-differential.py",
                        "--gcc", oracle / "bin/bison", "--gcc-datadir", oracle / "share/bison",
                        "--clang", bison, "--clang-datadir", data, "--source", ROOT / "work/upstream/bison-3.8.2",
                        "--output", result, *embed_bison], check=True, stdout=subprocess.DEVNULL)
        stats = json.loads(result.read_bytes())
        if stats["cases"] != 12 or stats["passed"] != 12 or stats["compiled_parsers"] != 5:
            raise ValueError("incomplete Bison oracle suite")
        subprocess.run(["python3", ROOT / "tests/bison-yacc-frontend.py",
                        "--canonical", oracle / "bin/yacc", "--canonical-datadir", oracle / "share/bison",
                        "--hybrid", yacc_binary, "--hybrid-datadir", data, "--output", result, *embed_yacc],
                       check=True, stdout=subprocess.DEVNULL)
        yacc = json.loads(result.read_bytes())
        if not yacc["passed"] or yacc["compile_status"] != 0 or yacc["runtime_status"] != 0:
            raise ValueError("failed yacc parser generation or execution")
        comparisons[compiler] = dict(bison_cases=stats["cases"], compiled_parsers=stats["compiled_parsers"],
                                     yacc_cases=1, generated_yacc_files=yacc["generated_sha256"])
    return comparisons


def check(pilot, link):
    row = json.loads((pilot / "pilot.json").read_bytes())
    archive = Path(row["archive"])
    release = json.loads(link.read_bytes())
    pkg = ROOT / "work/analysis/bison-3.8.2"
    inputs = sorted((pkg / "hybrid-artifacts/c-residue").glob("*.o"))
    if (row["control_binary_sha256"] != release["binary"]["sha256"]
            or row["control_sha256"] != release["source_library_sha256"][str(archive)]
            or digest(pilot / archive.name) != row["candidate_sha256"]
            or len(inputs) != 4 or any(digest(p) != release["source_library_sha256"][str(p.relative_to(ROOT))]
                                      for p in inputs)):
        raise ValueError("Bison candidate, C objects or release differs from the compiler receipt")
    with TemporaryDirectory() as folder:
        work = Path(folder)
        bison = work / "bison"
        subprocess.run(["clang-18", "-O2", "-g", "-fno-omit-frame-pointer", "-ffunction-sections", "-fdata-sections",
                        "-Wl,--gc-sections", "-o", bison, ROOT / "bridges/bison_main.c", *inputs, pilot / archive.name,
                        "-ldl", "-lpthread", "-lm", "-lrt"], check=True)
        (work / "yacc").symlink_to(bison.name)
        comparisons = compare_parsers(work, pkg, bison, work / "yacc")
        data = pkg / "normalized/clang-root/usr/share/bison"
        grammar = work / "sample.y"
        grammar.write_text("%token NUMBER\n%%\nstart: NUMBER;\n")
        for utility in ("bison", "yacc"):
            log = work / (utility + ".log")
            subprocess.run(["valgrind", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect,possible",
                            "--error-exitcode=99", "--log-file=" + str(log), work / utility, "-o", utility + ".c", grammar],
                           env=dict(os.environ, BISON_PKGDATADIR=str(data)), cwd=work, check=True)
            if "ERROR SUMMARY: 0 errors" not in log.read_text() or not (work / (utility + ".c")).is_file():
                raise ValueError("Memcheck or parser generation failed")
        return dict(row, canonical=comparisons, memcheck_parser_generations=2, candidate_executable_sha256=digest(bison))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("pilot", "link"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.pilot, args.link), indent=2, sort_keys=True))
