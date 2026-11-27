#!/usr/bin/env python3
"""Link the candidate file command and compare it with both release compilers on Linux."""
# SPDX-License-Identifier: BSD-2-Clause
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from check_cargo_private_inlines import digest


def check(link, pilot):
    parent=json.loads(link.read_bytes())
    receipt=json.loads((pilot/"pilot.json").read_bytes())
    key=receipt["archive"]
    archive=pilot/Path(key).name
    if (receipt["control_binary_sha256"]!=parent["binary"]["sha256"]
            or receipt["control_sha256"]!=parent["source_library_sha256"][key]
            or digest(archive)!=receipt["candidate_sha256"]):
        raise ValueError("file candidate or linked parent changed")
    source=Path("/rustbox-file")
    magic=source/"canonical-gcc/magic/magic"
    with TemporaryDirectory() as temp:
        directory=Path(temp)
        exe=directory/"file"
        subprocess.run(["clang-18","-O2","-Wl,--gc-sections","-o",exe,ROOT/"bridges/file_main.c",archive,
                        "-lbz2","-llz","-llzma","-lseccomp","-lz","-lzstd","-ldl","-lpthread","-lm"],check=True)
        cases={}
        for compiler in ("gcc","clang"):
            result=directory/(compiler+".json")
            subprocess.run([sys.executable,ROOT/"tests/file-oracle-differential.py",
                            "--gcc",source/("canonical-"+compiler)/"src/file","--clang",exe,"--magic",magic,
                            "--upstream-tests",source/"normalized-source/tests","--output",result],check=True,stdout=subprocess.DEVNULL)
            row=json.loads(result.read_bytes())
            if not row["gcc_clang_exact"] or row["comparisons"]!=174:
                raise ValueError("incomplete file command comparison")
            cases[compiler]=row["comparisons"]
        payload=directory/"sample.gz"
        payload.write_bytes(gzip.compress(b"rustbox compression headers\n",mtime=0))
        log=directory/"valgrind.log"
        subprocess.run(["valgrind","--leak-check=full","--errors-for-leak-kinds=definite,indirect,possible",
                        "--error-exitcode=99","--log-file="+str(log),exe,"--no-sandbox","-bz","-m",magic,payload],
                       stdout=subprocess.DEVNULL,check=True)
        if "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("missing successful Memcheck report")
    return dict(command_comparisons=cases, memcheck_cases=1, candidate_sha256=receipt["candidate_sha256"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link",type=Path)
    parser.add_argument("pilot",type=Path)
    args=parser.parse_args()
    print(json.dumps(check(args.link,args.pilot),sort_keys=True))
