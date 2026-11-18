#!/usr/bin/env python3
"""Run manifest-declared Coreutils applet paths under Valgrind."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


LEAK_OR_ERROR = re.compile(
    r"definitely lost: [1-9]|indirectly lost: [1-9]|ERROR SUMMARY: [1-9]"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    applets = manifest["applets"]
    declared = manifest["valgrind_cases"]
    cases = [
        {"applet": applet, "arguments": [option], "status": 0}
        for applet in applets
        for option in ("--help", "--version")
    ] + declared

    checked = 0
    with tempfile.TemporaryDirectory(prefix="rustbox-valgrind-") as temporary:
        root = Path(temporary)
        for index, case in enumerate(cases):
            applet = case["applet"]
            if applet not in applets:
                raise RuntimeError(f"Valgrind case names undeclared applet: {applet}")
            cwd = root / str(index)
            cwd.mkdir()
            setup = case.get("setup")
            if setup == "link":
                (cwd / "source").write_bytes(b"payload")
            elif setup == "unlink":
                (cwd / "victim").write_bytes(b"payload")
            elif setup is not None:
                raise RuntimeError(f"unknown Valgrind setup: {setup}")

            log = root / f"{index}-{applet}.log"
            env = os.environ.copy()
            env["LC_ALL"] = "C"
            env["ENV_TEST"] = "alpha"
            command = [
                "valgrind",
                "--quiet",
                "--leak-check=full",
                "--show-leak-kinds=definite,indirect",
                "--errors-for-leak-kinds=definite,indirect",
                "--error-exitcode=99",
                f"--log-file={log}",
                str(args.binary),
                f"--coreutils-prog={applet}",
                *case["arguments"],
            ]
            process = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            text = log.read_text(encoding="utf-8", errors="replace")
            if process.returncode != case["status"] or LEAK_OR_ERROR.search(text):
                raise AssertionError((case, process.returncode, text))
            checked += 1

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "valgrind_errors": 0,
        "definite_or_indirect_leaks": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
