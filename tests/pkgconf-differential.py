#!/usr/bin/env python3
"""Independent exact comparisons for the translated pkgconf tool family."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def run(binary: Path, arguments: list[str], environment: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        [str(binary), *arguments],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def digest(result: dict[str, object]) -> str:
    status = int(result["status"])
    payload = status.to_bytes(4, "little", signed=True) + result["stdout"] + b"\0" + result["stderr"]
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-dir", type=Path, required=True)
    parser.add_argument("--hybrid-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="rustbox-pkgconf-diff-") as temporary:
        pcdir = Path(temporary)
        (pcdir / "bar.pc").write_text(
            "prefix=/opt/bar\n"
            "libdir=${prefix}/lib\n"
            "includedir=${prefix}/include\n"
            "Name: bar\nDescription: dependency\nVersion: 2.1.3\n"
            "Libs: -L${libdir} -lbar\nCflags: -I${includedir}\n"
        )
        (pcdir / "foo.pc").write_text(
            "prefix=/opt/foo\n"
            "exec_prefix=${prefix}\n"
            "libdir=${exec_prefix}/lib\n"
            "includedir=${prefix}/include\n"
            "custom=rustbox\n"
            "Name: foo\nDescription: primary package\nVersion: 1.4.2\n"
            "Requires: bar >= 2.0\nRequires.private: bar < 3\n"
            "Libs: -L${libdir} -lfoo\nLibs.private: -lm\n"
            "Cflags: -I${includedir} -DFOO=1\n"
        )
        environment = dict(os.environ)
        environment.update(
            {
                "LC_ALL": "C",
                "NO_COLOR": "1",
                "PKG_CONFIG_PATH": str(pcdir),
                "PKG_CONFIG_LIBDIR": str(pcdir),
                "PKG_CONFIG_SYSTEM_INCLUDE_PATH": "",
                "PKG_CONFIG_SYSTEM_LIBRARY_PATH": "",
            }
        )
        pkg_queries = [
            ["--help"],
            ["--version"],
            ["--about"],
            ["--modversion", "foo"],
            ["--cflags", "foo"],
            ["--cflags-only-I", "foo"],
            ["--libs", "foo"],
            ["--libs-only-l", "foo"],
            ["--static", "--libs", "foo"],
            ["--variable=prefix", "foo"],
            ["--variable=custom", "foo"],
            ["--print-variables", "foo"],
            ["--print-requires", "foo"],
            ["--print-requires-private", "foo"],
            ["--list-all"],
            ["--exists", "foo"],
            ["--exists", "missing"],
            ["--atleast-version=1.4", "foo"],
            ["--exact-version=1.4.2", "foo"],
            ["--max-version=1.5", "foo"],
            ["--define-variable=prefix=/tmp/override", "--variable=prefix", "foo"],
            ["--env=CHECK", "foo"],
            ["--fragment-tree", "--libs", "foo"],
        ]
        cases: list[tuple[str, list[str]]] = []
        for tool in ("pkgconf", "pkg-config"):
            cases.extend((tool, query) for query in pkg_queries)
        for tool in ("bomtool", "pccritic", "spdxtool"):
            for query in (["--help"], ["--version"], ["--about"]):
                cases.append((tool, query))

        records = []
        for index, (tool, arguments) in enumerate(cases):
            canonical = run(args.canonical_dir / tool, arguments, environment)
            hybrid = run(args.hybrid_dir / tool, arguments, environment)
            exact = canonical == hybrid
            records.append(
                {
                    "index": index,
                    "tool": tool,
                    "arguments": arguments,
                    "canonical_sha256": digest(canonical),
                    "hybrid_sha256": digest(hybrid),
                    "exact": exact,
                }
            )
            if not exact:
                raise RuntimeError(f"pkgconf differential mismatch: {tool} {arguments!r}")

    evidence = {
        "schema": 1,
        "comparisons": len(records),
        "canonical_hybrid_exact": all(record["exact"] for record in records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"comparisons": len(records), "exact": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
