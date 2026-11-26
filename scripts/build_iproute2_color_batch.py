#!/usr/bin/env python3
"""Compile and compare IPRoute2 color palettes against canonical GCC and Clang for the selected engines."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_iproute2_colors import build
from check_cargo_private_inlines import ROOT, digest


def qualify(link, root, key, expected, baseline, ip_pilot):
    name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
    folder = root / name
    pilot = folder / "compiled"
    folder.mkdir(exist_ok=True)
    with (folder / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not pilot.is_dir():
            if name == "ip" and ip_pilot:
                with TemporaryDirectory(dir=folder) as tmp:
                    stage = Path(tmp) / "compiled"
                    shutil.copytree(ip_pilot,stage)
                    stage.rename(pilot)
            else:
                build(link,pilot,key)
        row = json.loads((pilot / "pilot.json").read_bytes())
        actual = dict(expected,candidate_sha256=digest(pilot / Path(key).name))
        if "rustc_archive" in row:
            actual["rustc_archive"] = actual.pop("cargo_archive")
        if row != actual or row["control_sha256"] != digest(ROOT / key):
            raise ValueError("compiled archive differs from the reviewed selection for " + name)
        driver = ROOT / "tests/iproute2-color/compare.py"
        probe = driver.with_name("palette.c")
        metadata = dict(archive=row, driver_sha256=digest(driver), probe_sha256=digest(probe))
        receipt = folder / "comparison.json"
        if receipt.exists():
            result = json.loads(receipt.read_bytes())
            if any(result[k] != v for k,v in metadata.items()):
                raise ValueError("cached archive or test harness changed for " + name)
        else:
            cmd = ["docker","run","--rm","--network","none","--platform","linux/amd64","-v",str(ROOT)+":/work:ro",
                   "-v","rustbox-iproute2-7.3.0:/rustbox-iproute2:ro","-w","/work","rustbox-e2fsprogs:2026-11-24",
                   "python3","-B",driver.relative_to(ROOT),link.relative_to(ROOT),pilot.relative_to(ROOT)]
            result = dict(**metadata, comparisons=json.loads(subprocess.check_output(cmd)))
        checks = result["comparisons"]
        if (checks["api"] != baseline["api"] or checks["attribute_cases_per_build"] != 336 or checks["memcheck_runs"] != 4
                or checks["public"] != (baseline["public"] if name=="ip" else {})
                or checks["archives"] != dict(parent=row["control_sha256"],candidate=row["candidate_sha256"])):
            raise ValueError("canonical palette behavior or memory checks differ for " + name)
        if not receipt.exists():
            pending = receipt.with_suffix(".tmp")
            pending.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
            pending.replace(receipt)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("baseline",type=Path)
    p.add_argument("--engine")
    p.add_argument("--ip-pilot",type=Path)
    p.add_argument("--jobs",type=int,default=2)
    a=p.parse_args()
    source = json.loads((ROOT/"evidence/iproute2-color-palette-sources.json").read_bytes())
    link,root=a.link.resolve(),a.output.resolve()
    baseline=json.loads(a.baseline.read_bytes())
    if (digest(link)!=source["link_report_sha256"] or a.jobs<1 or baseline["memcheck_runs"]!=3
            or len(baseline["api"])!=4 or len(baseline["public"])!=8 or baseline["attribute_cases_per_build"]!=336):
        p.error("expected the checked routing parent and the complete canonical ip palette baseline")
    keys=sorted(k for k in source["engines"] if not a.engine or Path(k).name=="lib"+a.engine+"_audit.a")
    if not keys:
        p.error("unknown IPRoute2 engine")
    root.mkdir(parents=True,exist_ok=True)
    def one(key):
        return qualify(link,root,key,source["engines"][key],baseline,a.ip_pilot)
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        verified=dict(zip(keys,pool.map(one,keys)))
    report=dict(engines=verified,link_report_sha256=digest(link),api_cases_per_candidate=336,
                memcheck_runs=sum(r["comparisons"]["memcheck_runs"] for r in verified.values()),
                static_pointer_slots_removed=sum(r["archive"]["static_pointer_slots_removed"] for r in verified.values()))
    target=root/((a.engine+"-" if a.engine else "")+"results.json")
    with TemporaryDirectory(dir=root) as tmp:
        pending=Path(tmp)/"results.json"
        pending.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        pending.replace(target)


if __name__=="__main__":
    main()
