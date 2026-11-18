#!/usr/bin/env python3
"""Compile-check one generated Cargo crate and record structured diagnostics."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Optional


def sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    return subprocess.run(
        command, cwd=cwd, env=env, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--crate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolchain")
    args = parser.parse_args()
    crate = args.crate.resolve()
    if not (crate / "Cargo.toml").is_file():
        raise RuntimeError("crate has no Cargo.toml")
    env = os.environ.copy()
    if args.toolchain:
        env["RUSTUP_TOOLCHAIN"] = args.toolchain

    process = subprocess.run(
        ["cargo", "check", "--message-format=json"],
        cwd=crate,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    levels: collections.Counter[str] = collections.Counter()
    codes: collections.Counter[str] = collections.Counter()
    build_success = False
    for line in process.stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("reason") == "compiler-message":
            diagnostic = message.get("message", {})
            levels[str(diagnostic.get("level", "unknown"))] += 1
            code = diagnostic.get("code")
            if isinstance(code, dict) and code.get("code"):
                codes[str(code["code"])] += 1
        elif message.get("reason") == "build-finished":
            build_success = bool(message.get("success"))

    result = {
        "schema": 1,
        "toolchain_request": args.toolchain or "crate default",
        "rustc": version(["rustc", "--version"], crate, env),
        "cargo": version(["cargo", "--version"], crate, env),
        "cargo_toml_sha256": sha256(crate / "Cargo.toml"),
        "cargo_lock_sha256": sha256(crate / "Cargo.lock"),
        "exit_status": process.returncode,
        "build_finished_success": build_success,
        "diagnostics_by_level": dict(sorted(levels.items())),
        "warning_codes": dict(sorted(codes.items())),
        "stderr_sha256": hashlib.sha256(process.stderr.encode()).hexdigest(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if process.returncode != 0 or not build_success or levels.get("error", 0):
        return process.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
