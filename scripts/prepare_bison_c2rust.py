#!/usr/bin/env python3
"""Select GNU Bison's exact normalized production closure for C2Rust."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--normalization", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.normalization.read_text())
    if manifest["changed_sources"] != ["src/main.c"]:
        raise RuntimeError("Bison normalization source set changed")
    if manifest["entrypoint"] != "rustbox_bison_main":
        raise RuntimeError("Bison multicall entrypoint changed")

    records = json.loads(args.database.read_text())
    if len(records) != 154:
        raise RuntimeError("Bison normalized compile database changed")
    selected = []
    excluded = []
    for record in records:
        source = record["file"]
        if source.endswith(("/lib/main.c", "/lib/yyerror.c")):
            excluded.append(source)
            continue
        arguments = list(record["arguments"])
        if "-DRUSTBOX_MULTICALL" not in arguments:
            arguments.insert(1, "-DRUSTBOX_MULTICALL")
        updated = dict(record)
        updated["arguments"] = arguments
        selected.append(updated)

    sources = sorted({record["file"] for record in selected})
    if len(selected) != 152 or len(sources) != 152 or len(excluded) != 2:
        raise RuntimeError(
            f"Bison final production closure changed: "
            f"{len(selected)}/{len(sources)}/{len(excluded)}"
        )
    if any(not source.startswith("/rustbox-bison/normalized-source/") for source in sources):
        raise RuntimeError("Bison final closure escapes normalized source")
    if not any(source.endswith("/src/main.c") for source in sources):
        raise RuntimeError("Bison multicall entrypoint source is absent")
    for generated in ("parse-gram.c", "scan-code-c.c", "scan-gram-c.c", "scan-skel-c.c"):
        if sum(source.endswith("/src/" + generated) for source in sources) != 1:
            raise RuntimeError(f"Bison generated production source changed: {generated}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    print(json.dumps({
        "commands": len(selected),
        "excluded_liby_sources": len(excluded),
        "sources": len(sources),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
