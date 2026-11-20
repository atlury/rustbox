#!/usr/bin/env python3
"""Differentially compare canonical GNU M4 and the translated hybrid."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str], data: bytes, cwd: Path) -> tuple[int, bytes, bytes]:
    result = subprocess.run(
        command,
        input=data,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--hybrid", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparisons = 0
    digest = hashlib.sha256()
    rng = random.Random(0x4D34_1421)
    cases: list[tuple[str, list[str], bytes]] = [
        ("empty", [], b""),
        ("plain", [], b"plain text\n"),
        ("nul", [], b"left\0right\n"),
        ("raw-bytes", [], bytes(range(1, 256))),
        ("help", ["--help"], b""),
        ("version", ["--version"], b""),
        ("invalid-option", ["--rustbox-invalid"], b""),
        ("prefix-builtins", ["--prefix-builtins"], b"m4_define(`x', `ok')m4_x\n"),
        ("fatal-warning", ["--fatal-warnings"], b"m4exit(`not-a-number')\n"),
        ("synclines", ["--synclines"], b"one\ntwo\n"),
        ("trace", ["--trace=foo"], b"define(`foo', `$1')foo(`x')\n"),
    ]
    operators = ["+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"]
    for index in range(96):
        left = rng.randrange(1, 1_000_000)
        right = rng.randrange(1, 1000)
        operator = operators[index % len(operators)]
        name = f"macro_{index}"
        value = f"value-{rng.randrange(1 << 32):08x}"
        programs = [
            f"define(`{name}', `{value}')dnl\n{name}\n",
            f"eval({left} {operator} {right})\n",
            f"ifelse(`{index % 3}', `0', `zero', `other')\n",
            f"substr(`abcdefghijklmnop', {index % 12}, {(index % 5) + 1})\n",
            f"translit(`rustbox-{index}', `a-z', `A-Z')\n",
            f"regexp(`rustbox-{index}', `box-\\([0-9]+\\)', `\\1')\n",
            f"patsubst(`a{index}b{index}c', `[0-9]+', `N')\n",
            f"format(`%08x:%d:%s', {left}, {right}, `{value}')\n",
        ]
        cases.append((f"generated-{index:03d}", [], programs[index % len(programs)].encode()))

    with tempfile.TemporaryDirectory(prefix="rustbox-m4-diff-") as temporary:
        root = Path(temporary)
        canonical_dir = root / "canonical"
        hybrid_dir = root / "hybrid"
        canonical_dir.mkdir()
        hybrid_dir.mkdir()
        canonical = canonical_dir / "m4"
        hybrid = hybrid_dir / "m4"
        canonical.symlink_to(args.canonical.resolve())
        hybrid.symlink_to(args.hybrid.resolve())

        def normalize(value: bytes) -> bytes:
            return value.replace(str(canonical).encode(), b"m4").replace(
                str(hybrid).encode(), b"m4"
            )

        for label, options, data in cases:
            left = run([str(canonical), *options], data, canonical_dir)
            right = run([str(hybrid), *options], data, hybrid_dir)
            normalized_left = (left[0], normalize(left[1]), normalize(left[2]))
            normalized_right = (right[0], normalize(right[1]), normalize(right[2]))
            comparisons += 1
            if normalized_left != normalized_right:
                raise RuntimeError(
                    f"{label} differs: canonical={(left[0], left[1][-200:], left[2][-200:])!r}; "
                    f"hybrid={(right[0], right[1][-200:], right[2][-200:])!r}"
                )
            digest.update(label.encode() + b"\0" + normalized_left[1] + b"\0" + normalized_left[2])

        for directory in (canonical_dir, hybrid_dir):
            (directory / "included.m4").write_bytes(b"define(`included', `from-file')included\n")
        include_data = b"include(`included.m4')\n"
        left = run([str(canonical)], include_data, canonical_dir)
        right = run([str(hybrid)], include_data, hybrid_dir)
        comparisons += 1
        if (left[0], normalize(left[1]), normalize(left[2])) != (
            right[0], normalize(right[1]), normalize(right[2])
        ):
            raise RuntimeError("include behavior differs")
        digest.update(b"include\0" + left[1] + b"\0" + normalize(left[2]))

    evidence = {
        "schema": 1,
        "comparisons": comparisons,
        "canonical_hybrid_exact": True,
        "generated_cases": 96,
        "fixed_cases": 12,
        "output_digest_sha256": digest.hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
