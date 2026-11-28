"""Build or replay one GNU tar table rewrite against the selected multicall sources."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive


def main(driver, marker, substitute, *, allow_identical=False):
    parser = argparse.ArgumentParser(description=driver.stem)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, marker, allow_identical=allow_identical)
    elif args.link and args.output:
        archives = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in archives if Path(k).name == "libtar_1_35_normalized_audit.a"]
        if args.replay:
            print(json.dumps(replay(args.link, key, args.output, transform=substitute), sort_keys=True))
        else:
            stage_selected_archive(args.link, args.output, key, marker, driver.name)
    else:
        parser.error("supply the link and the archive output directory")
