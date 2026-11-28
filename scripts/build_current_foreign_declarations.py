#!/usr/bin/env python3
"""Remove private foreign declarations reported dead on the current Cargo compiler inputs."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryFile

from batch_cargo_private_inlines import IDENTIFIER
from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest, layout
from inline_source_layout import WHITESPACE
from prune_private_inlines import POINTER
from rank_foreign_declarations import BLOCK, DECL

MARKER = ".rustbox-foreign-declarations-current"
SELECTOR = ROOT / "work/analysis/private-inlines-linux/release/foreign-declarations"
SCANNER = ROOT / "tools/private-inlines/src/bin/foreign-declarations.rs"


@contextmanager
def diagnostic_names(crate, sources):
    # rustc suppresses dead_code for leading underscores. Only change spelling
    # in the diagnostic compilation, keeping all byte offsets stable for syn.
    originals = {}
    try:
        for module in sources:
            path = crate / module
            data = path.read_bytes()
            counts = Counter(IDENTIFIER.findall(data))
            edits = bytearray(data)
            for block in BLOCK.finditer(data):
                offset = block.start(1)
                for line in block[1].splitlines(keepends=True):
                    declaration = DECL.match(line)
                    if declaration:
                        group = declaration.lastindex
                        name = declaration[group]
                        alias = b"z" + name[1:]
                        if name.startswith(b"_") and counts[name] == 1 and alias not in counts:
                            start = offset + declaration.start(group)
                            edits[start:start+len(name)] = alias
                            counts[alias] = 1
                    offset += len(line)
            if edits != data:
                originals[path] = data
                path.write_bytes(edits)
        yield
    finally:
        for path, data in originals.items():
            path.write_bytes(data)


def substitute(crate, sources, target):
    import tomllib

    channel = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=channel)
    command = ["cargo", "rustc", "--lib", "--release", "--locked", "--offline", "--message-format=json",
               "--", "-A", "warnings", "--force-warn", "dead_code", "--emit=metadata"]
    with diagnostic_names(crate, sources), TemporaryFile() as diagnostics:
        messages = 0
        with subprocess.Popen(command, cwd=crate, env=env, stdout=subprocess.PIPE) as child:
            for line in child.stdout:
                record = json.loads(line)
                if record.get("reason") != "compiler-message":
                    continue
                src = Path(record["target"]["src_path"])
                if src.is_relative_to(crate) and str(src.relative_to(crate)) in sources:
                    messages += 1
                    diagnostics.write(json.dumps(record["message"]).encode() + b"\n")
            if child.wait():
                raise ValueError("could not collect dead-code diagnostics for the selected target")
        if not messages:
            raise ValueError("no diagnostics for the selected library")
        diagnostics.seek(0)
        ranges = json.loads(subprocess.check_output([SELECTOR], stdin=diagnostics, cwd=crate))
    return apply_spans(crate, sources, ranges)


def apply_spans(crate, sources, ranges, *, selector=SELECTOR):
    if not ranges.keys() <= sources.keys():
        raise ValueError("diagnostic spans outside the selected compiler inputs")
    changes, pointers = {}, 0
    for module, spans in ranges.items():
        path = crate / module
        if digest(path) != sources[module]:
            raise ValueError(f"compiler input changed after diagnostics for {module}")
        data = bytearray(path.read_bytes())
        last = 0
        for start, end in spans:
            if not last <= start < end <= len(data):
                raise ValueError(f"invalid declaration offsets in {module}")
            declaration = data[start:end]
            if not declaration.startswith((b"fn ", b"static ")) or not declaration.endswith(b";"):
                raise ValueError(f"span does not delimit a foreign declaration in {module}")
            pointers += len(POINTER.findall(declaration))
            data[start:end] = data[start:end].translate(WHITESPACE)
            last = end
        changes[module] = bytes(data)
    if pointers == 0:
        raise ValueError("compiler and syntax checks found no removable pointer types")
    return changes, dict(scanner_source_sha256=digest(SCANNER), scanner_binary_sha256=digest(selector),
                         ranges=ranges, declarations_removed=sum(map(len, ranges.values())),
                         raw_pointer_types_removed=pointers)


def replay_compiler_layer(modules, read, row):
    from build_scalar_ffi import replay_layer

    def transform(crate, sources, selector):
        return apply_spans(crate, sources, row["ranges"], selector=selector)

    return replay_layer(modules, read, row, SELECTOR, transform=transform)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true", help="verify an existing compiler receipt")
    args = parser.parse_args()
    if args.mounted:
        _, target = layout(args.mounted)
        compile_mounted_sources(args.mounted, lambda crate, sources: substitute(crate, sources, ROOT / target),
                                MARKER, allow_identical=True)
    elif args.link and args.archive and args.output:
        if not args.replay:
            stage_selected_archive(args.link, args.output, args.archive, MARKER, Path(__file__).name, linux_scratch=True)
        spans = json.loads((args.output / "pilot.json").read_bytes())["ranges"]
        replay(args.link, args.archive, args.output, transform=lambda crate, sources: apply_spans(crate, sources, spans))
    else:
        parser.error("supply a link, a Cargo archive and a new output directory")
