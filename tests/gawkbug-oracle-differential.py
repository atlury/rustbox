#!/usr/bin/env python3
"""Stateful parity checks for the native GNU gawkbug frontend."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def digest(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def invoke(
    binary: Path, arguments: list[str], root: Path, editor: Path,
    stdin: bytes, *, canonical: bool, mail_status: int = 0,
) -> dict[str, object]:
    temporary = root / "tmp"
    home = root / "home"
    tools = root / "tools"
    for directory in (temporary, home, tools):
        directory.mkdir(parents=True, exist_ok=True)
    capture = root / "mail.capture"
    rmail = tools / "rmail"
    rmail.write_text(
        "#!/bin/sh\ncat >\"$CAPTURE\"\nexit \"$RMAIL_STATUS\"\n",
        encoding="utf-8",
    )
    rmail.chmod(0o755)
    environment = {
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": str(tools),
        "TMPDIR": str(temporary),
        "HOME": str(home),
        "USER": "rustbox-tester",
        "LOGNAME": "rustbox-tester",
        "EDITOR": str(editor),
        "CAPTURE": str(capture),
        "RMAIL_STATUS": str(mail_status),
    }
    command = [str(binary), *arguments] if canonical else [str(binary), "gawkbug", *arguments]
    process = subprocess.run(
        command, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=environment, timeout=20,
    )
    stdout = process.stdout
    stderr = process.stderr
    replacements = [(str(root).encode(), b"<ROOT>")]
    if canonical:
        replacements.append((str(binary).encode(), b"gawkbug"))
    for source, destination in replacements:
        stdout = stdout.replace(source, destination)
        stderr = stderr.replace(source, destination)
    return {
        "status": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "dead_letter": digest(home / "dead.gawkbug"),
        "mail_capture": digest(capture),
        "dead_letter_bytes": (home / "dead.gawkbug").read_bytes()
        if (home / "dead.gawkbug").is_file() else None,
        "mail_capture_bytes": capture.read_bytes() if capture.is_file() else None,
    }


def serial(value: dict[str, object]) -> dict[str, object]:
    return {
        key: (data.decode("utf-8", "backslashreplace") if isinstance(data, bytes) else data)
        for key, data in value.items()
        if not key.endswith("_bytes")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--rustbox", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    canonical = args.canonical.resolve()
    rustbox = args.rustbox.resolve()
    records: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="rustbox-gawkbug-") as temporary_name:
        root = Path(temporary_name)
        unchanged = root / "editor-unchanged"
        unchanged.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        unchanged.chmod(0o755)
        changed = root / "editor-changed"
        changed.write_text(
            "#!/bin/sh\n"
            "sed 's/^Subject:.*/Subject: deterministic report/' \"$1\" >\"$1.new\"\n"
            "mv \"$1.new\" \"$1\"\n",
            encoding="utf-8",
        )
        changed.chmod(0o755)
        failing = Path("/bin/false")
        cases = [
            ("unchanged-give-up", [], unchanged, b"y\n", 0),
            ("editor-failure-give-up", [], failing, b"y\n", 0),
            ("changed-decline", [], changed, b"n\n", 0),
            ("changed-custom-address-decline", ["bugs@example.test"], changed, b"n\n", 0),
            ("changed-send", ["bugs@example.test"], changed, b"y\n", 0),
            ("changed-mail-failure", ["bugs@example.test"], changed, b"y\n", 1),
        ]
        for label, arguments, editor, stdin, mail_status in cases:
            canonical_root = root / f"canonical-{label}"
            rustbox_root = root / f"rustbox-{label}"
            left = invoke(canonical, arguments, canonical_root, editor, stdin,
                          canonical=True, mail_status=mail_status)
            right = invoke(rustbox, arguments, rustbox_root, editor, stdin,
                           canonical=False, mail_status=mail_status)
            passed = left == right
            records.append({
                "label": label,
                "arguments": arguments,
                "passed": passed,
                "canonical": serial(left),
                "rustbox": serial(right),
            })

    result = {
        "schema": 1,
        "cases": len(records),
        "passed": sum(bool(record["passed"]) for record in records),
        "results": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"cases": result["cases"], "passed": result["passed"]}, sort_keys=True))
    return 0 if result["cases"] == result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
