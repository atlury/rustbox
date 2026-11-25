#!/usr/bin/env python3
"""Check pkgconf's raw/decoded argument vectors and package-file callbacks across byte values and locales."""
# SPDX-License-Identifier: ISC
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest


def run(link, pilot, work):
    j = json.loads(link.read_bytes())
    key, = [k for k in j["source_library_sha256"] if Path(k).name.startswith("libpkgconf_") and k.endswith(".a")]
    oracle = ROOT / "work/analysis/pkgconf-3.0.11/oracle"
    pinned = json.loads((ROOT / "evidence/pkgconf-3.0.11-oracle.json").read_bytes())
    archives = {cc: oracle / ("libpkgconf-" + cc + ".a") for cc in ("gcc","clang")}
    archives["parent"] = ROOT / key
    if digest(archives["parent"]) != j["source_library_sha256"][key]:
        raise ValueError("original pkgconf archive differs")
    target = "parent"
    if pilot:
        target = "candidate"
        row = json.loads((pilot / "pilot.json").read_bytes())
        archives[target] = pilot / Path(key).name
        if (row["archive"] != key or row["candidate_sha256"] != digest(archives[target])
                or row["control_sha256"] != digest(archives["parent"]) or row["control_binary_sha256"] != j["binary"]["sha256"]):
            raise ValueError("pkgconf candidate differs")
    bins = {}
    names = ("pkgconf","pkg-config","bomtool","pccritic","spdxtool")
    for cc in ("gcc","clang"):
        directory = work / cc
        directory.mkdir()
        for name in names:
            binary = ("pkgconf" if name == "pkg-config" else name) + "-" + cc
            if digest(oracle / binary) != pinned["binaries"][binary]["sha256"]:
                raise ValueError("canonical pkgconf binary differs")
            (directory / name).symlink_to(oracle / binary)
        bins[cc] = directory
    folder = work / target
    folder.mkdir()
    exe = folder / "engine"
    subprocess.run(["clang-18","-O2","-Wl,--gc-sections","-o",exe,ROOT / "bridges/pkgconf_main.c",archives[target],
                    "-ldl","-lpthread","-lm"],check=True)
    for name in names:
        (folder / name).symlink_to(exe)
    commands = {}
    for cc in ("gcc","clang"):
        report = work / (cc + ".json")
        subprocess.run([sys.executable,ROOT / "tests/pkgconf-differential.py","--canonical-dir",bins[cc],
                        "--hybrid-dir",folder,"--output",report],check=True,stdout=subprocess.DEVNULL)
        r=json.loads(report.read_bytes())
        if not r["comparisons"] or not r["canonical_hybrid_exact"]:
            raise ValueError("incomplete public command suite")
        commands[cc]=r["comparisons"]
    profiles = {}
    memory = 0
    locales = sorted(set(subprocess.check_output(["locale","-a"],text=True).splitlines()))
    if not {"C","fr_FR.iso88591","ja_JP.eucjp"} <= set(locales):
        raise ValueError("expected the project locale set")
    for name, archive in archives.items():
        exe = work / ("api-" + name)
        subprocess.run(["gcc" if name=="gcc" else "clang-18","-Wall","-Werror","-O2",Path(__file__).with_suffix(".c"),
                        archive,"-Wl,--gc-sections","-ldl","-lm","-lpthread","-o",exe],check=True)
        for loc in locales:
            for check in ([False,True] if loc in ("C","fr_FR.iso88591") else [False]):
                log=work/"memcheck"
                prefix=["valgrind","--error-exitcode=99","--leak-check=full","--errors-for-leak-kinds=definite,indirect","--log-file="+str(log)] if check else []
                data=subprocess.check_output([*prefix,exe,loc],timeout=120)
                checksum=sha256(data).hexdigest()
                if (not data or profiles.setdefault(loc,checksum)!=checksum
                        or check and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                    raise ValueError((name,loc,check,"callback, argument vector or memory comparison failed"))
                memory+=int(check)
    if profiles["C"]==profiles["fr_FR.iso88591"]:
        raise ValueError("locale-dependent byte classifications did not change")
    return dict(archives={n:digest(a) for n,a in archives.items()},commands=commands,locales=profiles,
                argument_splits_per_locale=256*5*2,package_files_per_locale=256,memcheck_runs=memory)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("link",type=Path)
    p.add_argument("pilot",type=Path,nargs="?")
    a=p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(run(a.link,a.pilot,Path(tmp)),indent=2,sort_keys=True))
