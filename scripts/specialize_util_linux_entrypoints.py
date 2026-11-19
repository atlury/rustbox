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


SAFE_APPLET = re.compile(r"^[a-z0-9_.-]+$")
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
    configured = manifest.get("entrypoints")
    if configured is None:
        entrypoints = {
            name: {
                "symbol": re.sub(r"[^a-z0-9_]", "_", name),
                "public_names": [name],
            }
            for name in applets
        }
    elif isinstance(configured, dict):
        entrypoints = configured
    else:
        raise RuntimeError("entrypoints must be an object")
    public_names = [
        name
        for record in entrypoints.values()
        for name in record.get("public_names", [])
    ]
    if sorted(public_names) != sorted(applets) or len(set(public_names)) != len(applets):
        raise RuntimeError("entrypoint public names differ from applets")
    symbol_tokens = {
        source_stem: record.get("symbol")
        for source_stem, record in entrypoints.items()
    }
    if not all(
        isinstance(token, str) and re.fullmatch(r"[a-z0-9_]+", token)
        for token in symbol_tokens.values()
    ):
        raise RuntimeError(f"unsafe entrypoint symbol: {symbol_tokens}")
    if len(set(symbol_tokens.values())) != len(symbol_tokens):
        raise RuntimeError(f"entrypoint symbols collide: {symbol_tokens}")
    if set(by_stem) != set(entrypoints) or len(by_stem) != len(entries):
        raise RuntimeError(
            f"entrypoint sources differ from applets: sources={sorted(by_stem)}, "
            f"entrypoints={sorted(entrypoints)}"
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
    for source_stem, configuration in entrypoints.items():
        entry = json.loads(json.dumps(by_stem[source_stem]))
        source = Path(entry["file"]).resolve()
        try:
            relative = source.relative_to(source_root)
        except ValueError as error:
            raise RuntimeError(f"source is outside normalized root: {source}") from error
        destination = specialized_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        before = source.read_text(encoding="utf-8")
        symbol = f"rustbox_{symbol_tokens[source_stem]}_main"
        after, replacements = MAIN_DEFINITION.subn(
            f"int {symbol}(", before, count=1
        )
        if replacements != 1 or MAIN_DEFINITION.search(after):
            raise RuntimeError(f"expected exactly one main definition: {source_stem}")
        destination.write_text(after, encoding="utf-8")

        arguments = entry["arguments"]
        if arguments.count(str(source)) != 1:
            raise RuntimeError(f"compile action source is not unique: {source_stem}")
        arguments[arguments.index(str(source))] = str(destination)
        compile_index = arguments.index("-c")
        arguments.insert(
            compile_index,
            f"-fmacro-prefix-map={specialized_root}={source_root}",
        )
        object_path = object_root / f"{symbol_tokens[source_stem]}.o"
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
                f"specialized compile failed for {source_stem}: {process.stderr[-4000:]}"
            )
        symbols = subprocess.run(
            ["nm", "-g", "--defined-only", str(object_path)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        defined = [line.split()[-1] for line in symbols if line.split()]
        if symbol not in defined or "main" in defined:
            raise RuntimeError(f"wrong specialized symbols for {source_stem}: {defined}")

        entry["file"] = str(destination)
        entry["output"] = str(object_path)
        rewritten.append(entry)
        records[source_stem] = {
            "canonical_entrypoint": "main",
            "specialized_entrypoint": symbol,
            "public_names": configuration["public_names"],
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
