#!/usr/bin/env python3
"""Compare every GNU Inetutils 2.8 executable across canonical compilers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


EXECUTABLES = {
    "dnsdomainname": "src/dnsdomainname",
    "ftp": "ftp/ftp",
    "ftpd": "ftpd/ftpd",
    "hostname": "src/hostname",
    "ifconfig": "ifconfig/ifconfig",
    "inetd": "src/inetd",
    "logger": "src/logger",
    "ping": "ping/ping",
    "ping6": "ping/ping6",
    "rcp": "src/rcp",
    "rexec": "src/rexec",
    "rexecd": "src/rexecd",
    "rlogin": "src/rlogin",
    "rlogind": "src/rlogind",
    "rsh": "src/rsh",
    "rshd": "src/rshd",
    "syslogd": "src/syslogd",
    "talk": "talk/talk",
    "talkd": "talkd/talkd",
    "telnet": "telnet/telnet",
    "telnetd": "telnetd/telnetd",
    "tftp": "src/tftp",
    "tftpd": "src/tftpd",
    "traceroute": "src/traceroute",
    "uucpd": "src/uucpd",
    "whois": "whois/whois",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(binary: Path, arguments: list[str]) -> dict[str, object]:
    environment = dict(os.environ)
    environment.update({"LC_ALL": "C", "LANG": "C", "TERM": "dumb"})
    try:
        process = subprocess.run(
            [str(binary), *arguments], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=10,
        )
        return {
            "status": process.returncode,
            "stdout_sha256": digest(process.stdout),
            "stderr_sha256": digest(process.stderr),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "timeout": True,
            "stdout_sha256": digest(error.stdout or b""),
            "stderr_sha256": digest(error.stderr or b""),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", type=Path, required=True)
    parser.add_argument("--clang-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for name, relative in EXECUTABLES.items():
        gcc = args.gcc_root / relative
        clang = args.clang_root / relative
        if not gcc.is_file() or not clang.is_file():
            raise RuntimeError(f"missing canonical {name} executable")
        for option in ("--help", "--version"):
            left = run(gcc, [option])
            right = run(clang, [option])
            passed = left == right and not left.get("timeout")
            records.append({
                "applet": name,
                "arguments": [option],
                "passed": passed,
                "result": left,
            })
            if not passed:
                raise RuntimeError(
                    f"{name} {option} differs: GCC={left!r}, Clang={right!r}"
                )
    evidence = {
        "schema": 1,
        "applets": len(EXECUTABLES),
        "cases": len(records),
        "passed": len(records),
        "gcc_clang_exact": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "applets": len(EXECUTABLES), "cases": len(records),
        "passed": len(records),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
