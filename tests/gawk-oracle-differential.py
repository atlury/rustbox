#!/usr/bin/env python3
"""Exact GCC/Clang contracts for canonical GNU Gawk 5.4.0."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def run(binary: Path, arguments: list[str], *, cwd: Path, stdin: bytes = b"",
        environment: dict[str, str] | None = None) -> dict[str, object]:
    env = os.environ.copy()
    env.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC0"})
    if environment:
        env.update(environment)
    result = subprocess.run(
        [binary.name, *arguments], executable=binary, cwd=cwd, input=stdin,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    return {
        "status": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def serial(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": result["status"],
        "stdout_bytes": len(result["stdout"]),
        "stdout_sha256": hashlib.sha256(result["stdout"]).hexdigest(),
        "stderr_bytes": len(result["stderr"]),
        "stderr_sha256": hashlib.sha256(result["stderr"]).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-build", type=Path, required=True)
    parser.add_argument("--clang-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    builds = [args.gcc_build.resolve(), args.clang_build.resolve()]
    records: list[dict[str, object]] = []

    def compare(label: str, arguments: list[str], *, cwd: Path,
                stdin: bytes = b"", environment_suffix: dict[str, str] | None = None
                ) -> None:
        values = []
        for build in builds:
            environment = dict(environment_suffix or {})
            if "GAWKLIBPATH" in environment:
                environment["GAWKLIBPATH"] = str(build / environment["GAWKLIBPATH"])
            values.append(run(build / "gawk", arguments, cwd=cwd, stdin=stdin,
                              environment=environment))
        passed = values[0] == values[1]
        records.append({"label": label, "arguments": arguments, "passed": passed,
                        "gcc": serial(values[0]), "clang": serial(values[1])})
        if not passed:
            raise RuntimeError(f"Gawk mismatch {label}: {values!r}")

    with tempfile.TemporaryDirectory(prefix="rustbox-gawk-oracle-") as temporary:
        root = Path(temporary)
        data = root / "data"
        data.write_bytes(b"alpha:10\nbeta:20\nalpha:30\nempty:\n")
        csv = root / "data.csv"
        csv.write_bytes(b'name,value\n"a,b",2\nc,3\n')
        include = root / "library.awk"
        include.write_text("function twice(x) { return x * 2 }\n")

        for option in (["--help"], ["--version"], ["--definitely-invalid"]):
            compare(option[0].lstrip("-").replace("-", "_"), option, cwd=root)

        cases = [
            ("print", ["{ print NR, $0 }"] , b"a\nb\n"),
            ("fields", ["-F:", "{ print $2, $1 }", str(data)], b""),
            ("variables", ["-v", "x=7", "BEGIN { print x * x }"], b""),
            ("arrays", ["{ n[$1] += $2 } END { for (k in n) print k, n[k] }", str(data)], b""),
            ("sorted_arrays", ["BEGIN { PROCINFO[\"sorted_in\"] = \"@ind_str_asc\"; a[\"z\"]=1; a[\"a\"]=2; for (k in a) print k, a[k] }"], b""),
            ("regex", ["/^[ab].*:[23]0$/ { print $1 }", str(data)], b""),
            ("sub_gsub", ["{ gsub(/[aeiou]/, \"_\"); print }"], b"hello\nworld\n"),
            ("split", ["BEGIN { n=split(\"a::b:c\", a, /:/); for(i=1;i<=n;i++) print i, a[i] }"], b""),
            ("match_capture", ["BEGIN { match(\"abc123\", /([a-z]+)([0-9]+)/, a); print a[1], a[2] }"], b""),
            ("printf", ["BEGIN { printf \"%08x %.3f\\n\", 48879, 1/3 }"], b""),
            ("math", ["BEGIN { print int(sqrt(81)), log(exp(2)) }"], b""),
            ("mpfr", ["-M", "-v", "PREC=200", "BEGIN { print 1/3; print 2^200 }"], b""),
            ("posix", ["--posix", "BEGIN { print length(\"abc\") }"], b""),
            ("lint", ["--lint", "BEGIN { x = 1; print x }"], b""),
            ("characters_as_bytes", ["-b", "BEGIN { print length(\"é\") }"], b""),
            ("csv", ["--csv", "NR > 1 { print $1, $2 }", str(csv)], b""),
            ("include", ["-f", str(include), "-e", "BEGIN { print twice(21) }"], b""),
            ("nextfile", ["{ print FILENAME, FNR; nextfile }", str(data), str(csv)], b""),
            ("nul_input", ["{ print length($0) }"], b"a\x00b\n"),
            ("invalid_program", ["BEGIN { if ( }"], b""),
            ("exit_status", ["BEGIN { print \"before\"; exit 37 }"], b""),
            ("extension", ["@load \"ordchr\"\nBEGIN { print ord(\"A\"), chr(66) }"], b""),
        ]
        for label, arguments, stdin in cases:
            suffix = {"GAWKLIBPATH": "extension/.libs"} if label == "extension" else None
            compare(label, arguments, cwd=root, stdin=stdin,
                    environment_suffix=suffix)

        effects = [root / "gcc.out", root / "clang.out"]
        effect_results = []
        for build, output in zip(builds, effects):
            effect_results.append(run(
                build / "gawk",
                [f'BEGIN {{ print "alpha" > "{output.name}"; print "beta" >> "{output.name}"; close("{output.name}") }}'],
                cwd=root,
            ))
        passed = effect_results[0] == effect_results[1] and effects[0].read_bytes() == effects[1].read_bytes()
        records.append({"label": "redirection", "arguments": ["output-file"],
                        "passed": passed, "gcc": serial(effect_results[0]),
                        "clang": serial(effect_results[1]),
                        "effect_sha256": hashlib.sha256(effects[0].read_bytes()).hexdigest()})
        if not passed:
            raise RuntimeError("Gawk redirection effects differ")

    output = {"schema": 1, "release": "5.4.0", "cases": len(records),
              "passed": sum(bool(record["passed"]) for record in records),
              "results": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"cases": output["cases"], "passed": output["passed"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
