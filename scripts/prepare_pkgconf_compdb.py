#!/usr/bin/env python3
"""Select pkgconf's exact four-tool production closure from Meson."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


PREFIXES = ("libpkgconf.a.p/", "pkgconf.p/", "bomtool.p/", "pccritic.p/", "spdxtool.p/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-list", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    selected = [record for record in records if str(record.get("output", "")).startswith(PREFIXES)]
    unique = {record["file"] for record in selected}
    counts = Counter(str(record["output"]).split(".p/", 1)[0] + ".p/" for record in selected)
    expected = {
        "libpkgconf.a.p/": 21,
        "pkgconf.p/": 4,
        "bomtool.p/": 2,
        "pccritic.p/": 3,
        "spdxtool.p/": 8,
    }
    if len(selected) != 38 or len(unique) != 35 or dict(counts) != expected:
        raise RuntimeError(
            f"pkgconf production database changed: actions={len(selected)}, "
            f"sources={len(unique)}, targets={dict(counts)!r}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selected, indent=2) + "\n")
    sources = sorted({
        (Path(record["directory"]) / record["file"]).resolve()
        for record in selected
    })
    if len(sources) != 35 or any(
        not source.is_relative_to(Path("/rustbox-pkgconf/source")) for source in sources
    ):
        raise RuntimeError("pkgconf source list escapes the canonical source root")
    args.source_list.write_text("".join(f"{source}\n" for source in sources))
    print(json.dumps({"compile_actions": len(selected), "unique_sources": len(unique)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
