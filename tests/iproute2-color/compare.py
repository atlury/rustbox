#!/usr/bin/env python3
"""Compare IPRoute2 color attributes, variadic formatting, palette state and read-only loopback output."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest
from test_iproute2_route_names import SOURCE
from test_routing_protocol_pilot import LIBS


def check(link, pilot, work):
    release = json.loads(link.read_bytes())
    if pilot:
        key = json.loads((pilot / "pilot.json").read_bytes())["archive"]
    else:
        key, = [k for k in release["source_library_sha256"] if Path(k).name == "libip_audit.a"]
    public_ip = Path(key).name == "libip_audit.a"
    archives = {"parent": ROOT / key}
    if digest(archives["parent"]) != release["source_library_sha256"][key]:
        raise ValueError("IPRoute2 parent archive differs")
    if pilot:
        row = json.loads((pilot / "pilot.json").read_bytes())
        archives["candidate"] = pilot / Path(key).name
        if (row["archive"] != key or row["candidate_sha256"] != digest(archives["candidate"])
                or row["control_sha256"] != digest(archives["parent"]) or row["canonical_sha256"] != digest(SOURCE / "lib/color.c")):
            raise ValueError("IPRoute2 palette candidate differs")
    driver = Path(__file__).with_name("palette.c")
    obj = work / "palette.o"
    subprocess.run(["gcc","-O2","-Wall","-Wextra","-Werror","-I"+str(SOURCE/"include"),"-c",driver,"-o",obj],check=True)
    targets, programs = {}, {}
    pins = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())["canonical"]
    for cc in ("gcc","clang-18"):
        db = json.loads((ROOT / f"work/analysis/iproute2-7.3.0/oracle/{cc}-compile-commands.json").read_bytes())
        flags, = [r["arguments"] for r in db if r["file"].endswith("/lib/color.c")]
        color = work / (cc + ".o")
        flags[flags.index("-o") + 1] = str(color)
        subprocess.run([*flags,"-ffunction-sections","-fdata-sections"],cwd=SOURCE/"lib",check=True)
        targets[cc] = work / ("api-" + cc)
        subprocess.run([cc,"-Wl,--gc-sections",obj,color,"-o",targets[cc]],check=True)
        programs[cc] = Path("/rustbox-iproute2/programs-"+cc)/"ip"
        if digest(programs[cc]) != pins[cc]["canonical_sha256"]["ip"]:
            raise ValueError("canonical public ip binary differs")
    for name, archive in archives.items():
        targets[name] = work / ("api-" + name)
        subprocess.run(["clang-18","-Wl,--gc-sections",obj,archive,*LIBS,"-o",targets[name]],check=True)
        if not public_ip:
            continue
        programs[name] = work / ("ip-" + name)
        subprocess.run(["clang-18","-O2","-Wl,--gc-sections","-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
                        ROOT/"bridges/iproute2_program_main.c",archive,*LIBS,"-o",programs[name]],check=True)
    api, public = {}, {}
    memchecks = 0
    for target, binary in targets.items():
        for option, json_mode in ((0,0),(1,0),(2,0),(2,1)):
            key_name = f"{option}/{json_mode}"
            prefix = []
            if option == 2 and not json_mode:
                log = work / (target + ".memcheck")
                prefix = ["valgrind","--error-exitcode=99","--leak-check=full","--errors-for-leak-kinds=definite,indirect",
                          "--log-file="+str(log)]
            result = subprocess.run([*prefix,binary,str(option),str(json_mode)],capture_output=True,timeout=120)
            if result.returncode or result.stderr or len(result.stdout.splitlines()) != 84:
                raise ValueError((target,key_name,result.returncode,result.stderr))
            if prefix:
                if b"\x1b[36m" not in result.stdout or b"\x1b[1;36m" not in result.stdout or "ERROR SUMMARY: 0 errors" not in log.read_text():
                    raise ValueError("light or dark color bytes or memory comparison missing")
                memchecks += 1
            elif b"\x1b[" in result.stdout:
                raise ValueError("unexpected color escape in disabled profile")
            checksum = sha256(result.stdout).hexdigest()
            if api.setdefault(key_name,checksum) != checksum:
                raise ValueError((target,key_name,"palette bytes or lengths differ"))
        if not public_ip:
            continue
        for bg in ("1;0","0;7"):
            for opts in (("-c",),("-c=never",),("-c=auto",),("-j","-c")):
                env = dict(os.environ, LC_ALL="C", COLORFGBG=bg)
                env.pop("NO_COLOR",None)
                result = subprocess.run(["ip",*opts,"-br","address","show","dev","lo"],executable=programs[target],
                                        capture_output=True,env=env,timeout=30)
                if result.returncode or result.stderr or not result.stdout or ((opts==("-c",)) != (b"\x1b[" in result.stdout)):
                    raise ValueError((target,opts,result.returncode,result.stderr,result.stdout[:120]))
                name = bg + "/" + " ".join(opts)
                checksum = sha256(result.stdout).hexdigest()
                if public.setdefault(name,checksum) != checksum:
                    raise ValueError((target,name,"public loopback output differs"))
    return dict(api=api, public=public, attribute_cases_per_build=336, memcheck_runs=memchecks,
                archives={name:digest(path) for name,path in archives.items()})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link",type=Path)
    p.add_argument("pilot",type=Path,nargs="?")
    a = p.parse_args()
    with TemporaryDirectory() as temp:
        print(json.dumps(check(a.link,a.pilot,Path(temp)),indent=2,sort_keys=True))
