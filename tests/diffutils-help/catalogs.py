#!/usr/bin/env python3
"""Verify all four GNU Diffutils help catalogs with real French and German gettext lookups."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import gettext
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

FIRST_MESSAGE = {
    "cmp": "-b, --print-bytes          print differing bytes",
    "diff": "    --normal                  output a normal diff (the default)",
    "diff3": "-A, --show-all              output all changes, bracketing conflicts",
    "sdiff": "-o, --output=FILE            operate interactively, sending output to FILE",
}


def canonical():
    oracle = ROOT / "work/analysis/diffutils-3.12/oracle"
    pins = json.loads((ROOT / "evidence/diffutils-3.12-oracle.json").read_bytes())["binaries"]
    programs = {}
    for cc in ("gcc", "clang"):
        programs[cc] = {name: oracle / (name + "-" + cc) for name in FIRST_MESSAGE}
        if any(digest(path) != pins[cc][name]["sha256"] for name, path in programs[cc].items()):
            raise ValueError("canonical Diffutils executable differs")
    return programs


def profiles(programs, work, *, subcommand=None):
    profiles = {}
    catalogs = {}
    for language in ("de", "fr"):
        mo = Path("/usr/local/share/locale") / language / "LC_MESSAGES/diffutils.mo"
        if digest(mo) != digest(ROOT / "work/upstream/diffutils-3.12/po" / (language + ".gmo")):
            raise ValueError("expected the shipped GNU Diffutils gettext catalog")
        with mo.open("rb") as f:
            catalogs[language] = gettext.GNUTranslations(f)
    memchecks = 0
    for target, binaries in programs.items():
        for name, path in binaries.items():
            for lang, catalog in (("C", None), *catalogs.items()):
                env = dict(os.environ, LC_ALL="fr_FR.utf8" if catalog else "C", LANGUAGE=lang, TZ="UTC")
                for option in ("--help", "--invalid-rustbox-option"):
                    result = subprocess.run([name, option], executable=path, capture_output=True, env=env,
                                            stdin=subprocess.DEVNULL, timeout=30)
                    msg = FIRST_MESSAGE[name]
                    translated = catalog.gettext(msg) if catalog else msg
                    if option == "--help" and (result.returncode or result.stderr or not translated.encode() in result.stdout
                                               or catalog and msg == translated):
                        raise ValueError((name, lang, target, "translated option message missing"))
                    key = "/".join((name, lang, option))
                    value = [result.returncode, sha256(result.stdout).hexdigest(), sha256(result.stderr).hexdigest()]
                    if profiles.setdefault(key, value) != value:
                        raise ValueError((name, lang, option, target, "output or exit status differs"))
            log = work / f"{target}-{name}.log"
            command = [subcommand, name] if subcommand is not None and target == "candidate" else [path]
            run = subprocess.run(["valgrind","--error-exitcode=99","--leak-check=full",
                                  "--errors-for-leak-kinds=definite,indirect","--log-file="+str(log),*command,"--help"],
                                 env=dict(os.environ,LC_ALL="fr_FR.utf8",LANGUAGE="fr"), capture_output=True, timeout=120)
            if run.returncode or run.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
                raise ValueError((name, target, "translated help Memcheck failed"))
            memchecks += 1
    return dict(cases=len(profiles), profiles=profiles, memcheck_runs=memchecks)


def file_cases(programs, test_target, work):
    results = {}
    for cc in ("gcc", "clang"):
        flags = []
        for name in FIRST_MESSAGE:
            flags.extend(["--gcc-"+name, programs[cc][name], "--clang-"+name, programs[test_target][name]])
        out = work / (cc + ".json")
        subprocess.run([sys.executable, ROOT / "tests/diffutils-oracle-differential.py", *flags, "--output", out],
                       check=True, stdout=subprocess.DEVNULL)
        row = json.loads(out.read_bytes())
        if not row["gcc_clang_exact"] or not row["records"] or not all(r["exact"] for r in row["records"]):
            raise ValueError("Diffutils file and exit comparisons differ")
        results[cc] = len(row["records"])
    return results


def run(link, pilot, work):
    release = json.loads(link.read_bytes())
    key, = [k for k in release["source_library_sha256"] if Path(k).name.startswith("libdiffutils_") and k.endswith(".a")]
    archives = {"parent": ROOT / key}
    if digest(archives["parent"]) != release["source_library_sha256"][key]:
        raise ValueError("Diffutils parent archive differs")
    test_target = "parent"
    if pilot:
        row = json.loads((pilot / "pilot.json").read_bytes())
        archives["candidate"] = pilot / Path(key).name
        if (row["archive"] != key or row["control_sha256"] != digest(archives["parent"])
                or row["candidate_sha256"] != digest(archives["candidate"])):
            raise ValueError("Diffutils candidate differs")
        test_target = "candidate"
    programs = canonical()
    for target, archive in archives.items():
        directory = work / target
        directory.mkdir()
        programs[target] = {}
        for name in FIRST_MESSAGE:
            binary = directory / name
            subprocess.run(["clang-18","-O2","-Wl,--gc-sections","-DRUSTBOX_ENTRY=rustbox_"+name+"_main",
                            ROOT / "bridges/diffutils_main.c",archive,"-ldl","-lpthread","-lm","-o",binary],check=True)
            programs[target][name] = binary
    return dict(public=profiles(programs, work),file_comparisons=file_cases(programs, test_target, work),
                archives={target:digest(archive) for target,archive in archives.items()})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    args = p.parse_args()
    with TemporaryDirectory() as temp:
        print(json.dumps(run(args.link,args.pilot,Path(temp)),indent=2,sort_keys=True))
