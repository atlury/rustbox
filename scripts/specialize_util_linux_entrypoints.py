#!/usr/bin/env python3
"""Give standalone util-linux main functions stable, unique hybrid ABI names."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


SAFE_APPLET = re.compile(r"^[a-z0-9_]+$")
MAIN_DEFINITION = re.compile(r"\bint\s+main\s*\(")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    entries = json.loads(args.database.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    applets = manifest["applets"]
    if not all(isinstance(name, str) and SAFE_APPLET.fullmatch(name) for name in applets):
        raise RuntimeError("unsafe applet name in manifest")
    by_stem = {Path(entry["file"]).stem: entry for entry in entries}
    if set(by_stem) != set(applets) or len(by_stem) != len(entries):
        raise RuntimeError(
            f"entrypoint sources differ from applets: sources={sorted(by_stem)}, "
            f"applets={sorted(applets)}"
        )

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    specialized_root = output.parent / "source"
    object_root = output.parent / "objects"
    if specialized_root.exists():
        shutil.rmtree(specialized_root)
    if object_root.exists():
        shutil.rmtree(object_root)
    specialized_root.mkdir(parents=True)
    object_root.mkdir(parents=True)
    rewritten = []
    records = {}
    for applet in applets:
        entry = json.loads(json.dumps(by_stem[applet]))
        source = Path(entry["file"]).resolve()
        try:
            relative = source.relative_to(source_root)
        except ValueError as error:
            raise RuntimeError(f"source is outside normalized root: {source}") from error
        destination = specialized_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        before = source.read_text(encoding="utf-8")
        symbol = f"rustbox_{applet}_main"
        after, replacements = MAIN_DEFINITION.subn(
            f"int {symbol}(", before, count=1
        )
        if replacements != 1 or MAIN_DEFINITION.search(after):
            raise RuntimeError(f"expected exactly one main definition: {applet}")
        destination.write_text(after, encoding="utf-8")

        arguments = entry["arguments"]
        if arguments.count(str(source)) != 1:
            raise RuntimeError(f"compile action source is not unique: {applet}")
        arguments[arguments.index(str(source))] = str(destination)
        compile_index = arguments.index("-c")
        arguments.insert(
            compile_index,
            f"-fmacro-prefix-map={specialized_root}={source_root}",
        )
        object_path = object_root / f"{applet}.o"
        output_index = arguments.index("-o") + 1
        arguments[output_index] = str(object_path)
        process = subprocess.run(
            arguments,
            cwd=entry["directory"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.returncode:
            raise RuntimeError(
                f"specialized compile failed for {applet}: {process.stderr[-4000:]}"
            )
        symbols = subprocess.run(
            ["nm", "-g", "--defined-only", str(object_path)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        defined = [line.split()[-1] for line in symbols if line.split()]
        if symbol not in defined or "main" in defined:
            raise RuntimeError(f"wrong specialized symbols for {applet}: {defined}")

        entry["file"] = str(destination)
        entry["output"] = str(object_path)
        rewritten.append(entry)
        records[applet] = {
            "canonical_entrypoint": "main",
            "specialized_entrypoint": symbol,
            "before_sha256": sha256(source),
            "after_sha256": sha256(destination),
            "compiler_replay": "pass",
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rewritten, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "schema": 1,
        "database_sha256": sha256(output),
        "entrypoints": records,
    }
    (output.parent / "entrypoints.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "commands": len(rewritten),
        "database_sha256": evidence["database_sha256"],
        "entrypoints": {name: record["specialized_entrypoint"] for name, record in records.items()},
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
