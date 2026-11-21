#!/usr/bin/env python3
"""Apply eight type-directed C integer promotions missed by C2Rust 0.22.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPAIRS = {
    "src/cmdbuf.rs": [
        (
            "n.overflowing_mul(10 as ::core::ffi::c_int)",
            "n.overflowing_mul(10 as LINENUM)",
            "ckd_mul LINENUM operand promotion",
        ),
        (
            ".overflowing_add(*p as ::core::ffi::c_int - '0' as i32)",
            ".overflowing_add((*p as ::core::ffi::c_int - '0' as i32) as LINENUM)",
            "ckd_add LINENUM operand promotion",
        ),
    ],
    "src/line.rs": [
        (
            ".overflowing_mul(10 as ::core::ffi::c_int)",
            ".overflowing_mul(10 as ::core::ffi::c_uint)",
            "ckd_mul unsigned-int operand promotion",
        ),
        (
            ".overflowing_add(ch.wrapping_sub('0' as i32 as LWCHAR))",
            ".overflowing_add(ch.wrapping_sub('0' as i32 as LWCHAR) as ::core::ffi::c_uint)",
            "ckd_add unsigned-int operand promotion",
        ),
    ],
    "src/output.rs": [
        (
            "let (fresh14, fresh15) = val.overflowing_mul(radix);",
            "let (fresh14, fresh15) = val.overflowing_mul(radix as POSITION);",
            "ckd_mul POSITION operand promotion",
        ),
        (
            "let (fresh16, fresh17) = val.overflowing_add(digit);",
            "let (fresh16, fresh17) = val.overflowing_add(digit as POSITION);",
            "ckd_add POSITION operand promotion",
        ),
        (
            "let (fresh18, fresh19) = val.overflowing_mul(radix);",
            "let (fresh18, fresh19) = val.overflowing_mul(radix as ::core::ffi::c_ulong);",
            "ckd_mul unsigned-long operand promotion",
        ),
        (
            "let (fresh20, fresh21) = val.overflowing_add(digit);",
            "let (fresh20, fresh21) = val.overflowing_add(digit as ::core::ffi::c_ulong);",
            "ckd_add unsigned-long operand promotion",
        ),
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    crate = args.crate.resolve()
    changes = []
    for relative, repairs in REPAIRS.items():
        path = crate / relative
        before_hash = sha256(path)
        text = path.read_text(encoding="utf-8")
        for old, new, reason in repairs:
            count = text.count(old)
            if count != 1:
                raise RuntimeError(
                    f"expected exactly one {reason} site in {relative}, found {count}"
                )
            text = text.replace(old, new, 1)
            changes.append({"path": relative, "reason": reason})
        path.write_text(text, encoding="utf-8")
        changes[-len(repairs)]["file_before_sha256"] = before_hash
        changes[-1]["file_after_sha256"] = sha256(path)
    result = {
        "schema": 1,
        "translator": "c2rust 0.22.1",
        "kind": "type-directed C integer promotions",
        "semantic_algorithm_changes": 0,
        "repair_count": len(changes),
        "changes": changes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
