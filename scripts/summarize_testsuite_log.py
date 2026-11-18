#!/usr/bin/env python3
"""Extract the stable Automake testsuite totals from a completed log."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FIELDS = ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", required=True)
    args = parser.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    counts: dict[str, int] = {}
    for field in FIELDS:
        matches = re.findall(rf"^# {field}:\s+(\d+)$", text, re.MULTILINE)
        if len(matches) != 1:
            raise RuntimeError(f"expected one {field} count, found {len(matches)}")
        counts[field.lower()] = int(matches[0])
    errors = re.findall(r"^ERROR: (.+)$", text, re.MULTILINE)
    result = {"schema": 1, "suite": args.suite, **counts, "errors": errors}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
