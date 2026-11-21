#!/usr/bin/env python3
"""Compare independent GCC and Clang builds of canonical GNU bc and dc."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, argv0: bytes, arguments: list[bytes], data: bytes) -> dict[str, object]:
    completed = subprocess.run(
        [argv0, *arguments],
        executable=os.fsencode(binary),
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return {
        "status": completed.returncode,
        "stdout_sha256": sha256(completed.stdout),
        "stderr_sha256": sha256(completed.stderr),
        "stdout_length": len(completed.stdout),
        "stderr_length": len(completed.stderr),
    }


BC_CASES: list[tuple[str, list[bytes], bytes]] = [
    ("empty", [], b""),
    ("addition", [b"-q"], b"2+3\n"),
    ("precedence", [b"-q"], b"2+3*4\n(2+3)*4\n"),
    ("scale", [b"-q"], b"scale=20\n1/7\n"),
    ("ibase-obase", [b"-q"], b"obase=16\n255\nibase=16\nFF\n"),
    ("large-integer", [b"-q"], b"2^1024\n"),
    ("sqrt", [b"-q"], b"scale=50\nsqrt(2)\n"),
    ("function", [b"-q"], b"define f(x){if(x<2)return(1);return(x*f(x-1))}\nf(40)\n"),
    ("array", [b"-q"], b"for(i=0;i<5;i++)a[i]=i*i\nfor(i=0;i<5;i++)a[i]\n"),
    ("auto", [b"-q"], b"define f(x){auto y;y=x+1;return(y)}\nf(9)\n"),
    ("boolean", [b"-q"], b"1&&0\n1||0\n!0\n"),
    ("strings", [b"-q"], b"\"alpha\\nbeta\\n\"\n"),
    ("print", [b"-q"], b"print \"x=\", 7, \"\\n\"\n"),
    ("last", [b"-q"], b"3*7\nlast+1\n"),
    ("math-library", [b"-q", b"-l"], b"scale=30\ns(1)\nc(1)\na(1)\ne(1)\nl(2)\nj(3,2)\n"),
    ("warn-extension", [b"-q", b"-w"], b"print 1, \"\\n\"\n"),
    ("standard-reject", [b"-q", b"-s"], b"print 1, \"\\n\"\n"),
    ("syntax-error", [b"-q"], b"1+\n"),
    ("runtime-divzero", [b"-q"], b"1/0\n"),
    ("quit", [b"-q"], b"1\nquit\n2\n"),
    ("halt", [b"-q"], b"1\nhalt\n2\n"),
    ("version", [b"--version"], b""),
    ("help", [b"--help"], b""),
    ("bad-option", [b"--definitely-invalid"], b""),
]


DC_CASES: list[tuple[str, list[bytes], bytes]] = [
    ("empty", [], b""),
    ("addition", [], b"2 3 + p\n"),
    ("subtraction", [], b"7 12 - p\n"),
    ("multiply", [], b"123456789 987654321 * p\n"),
    ("divide", [], b"20 k 1 7 / p\n"),
    ("remainder", [], b"17 5 % p\n"),
    ("power", [], b"2 256 ^ p\n"),
    ("sqrt", [], b"40 k 2 v p\n"),
    ("stack", [], b"1 2 3 f\n"),
    ("clear", [], b"1 2 3 c z p\n"),
    ("register", [], b"42 sa 0 la + p\n"),
    ("register-stack", [], b"1 Sa 2 Sa La p La p\n"),
    ("array", [], b"10 3:a 3;a p\n"),
    ("macro", [], b"[2 3 + p]x\n"),
    ("conditional", [], b"[equal]sa 4 4 =a\n"),
    ("string", [], b"[alpha beta]p\n"),
    ("base", [], b"16 o 255 p\n16 i FF p\n"),
    ("precision", [b"-x"], b"20 k 1 7 / p\n"),
    ("syntax-error", [], b"?\n"),
    ("version", [b"--version"], b""),
    ("help", [b"--help"], b""),
    ("bad-option", [b"--definitely-invalid"], b""),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-bc", type=Path, required=True)
    parser.add_argument("--clang-bc", type=Path, required=True)
    parser.add_argument("--gcc-dc", type=Path, required=True)
    parser.add_argument("--clang-dc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="rustbox-bc-differential-"):
        for applet, cases, gcc, clang in (
            ("bc", BC_CASES, args.gcc_bc, args.clang_bc),
            ("dc", DC_CASES, args.gcc_dc, args.clang_dc),
        ):
            for name, arguments, data in cases:
                argv0 = os.fsencode(applet)
                left = run(gcc, argv0, arguments, data)
                right = run(clang, argv0, arguments, data)
                if left != right:
                    raise RuntimeError(f"{applet}/{name}: GCC {left} != Clang {right}")
                records.append({"applet": applet, "name": name, "result": left})

    payload = {
        "schema": 1,
        "cases": len(records),
        "passed": len(records),
        "records": records,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"bc/dc canonical differential: {len(records)}/{len(records)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
