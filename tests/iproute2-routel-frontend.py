#!/usr/bin/env python3
"""Exact synthetic differential for the native IPRoute2 routel frontend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(
    command: list[str], environment: dict[str, str], *, executable: Path | None = None
) -> tuple[int, bytes, bytes]:
    process = subprocess.run(
        command,
        executable=executable,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    return process.returncode, process.stdout, process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path, action="append")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="rustbox-routel-") as temporary:
        temporary_path = Path(temporary)
        fake_ip = temporary_path / "ip"
        fake_ip.write_text(
            "#!/usr/bin/env python3\n"
            "import os,sys\n"
            "p=os.environ.get('RUSTBOX_ROUTEL_ARGV_LOG')\n"
            "if p: open(p,'wb').write(b'\\0'.join(x.encode() for x in sys.argv)+b'\\n')\n"
            "sys.stdout.write(os.environ.get('RUSTBOX_ROUTEL_JSON','[]'))\n"
        )
        fake_ip.chmod(0o755)

        large = [
            {
                "dst": f"10.{index // 256}.{index % 256}.0/24",
                "gateway": "192.0.2.1",
                "protocol": "static",
                "scope": "global",
                "dev": "eth0",
                "table": index,
            }
            for index in range(800)
        ]
        cases = [
            ("help-short", ["-h"], "[]"),
            ("help-long-prefix", ["--he"], "[]"),
            ("help-long-prefix-argument", ["--he=value"], "[]"),
            ("unknown-short", ["-V"], "[]"),
            ("unknown-long", ["--definitely-invalid"], "[]"),
            ("missing-family-short", ["-f"], "[]"),
            ("missing-family-long", ["--family"], "[]"),
            ("missing-family-prefix", ["--fam"], "[]"),
            ("unknown-after-help", ["-hV"], "[]"),
            ("empty-ipv4", [], "[]"),
            ("empty-ipv6", ["-6"], "[]"),
            (
                "ipv4-fields",
                ["254", "type", "unicast"],
                json.dumps(
                    [
                        {
                            "dst": "default",
                            "gateway": "192.0.2.1",
                            "prefsrc": "192.0.2.44",
                            "protocol": "static",
                            "scope": "global",
                            "dev": "ethernet-long-name",
                            "table": 254,
                            "ignored": {"nested": [1, 2, {"x": True}]},
                        },
                        {"dst": "198.51.100.0/24", "dev": "eth0"},
                    ],
                    separators=(",", ":"),
                ),
            ),
            (
                "ipv6-unicode",
                ["--family=inet6", "main"],
                '[{"dst":"2001:db8::/64","gateway":"fe80::1",'
                '"protocol":"ra","scope":"global","dev":"v\\u00e9th0",'
                '"table":"main"}]',
            ),
            (
                "family-prefix",
                ["--fam", "inet6", "all"],
                '[{"dst":"default","dev":"eth0","table":"all"}]',
            ),
            ("clustered-family", ["-46", "main"], "[]"),
            ("large-deadlock-proof", ["all"], json.dumps(large, separators=(",", ":"))),
        ]

        for name, arguments, route_json in cases:
            canonical_log = temporary_path / f"{name}-canonical.args"
            common = os.environ.copy()
            common.update(
                {
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "PATH": f"{temporary_path}:{common.get('PATH', '')}",
                    "RUSTBOX_ROUTEL_JSON": route_json,
                }
            )
            canonical_environment = common | {
                "RUSTBOX_ROUTEL_ARGV_LOG": str(canonical_log)
            }
            canonical = run(
                [sys.executable, str(args.canonical), *arguments], canonical_environment
            )
            logical = b"routel"
            canonical = (
                canonical[0],
                canonical[1].replace(str(args.canonical).encode(), logical),
                canonical[2].replace(str(args.canonical).encode(), logical),
            )
            canonical_arguments = canonical_log.read_bytes() if canonical_log.exists() else b""
            if canonical_arguments:
                canonical_parts = canonical_arguments.split(b"\0")
                canonical_parts[0] = b"ip"
                canonical_arguments = b"\0".join(canonical_parts)
            for native_index, native_path in enumerate(args.native):
                native_log = temporary_path / f"{name}-native-{native_index}.args"
                native_environment = common | {
                    "RUSTBOX_ROUTEL_ARGV_LOG": str(native_log)
                }
                native = run(
                    ["routel", *arguments], native_environment, executable=native_path
                )
                native_arguments = (
                    native_log.read_bytes() if native_log.exists() else b""
                )
                if canonical != native or canonical_arguments != native_arguments:
                    raise RuntimeError(
                        f"routel mismatch for {name} native {native_index}: "
                        f"canonical={canonical!r} native={native!r} "
                        f"canonical_argv={canonical_arguments!r} "
                        f"native_argv={native_arguments!r}"
                    )
            records.append(
                {
                    "name": name,
                    "arguments": arguments,
                    "passed": True,
                    "ip_argv_exact": True,
                    "status": canonical[0],
                    "stdout_bytes": len(canonical[1]),
                    "stdout_sha256": digest(canonical[1]),
                    "stderr_bytes": len(canonical[2]),
                    "stderr_sha256": digest(canonical[2]),
                    "json_bytes": len(route_json.encode()),
                }
            )

    result = {
        "schema": 1,
        "release": "7.3.0",
        "cases": len(records),
        "passed": len(records),
        "large_capture_bytes": max(record["json_bytes"] for record in records),
        "canonical_native_exact": True,
        "native_frontends": len(args.native),
        "ip_argv_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("cases", "passed", "large_capture_bytes")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
