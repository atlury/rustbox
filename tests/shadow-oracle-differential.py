#!/usr/bin/env python3
"""Independent public and isolated-state comparisons for canonical Shadow builds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)


@dataclass(frozen=True)
class Case:
    name: str
    program: str
    arguments: tuple[str, ...]
    stdin: bytes = b""
    stateful: bool = False


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    (root / "etc/default").mkdir(parents=True)
    (root / "home/alice").mkdir(parents=True)
    files = {
        "etc/passwd": (
            "root:x:0:0:root:/root:/bin/sh\n"
            "alice:x:1000:1000:Alice:/home/alice:/bin/sh\n"
        ),
        "etc/shadow": (
            "root:*:20000:0:99999:7:::\n"
            "alice:!:20000:0:99999:7:::\n"
        ),
        "etc/group": "root:x:0:\nusers:x:1000:alice\ndevs:x:1100:\n",
        "etc/gshadow": "root:*::\nusers:*::alice\ndevs:*::\n",
        "etc/subuid": "alice:100000:65536\n",
        "etc/subgid": "alice:100000:65536\n",
        "etc/login.defs": (
            "UID_MIN 1000\nUID_MAX 60000\n"
            "GID_MIN 1000\nGID_MAX 60000\n"
            "SUB_UID_MIN 100000\nSUB_UID_MAX 600100000\nSUB_UID_COUNT 65536\n"
            "SUB_GID_MIN 100000\nSUB_GID_MAX 600100000\nSUB_GID_COUNT 65536\n"
            "CREATE_HOME no\nUSERGROUPS_ENAB yes\nENCRYPT_METHOD SHA512\n"
        ),
        "etc/default/useradd": "GROUP=1000\nHOME=/home\nSHELL=/bin/sh\n",
        "etc/shells": "/bin/sh\n/bin/bash\n",
        "etc/nsswitch.conf": "passwd: files\ngroup: files\nshadow: files\n",
    }
    for relative, contents in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    os.chmod(root / "etc/shadow", 0o600)
    os.chmod(root / "etc/gshadow", 0o600)


def snapshot(root: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        metadata = path.lstat()
        if path.is_symlink():
            result[relative] = {
                "kind": "symlink",
                "target": os.readlink(path),
            }
        elif path.is_dir():
            result[relative] = {
                "kind": "directory",
                "mode": stat.S_IMODE(metadata.st_mode),
            }
        elif path.is_file():
            contents = path.read_bytes()
            result[relative] = {
                "kind": "file",
                "mode": stat.S_IMODE(metadata.st_mode),
                "bytes": len(contents),
                "sha256": digest(contents),
            }
        else:
            result[relative] = {"kind": "other", "mode": metadata.st_mode}
    return result


def invoke(binary: Path, case: Case, root: Path) -> dict[str, object]:
    arguments = tuple(
        str(root) if argument == "{ROOT}" else argument
        for argument in case.arguments
    )
    environment = os.environ.copy()
    environment.update({
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "PATH": "/usr/bin:/bin",
    })
    try:
        process = subprocess.run(
            [case.program, *arguments],
            executable=str(binary),
            input=case.stdin,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        status: int | str = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as error:
        status = "timeout"
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    result: dict[str, object] = {
        "status": status,
        "stdout_bytes": len(stdout),
        "stdout_sha256": digest(stdout),
        "stderr_bytes": len(stderr),
        "stderr_sha256": digest(stderr),
    }
    if case.stateful:
        result["state"] = snapshot(root)
    return result


def cases() -> list[Case]:
    public = [
        Case(f"{program}-{option[2:]}", program, (option,))
        for program in PROGRAMS
        for option in ("--help", "--version")
    ]
    deterministic = [
        Case("getsubids-missing-user", "getsubids", ("rustbox-shadow-no-user",)),
        Case("newuidmap-invalid", "newuidmap", ("not-a-pid",)),
        Case("newgidmap-invalid", "newgidmap", ("not-a-pid",)),
        Case("nologin-message", "nologin", ()),
        Case("chage-list-missing", "chage", ("-l", "rustbox-shadow-no-user")),
        Case("faillog-missing", "faillog", ("-u", "987654321")),
        Case("lastlog-missing", "lastlog", ("-u", "987654321")),
    ]
    stateful = [
        Case("chage-prefix", "chage", ("-P", "{ROOT}", "-d", "21000", "alice"), stateful=True),
        Case("chpasswd-prefix", "chpasswd", ("-P", "{ROOT}", "-e"), b"alice:$6$fixed$saltedhash\n", True),
        Case("groupadd-prefix", "groupadd", ("-P", "{ROOT}", "-g", "1200", "staff"), stateful=True),
        Case("groupdel-prefix", "groupdel", ("-P", "{ROOT}", "devs"), stateful=True),
        Case("groupmod-prefix", "groupmod", ("-P", "{ROOT}", "-n", "developers", "devs"), stateful=True),
        Case("useradd-prefix", "useradd", ("-P", "{ROOT}", "-M", "-N", "-u", "1200", "-g", "1000", "-s", "/bin/sh", "bob"), stateful=True),
        Case("userdel-prefix", "userdel", ("-P", "{ROOT}", "alice"), stateful=True),
        Case("usermod-prefix", "usermod", ("-P", "{ROOT}", "-c", "Alice Updated", "alice"), stateful=True),
    ]
    return public + deterministic + stateful


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc-root", required=True, type=Path)
    parser.add_argument("--clang-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = []
    with tempfile.TemporaryDirectory(prefix="rustbox-shadow-") as temporary:
        root = Path(temporary) / "root"
        for case in cases():
            fixture(root)
            gcc = invoke(args.gcc_root / case.program, case, root)
            fixture(root)
            clang = invoke(args.clang_root / case.program, case, root)
            records.append({
                "name": case.name,
                "program": case.program,
                "arguments": list(case.arguments),
                "stateful": case.stateful,
                "gcc": gcc,
                "clang": clang,
                "passed": gcc == clang,
            })

    passed = sum(record["passed"] for record in records)
    result = {
        "schema": 1,
        "programs": len(PROGRAMS),
        "cases": len(records),
        "stateful_cases": sum(case.stateful for case in cases()),
        "passed": passed,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    summary = {key: result[key] for key in ("programs", "cases", "stateful_cases", "passed")}
    print(json.dumps(summary, sort_keys=True))
    return 0 if passed == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
