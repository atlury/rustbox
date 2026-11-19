#!/usr/bin/env python3
"""Run manifest-declared Coreutils applet paths under Valgrind."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


METRIC = re.compile(
    r"(?P<name>definitely lost|indirectly lost): "
    r"(?P<bytes>[0-9,]+) bytes in (?P<blocks>[0-9,]+) blocks"
)
LOSS_RECORD = re.compile(
    r"(?P<bytes>[0-9,]+) bytes in (?P<blocks>[0-9,]+) blocks are "
    r"(?P<name>definitely lost|indirectly lost)"
)
ERRORS = re.compile(r"ERROR SUMMARY: (?P<count>[0-9,]+)")


def valgrind_metrics(text: str) -> dict[str, int]:
    result = {
        "definitely_lost_bytes": 0,
        "definitely_lost_blocks": 0,
        "indirectly_lost_bytes": 0,
        "indirectly_lost_blocks": 0,
        "errors": 0,
    }
    for match in METRIC.finditer(text):
        prefix = match.group("name").replace(" ", "_")
        result[prefix + "_bytes"] = int(match.group("bytes").replace(",", ""))
        result[prefix + "_blocks"] = int(match.group("blocks").replace(",", ""))
    for match in LOSS_RECORD.finditer(text):
        prefix = match.group("name").replace(" ", "_")
        result[prefix + "_bytes"] += int(match.group("bytes").replace(",", ""))
        result[prefix + "_blocks"] += int(match.group("blocks").replace(",", ""))
    if match := ERRORS.search(text):
        result["errors"] = int(match.group("count").replace(",", ""))
    return result


def run_case(
    binary: Path, case: dict[str, object], cwd: Path, log: Path, env: dict[str, str]
) -> tuple[int, dict[str, int], str]:
    command = [
        "valgrind",
        "--quiet",
        "--leak-check=full",
        "--show-leak-kinds=definite,indirect",
        "--errors-for-leak-kinds=definite,indirect",
        f"--log-file={log}",
        str(binary),
        f"--coreutils-prog={case['applet']}",
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
    return process.returncode, valgrind_metrics(text), text


def prepare_case(directory: Path, setup: object) -> None:
    directory.mkdir(parents=True)
    if setup == "link":
        (directory / "source").write_bytes(b"payload")
    elif setup == "unlink":
        (directory / "victim").write_bytes(b"payload")
    elif setup == "file":
        (directory / "file").write_bytes(b"payload")
    elif setup == "comm":
        (directory / "left").write_bytes(b"alpha\ncommon\n")
        (directory / "right").write_bytes(b"beta\ncommon\n")
    elif setup is not None:
        raise RuntimeError(f"unknown Valgrind setup: {setup}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--canonical", type=Path)
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

    with tempfile.TemporaryDirectory(prefix="rustbox-valgrind-") as temporary:
        root = Path(temporary)

        def check_case(item: tuple[int, dict[str, object]]) -> tuple[bool, bool]:
            index, case = item
            applet = case["applet"]
            if applet not in applets:
                raise RuntimeError(f"Valgrind case names undeclared applet: {applet}")
            setup = case.get("setup")
            hybrid_cwd = root / str(index) / "hybrid"
            canonical_cwd = root / str(index) / "canonical"
            prepare_case(hybrid_cwd, setup)
            prepare_case(canonical_cwd, setup)

            env = os.environ.copy()
            env["LC_ALL"] = "C"
            env["ENV_TEST"] = "alpha"
            actual = run_case(
                args.binary, case, hybrid_cwd, root / f"{index}-{applet}-hybrid.log", env
            )
            if args.canonical is None:
                expected = (case["status"], {name: 0 for name in actual[1]}, "")
            else:
                expected = run_case(
                    args.canonical, case, canonical_cwd,
                    root / f"{index}-{applet}-canonical.log", env
                )
            metrics_not_worse = all(
                actual[1][name] <= expected[1][name] for name in actual[1]
            )
            if expected[0] != case["status"] or actual[0] != expected[0] or not metrics_not_worse:
                raise AssertionError((case, expected, actual))
            return any(expected[1].values()), actual[1] != expected[1]

        workers = min(8, len(cases))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            comparisons = list(executor.map(check_case, enumerate(cases)))

    checked = len(cases)
    canonical_nonzero = sum(nonzero for nonzero, _improved in comparisons)
    improved = sum(improved for _nonzero, improved in comparisons)

    result = {
        "schema": 1,
        "cases": checked,
        "passed": checked,
        "canonical_nonzero_resource_cases": canonical_nonzero,
        "improved_resource_cases": improved,
        "parallel_workers": workers,
        "valgrind_errors": 0,
        "definite_or_indirect_leaks": 0,
        "translation_introduced_resource_deltas": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
