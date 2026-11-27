#!/usr/bin/env python3
"""Keep one private-crate import of each selected libc signature across translated Rust modules."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from inline_source_layout import WHITESPACE
from prune_private_inlines import POINTER
from share_stdio_layout import provider_namespace
from verify_c_string_sources import syntax_tool

SOURCE = ROOT / "tools/private-inlines/src/bin/scalar-ffi.rs"
MARKER = ".rustbox-scalar-ffi-pilot"
SYMBOLS = {"free", "malloc", "realloc", "calloc", "strcmp", "strncmp", "strlen", "memcmp", "memcpy", "memmove", "memset"}


def substitute(crate, sources, tool):
    selected = json.loads(subprocess.check_output([tool, crate], input=json.dumps(sorted(sources)).encode()))
    if not selected.keys() <= sources.keys():
        raise ValueError("foreign declaration outside compiler inputs")
    groups = defaultdict(lambda: defaultdict(list))
    for module, declarations in selected.items():
        for signature, start, end, after in declarations:
            symbol = signature[3:signature.index("(")]
            if symbol in SYMBOLS:
                groups[symbol][signature].append((module, start, end, after))

    edits = defaultdict(list)
    imports = defaultdict(list)
    owners = {}
    removed = 0
    for symbol, variants in sorted(groups.items()):
        if len(variants) != 1:
            continue
        signature, declarations = next(iter(variants.items()))
        declarations.sort()
        if len(declarations) < 2 or len({row[0] for row in declarations}) != len(declarations):
            continue
        owner, start, _, _ = declarations[0]
        namespace = provider_namespace(crate / "lib.rs", Path(owner)).with_suffix("")
        if not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part) for part in namespace.parts):
            raise ValueError("unexpected scalar ABI provider namespace")
        qualified = "crate::" + "::".join((*namespace.parts, symbol))
        edits[owner].append((start, start, b"pub(crate) "))
        owners[symbol] = dict(signature=signature, provider=owner, copies=len(declarations))
        for module, start, end, after in declarations[1:]:
            edits[module].append((start, end, None))
            imports[module, after].append(qualified)
            removed += signature.count("*")
    if not owners:
        raise ValueError("no repeated eligible libc interfaces in this crate")
    for (module, after), paths in imports.items():
        edits[module].append((after, after, "".join(" use " + p + ";" for p in sorted(paths)).encode()))

    changes = {}
    observed = 0
    for module, module_edits in edits.items():
        data = (crate / module).read_bytes()
        stop = 0
        parts = []
        for start, end, replacement in sorted(module_edits, key=lambda e: (e[0], e[1])):
            if not stop <= start <= end <= len(data):
                raise ValueError("overlapping foreign declaration edits")
            old = data[start:end]
            if replacement is None:
                if not old.startswith(b"fn ") or not old.endswith(b";"):
                    raise ValueError("unexpected foreign declaration range")
                replacement = old.translate(WHITESPACE)
            elif replacement.startswith(b" use ") and (data[start-1:start] != b"}" or data[start:start+1] not in (b"\n",b"\r",b"")):
                raise ValueError("foreign import moved outside the module boundary")
            parts.extend((data[stop:start], replacement))
            stop = end
        new = b"".join([*parts, data[stop:]])
        observed += len(POINTER.findall(data)) - len(POINTER.findall(new))
        changes[module] = new
    if observed != removed:
        raise ValueError("pointer delta disagrees with selected ABI signatures")
    return changes, dict(scalar_ffi=owners, raw_pointer_types_removed=removed, scanner_source_sha256=digest(SOURCE))


def replay_layer(parent, read_parent, row, tool):
    from hashlib import sha256
    from tempfile import TemporaryDirectory
    from check_e2fsprogs_dirhash_arrays import source_list_digest
    if len(parent) != row["compiler_selected_sources"] or source_list_digest(parent) != row["parent_sources_sha256"]:
        raise ValueError("scalar ABI parent differs from the verified compiler inputs")
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        for module, checksum in parent.items():
            relative = Path(module)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("expected a crate-relative compiler input")
            path = crate / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = read_parent(module)
            if sha256(data).hexdigest() != checksum:
                raise ValueError("scalar ABI module differs from the verified parent")
            path.write_bytes(data)
        changed, facts = substitute(crate, parent, tool)
    updated = {**parent, **{k: sha256(v).hexdigest() for k, v in changed.items()}}
    if (any(row.get(k) != v for k,v in facts.items())
            or source_list_digest(updated) != row["candidate_sources_sha256"]):
        raise ValueError("scalar ABI source replay differs from the cold compiler receipt")
    return changed


def build(link, key, output):
    origin = cargo_origin(json.loads(link.read_bytes()), key)
    if direct_crate(origin) is not None:
        from build_staged_c_strings import build as direct
        direct(link, output, key, scalar_ffi=True)
    else:
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if args.mounted:
        scanner = syntax_tool("scalar-ffi")
        compile_mounted_sources(args.mounted, lambda c,s: substitute(c,s,scanner), MARKER, allow_identical=True)
    elif args.link and args.replay:
        row = json.loads((args.replay / "pilot.json").read_bytes())
        scanner = syntax_tool("scalar-ffi")
        result = replay(args.link, row["archive"], transform=lambda c,s: substitute(c,s,scanner))
        origin = cargo_origin(json.loads(args.link.read_bytes()), row["archive"])
        if direct_crate(origin) is not None:
            result.pop("cargo_archive", None)
            result["rustc_archive"] = str(origin)
        result["candidate_sha256"] = digest(args.replay / Path(row["archive"]).name)
        if result != row:
            raise ValueError("foreign declaration source replay differs from the compiler receipt")
        print(f'Replayed {row["raw_pointer_types_removed"]} duplicate pointer declarations.')
    elif args.link and args.archive and args.output:
        build(args.link, args.archive, args.output)
    else:
        parser.error("supply a link and an archive and output, or a pilot to replay")
