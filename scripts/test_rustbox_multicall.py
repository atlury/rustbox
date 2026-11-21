#!/usr/bin/env python3
"""Compare every integrated applet's help/version surface to its verified oracle."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def invoke(argv: list[str], *, executable: Path | None = None) -> dict[str, object]:
    try:
        process = subprocess.run(
            argv,
            executable=str(executable) if executable else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            env={"LC_ALL": "C", "LANG": "C", "PATH": "/usr/bin:/bin", "TERM": "dumb"},
        )
        return {
            "status": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "timeout": True,
            "stdout": error.stdout or b"",
            "stderr": error.stderr or b"",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--coreutils-build", type=Path, required=True)
    parser.add_argument("--util-linux-build", type=Path, required=True)
    parser.add_argument("--m4-oracle", type=Path, required=True)
    parser.add_argument("--pkgconf-oracle-dir", type=Path, required=True)
    parser.add_argument("--file-oracle", type=Path, required=True)
    parser.add_argument("--patch-oracle", type=Path, required=True)
    parser.add_argument("--sed-oracle", type=Path, required=True)
    parser.add_argument("--diffutils-oracle-dir", type=Path, required=True)
    parser.add_argument("--grep-oracle", type=Path, required=True)
    parser.add_argument("--bc-oracle-dir", type=Path, required=True)
    parser.add_argument("--attr-oracle-dir", type=Path, required=True)
    parser.add_argument("--rustbox", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    rustbox = args.rustbox.resolve()
    core_oracle = args.coreutils_build.resolve() / "src/coreutils"
    util_build = args.util_linux_build.resolve()
    m4_oracle = args.m4_oracle.resolve()
    pkgconf_oracle_dir = args.pkgconf_oracle_dir.resolve()
    file_oracle = args.file_oracle.resolve()
    patch_oracle = args.patch_oracle.resolve()
    sed_oracle = args.sed_oracle.resolve()
    diffutils_oracle_dir = args.diffutils_oracle_dir.resolve()
    grep_oracle = args.grep_oracle.resolve()
    bc_oracle_dir = args.bc_oracle_dir.resolve()
    attr_oracle_dir = args.attr_oracle_dir.resolve()
    failures: list[dict[str, object]] = []
    cases = 0

    core_names = ["true", "false"]
    for path in sorted((repository / "batches").glob("coreutils-small-*.json")):
        core_names.extend(json.loads(path.read_text(encoding="utf-8"))["applets"])
    core_names = sorted(set(core_names) - {"chcon", "runcon"})
    if len(core_names) != 106:
        raise RuntimeError(f"expected 106 no-security Coreutils applets, found {len(core_names)}")
    for name in core_names:
        for option in ("--help", "--version"):
            cases += 1
            oracle = invoke([name, option], executable=core_oracle)
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "coreutils", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    util_names: list[tuple[str, str]] = []
    for path in sorted((repository / "batches").glob("util-linux-small-*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        suffix = str(manifest["name"]).removeprefix("util-linux-small-")
        hybrid = util_build / f"rustbox-util-linux-small-{suffix}"
        for name in manifest["applets"]:
            dispatch_name = "util-linux-kill" if name == "kill" else name
            util_names.append((name, dispatch_name))
        if not hybrid.is_file():
            raise RuntimeError(f"missing verified util-linux hybrid: {hybrid}")
        for name, dispatch_name in util_names[-len(manifest["applets"]):]:
            for option in ("--help", "--version"):
                cases += 1
                oracle = invoke([str(hybrid), name, option])
                actual = invoke([str(rustbox), dispatch_name, option])
                if oracle != actual:
                    failures.append({"suite": "util-linux", "applet": name, "dispatch_name": dispatch_name, "option": option, "oracle": oracle, "actual": actual})
    if len(util_names) != 155:
        raise RuntimeError(f"expected 155 util-linux public names, found {len(util_names)}")

    for option in ("--help", "--version"):
        cases += 1
        oracle = invoke(["m4", option], executable=m4_oracle)
        actual = invoke([str(rustbox), "m4", option])
        if oracle != actual:
            failures.append({"suite": "m4", "applet": "m4", "option": option, "oracle": oracle, "actual": actual})

    pkgconf_names = ["pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool"]
    for name in pkgconf_names:
        oracle_name = "pkgconf" if name == "pkg-config" else name
        oracle_binary = pkgconf_oracle_dir / oracle_name
        for option in ("--help", "--version"):
            cases += 1
            oracle = invoke([name, option], executable=oracle_binary)
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "pkgconf", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    for option in ("--help", "--version"):
        cases += 1
        oracle = invoke(["file", option], executable=file_oracle)
        actual = invoke([str(rustbox), "file", option])
        if oracle != actual:
            failures.append({"suite": "file", "applet": "file", "option": option, "oracle": oracle, "actual": actual})

    for option in ("--help", "--version"):
        cases += 1
        oracle = invoke(["patch", option], executable=patch_oracle)
        actual = invoke([str(rustbox), "patch", option])
        if oracle != actual:
            failures.append({"suite": "patch", "applet": "patch", "option": option, "oracle": oracle, "actual": actual})

    for option in ("--help", "--version"):
        cases += 1
        oracle = invoke(["sed", option], executable=sed_oracle)
        actual = invoke([str(rustbox), "sed", option])
        if oracle != actual:
            failures.append({"suite": "sed", "applet": "sed", "option": option, "oracle": oracle, "actual": actual})

    diffutils_names = ["cmp", "diff", "diff3", "sdiff"]
    for name in diffutils_names:
        for option in ("--help", "--version"):
            cases += 1
            oracle = invoke([name, option], executable=diffutils_oracle_dir / name)
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "diffutils", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    grep_names = {"grep": None, "egrep": "-E", "fgrep": "-F"}
    for name, matcher in grep_names.items():
        for option in ("--help", "--version"):
            cases += 1
            arguments = ["grep", *([matcher] if matcher else []), option]
            oracle = invoke(arguments, executable=grep_oracle)
            if matcher:
                oracle["stderr"] = (
                    f"{name}: warning: {name} is obsolescent; using grep {matcher}\n".encode()
                    + oracle["stderr"]
                )
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "grep", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    bc_names = ["bc", "dc"]
    for name in bc_names:
        oracle_binary = bc_oracle_dir / name / name
        for option in ("--help", "--version"):
            cases += 1
            oracle = invoke([name, option], executable=oracle_binary)
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "bc", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    attr_names = ["attr", "getfattr", "setfattr"]
    for name in attr_names:
        oracle_binary = attr_oracle_dir / name
        for option in ("--help", "--version"):
            cases += 1
            oracle = invoke([name, option], executable=oracle_binary)
            actual = invoke([str(rustbox), name, option])
            if oracle != actual:
                failures.append({"suite": "attr", "applet": name, "option": option, "oracle": oracle, "actual": actual})

    result = {
        "schema": 1,
        "cases": cases,
        "passed": cases - len(failures),
        "coreutils_applets": len(core_names),
        "util_linux_applets": len(util_names),
        "m4_applets": 1,
        "pkgconf_public_names": len(pkgconf_names),
        "file_applets": 1,
        "patch_applets": 1,
        "sed_applets": 1,
        "diffutils_applets": len(diffutils_names),
        "grep_applets": len(grep_names),
        "bc_applets": len(bc_names),
        "attr_applets": len(attr_names),
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            result,
            indent=2,
            default=lambda value: value.decode("utf-8", "backslashreplace"),
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: result[key] for key in ("cases", "passed", "coreutils_applets", "util_linux_applets", "m4_applets", "pkgconf_public_names", "file_applets", "patch_applets", "sed_applets", "diffutils_applets", "grep_applets", "bc_applets", "attr_applets")}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
