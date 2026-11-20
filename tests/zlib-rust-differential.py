#!/usr/bin/env python3
"""Differentially exercise canonical zlib and its translated Rust library."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str], data: bytes = b"", cwd: Path | None = None) -> tuple[int, bytes, bytes]:
    result = subprocess.run(
        command,
        input=data,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )
    return result.returncode, result.stdout, result.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-example", type=Path, required=True)
    parser.add_argument("--rust-example", type=Path, required=True)
    parser.add_argument("--canonical-infcover", type=Path, required=True)
    parser.add_argument("--rust-infcover", type=Path, required=True)
    parser.add_argument("--canonical-minigzip", type=Path, required=True)
    parser.add_argument("--rust-minigzip", type=Path, required=True)
    parser.add_argument("--rust-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparisons = 0
    output_digest = hashlib.sha256()
    diagnostic_names = {
        str(args.canonical_example).encode(): b"example",
        str(args.rust_example).encode(): b"example",
        str(args.canonical_infcover).encode(): b"infcover",
        str(args.rust_infcover).encode(): b"infcover",
        str(args.canonical_minigzip).encode(): b"minigzip",
        str(args.rust_minigzip).encode(): b"minigzip",
    }

    def normalize_stderr(value: bytes) -> bytes:
        for path, name in diagnostic_names.items():
            value = value.replace(path, name)
        return value

    def compare(left: tuple[int, bytes, bytes], right: tuple[int, bytes, bytes], label: str) -> None:
        nonlocal comparisons
        comparisons += 1
        left = (left[0], left[1], normalize_stderr(left[2]))
        right = (right[0], right[1], normalize_stderr(right[2]))
        if left != right:
            raise RuntimeError(
                f"{label} differs: canonical={(left[0], len(left[1]), left[2][-200:])!r}; "
                f"rust={(right[0], len(right[1]), right[2][-200:])!r}"
            )
        output_digest.update(label.encode() + b"\0" + left[1] + b"\0" + left[2])

    with tempfile.TemporaryDirectory(prefix="rustbox-zlib-diff-") as temporary:
        root = Path(temporary)
        canonical_dir = root / "canonical"
        rust_dir = root / "rust"
        canonical_dir.mkdir()
        rust_dir.mkdir()
        compare(
            run([str(args.canonical_example), "example.gz"], cwd=canonical_dir),
            run([str(args.rust_example), "example.gz"], cwd=rust_dir),
            "upstream-example",
        )
        compare(
            run([str(args.canonical_infcover)]),
            run([str(args.rust_infcover)]),
            "upstream-infcover",
        )

        random_source = random.Random(0x5A17_14)
        sizes = [0, 1, 2, 7, 31, 255, 1024, 4095, 16384, 65535]
        options = [[], ["-1"], ["-6"], ["-9"], ["-f"], ["-h"], ["-r"], ["-9", "-f"]]
        corpora: list[tuple[str, bytes]] = []
        for size in sizes:
            corpora.extend((
                (f"zero-{size}", bytes(size)),
                (f"linear-{size}", bytes(index & 255 for index in range(size))),
                (f"alternating-{size}", (b"rustbox-zlib\x00\xff" * ((size + 13) // 14))[:size]),
                (f"random-{size}", random_source.randbytes(size)),
            ))

        compressed_samples: list[bytes] = []
        for index, (name, data) in enumerate(corpora):
            flags = options[index % len(options)]
            canonical = run([str(args.canonical_minigzip), *flags], data)
            rust = run([str(args.rust_minigzip), *flags], data)
            compare(canonical, rust, f"compress-{name}-{'-'.join(flags) or 'default'}")
            if canonical[0] != 0:
                raise RuntimeError(f"canonical compression failed: {name}")
            compressed = canonical[1]
            compressed_samples.append(compressed)
            canonical_decode = run([str(args.canonical_minigzip), "-d"], compressed)
            rust_decode = run([str(args.rust_minigzip), "-d"], compressed)
            compare(canonical_decode, rust_decode, f"decompress-{name}")
            if canonical_decode[0] != 0 or canonical_decode[1] != data:
                raise RuntimeError(f"round trip failed: {name}")

        for index, compressed in enumerate(compressed_samples[::5]):
            for cut in (1, max(1, len(compressed) // 2)):
                damaged = compressed[:-cut]
                compare(
                    run([str(args.canonical_minigzip), "-d"], damaged),
                    run([str(args.rust_minigzip), "-d"], damaged),
                    f"truncated-{index}-{cut}",
                )

        valgrind = [
            "valgrind", "--quiet", "--leak-check=full", "--show-leak-kinds=all",
            "--errors-for-leak-kinds=all", "--error-exitcode=99",
        ]
        if run([*valgrind, str(args.rust_example), "valgrind.gz"], cwd=rust_dir)[0] != 0:
            raise RuntimeError("Valgrind failed for Rust-backed zlib example")
        if run([*valgrind, str(args.rust_infcover)])[0] != 0:
            raise RuntimeError("Valgrind failed for Rust-backed zlib infcover")

    evidence = {
        "schema": 1,
        "comparisons": comparisons,
        "corpus_inputs": len(corpora),
        "output_digest_sha256": output_digest.hexdigest(),
        "canonical_rust_exact": True,
        "cross_decompression": "pass",
        "upstream_example": "pass",
        "upstream_infcover": "pass",
        "valgrind": {"rust_example": "pass", "rust_infcover": "pass"},
        "rust_library_bytes": args.rust_library.stat().st_size,
        "rust_library_sha256": hashlib.sha256(args.rust_library.read_bytes()).hexdigest(),
        "rust_test_binary_bytes": {
            "example": args.rust_example.stat().st_size,
            "infcover": args.rust_infcover.stat().st_size,
            "minigzip": args.rust_minigzip.stat().st_size,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": comparisons, "corpus_inputs": len(corpora)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
