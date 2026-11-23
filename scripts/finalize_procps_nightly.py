#!/usr/bin/env python3
"""Repair the three C2Rust representation errors in translated Procps-ng."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from modernize_c2rust_output import (
    deduplicate_function_static_exports,
    deduplicate_no_mangle_functions,
    deduplicate_no_mangle_statics,
)


STACK_DECLARATION = """    static mut stack: [stat_result; 15] = [stat_result {
        item: STAT_noop,
        result: C2RustUnnamed_15 { s_int: 0 },
    }; 15];
"""

GLOBAL_STACKS = """static mut SUM_UNIFY_STACK: [stat_result; 15] = [stat_result {
    item: STAT_noop,
    result: C2RustUnnamed_15 { s_int: 0 },
}; 15];
static mut SUM_VERSUS_STACK: [stat_result; 15] = [stat_result {
    item: STAT_noop,
    result: C2RustUnnamed_15 { s_int: 0 },
}; 15];
"""

WATCH_BOOL_ORIGINAL = """            sleep_dontsleep = (sleep_dontsleep as ::core::ffi::c_int
                | (screen_size_changed as ::core::ffi::c_int != 0
                    && flags & WATCH_NORERUN as uf16 == 0) as ::core::ffi::c_int)
                as bool;
"""

WATCH_BOOL_REPAIRED = """            sleep_dontsleep = (sleep_dontsleep as ::core::ffi::c_int
                | (screen_size_changed as ::core::ffi::c_int != 0
                    && flags & WATCH_NORERUN as uf16 == 0) as ::core::ffi::c_int)
                != 0;
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_stack_function(
    text: str, start: str, end: str, replacement: str
) -> tuple[str, dict[str, object]]:
    begin = text.find(start)
    finish = text.find(end, begin + len(start))
    if begin < 0 or finish < 0:
        raise RuntimeError(f"translated Procps top function boundary changed: {start}")
    block = text[begin:finish]
    if block.count(STACK_DECLARATION) != 1:
        raise RuntimeError(f"translated Procps top stack changed: {start}")
    stack_uses = len(re.findall(r"\bstack\b", block)) - 1
    block = block.replace(STACK_DECLARATION, "", 1)
    block = re.sub(r"\bstack\b", replacement, block)
    return text[:begin] + block + text[finish:], {
        "function": start.split("(", 1)[0].split()[-1],
        "module_static": replacement,
        "rewritten_stack_uses": stack_uses,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output:
        raise RuntimeError("input must be a C2Rust crate and output must differ")
    if output.parent != source.parent or not output.name.endswith("-nightly"):
        raise RuntimeError("output must be a sibling ending in -nightly")

    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("target", "Cargo.lock"))

        top = staged / "src/src/top/top.rs"
        top_text = top.read_text(encoding="utf-8")
        top_before = digest(top)
        anchor = "static mut accum: stat_stack = stat_stack {"
        if top_text.count(anchor) != 1 or "SUM_UNIFY_STACK" in top_text:
            raise RuntimeError("translated Procps top static layout changed")
        top_text = top_text.replace(anchor, GLOBAL_STACKS + anchor, 1)
        top_text, unify = rewrite_stack_function(
            top_text,
            'unsafe extern "C" fn sum_unify(',
            'unsafe extern "C" fn sum_versus(',
            "SUM_UNIFY_STACK",
        )
        top_text, versus = rewrite_stack_function(
            top_text,
            'unsafe extern "C" fn sum_versus(',
            'unsafe extern "C" fn do_cpus(',
            "SUM_VERSUS_STACK",
        )
        initializer = "(&raw const stack as *mut stat_result)"
        if top_text.count(initializer) != 2:
            raise RuntimeError("translated Procps top initializer shape changed")
        top_text = top_text.replace(
            initializer, "(&raw const SUM_UNIFY_STACK as *mut stat_result)", 1
        ).replace(
            initializer, "(&raw const SUM_VERSUS_STACK as *mut stat_result)", 1
        )
        top.write_text(top_text, encoding="utf-8")

        watch = staged / "src/src/watch.rs"
        watch_text = watch.read_text(encoding="utf-8")
        watch_before = digest(watch)
        if watch_text.count(WATCH_BOOL_ORIGINAL) != 1:
            raise RuntimeError("translated Procps watch boolean shape changed")
        watch.write_text(
            watch_text.replace(WATCH_BOOL_ORIGINAL, WATCH_BOOL_REPAIRED, 1),
            encoding="utf-8",
        )

        duplicate_exports_mangled = [
            *deduplicate_no_mangle_functions(staged),
            *deduplicate_no_mangle_statics(staged),
            *deduplicate_function_static_exports(staged),
        ]
        if [item["symbol"] for item in duplicate_exports_mangled] != [
            "Items", "Pids_info"
        ]:
            raise RuntimeError("translated Procps duplicate-export inventory changed")

        manifest = {
            "schema": 1,
            "toolchain": "nightly-2023-04-15",
            "semantic_repairs": 3,
            "thread_local_attributes_preserved": sum(
                path.read_text(encoding="utf-8").count("#[thread_local]")
                for path in staged.rglob("*.rs")
            ),
            "duplicate_exports_mangled": duplicate_exports_mangled,
            "changes": [
                {
                    "path": "src/src/top/top.rs",
                    "before_sha256": top_before,
                    "after_sha256": digest(top),
                    "operation": "hoist two C function-local static arrays for translated initializers",
                    "functions": [unify, versus],
                },
                {
                    "path": "src/src/watch.rs",
                    "before_sha256": watch_before,
                    "after_sha256": digest(watch),
                    "operation": "spell C integer-to-bool conversion as a nonzero comparison",
                    "occurrences": 1,
                },
            ],
        }
        if manifest["thread_local_attributes_preserved"] != 29:
            raise RuntimeError("translated Procps thread-local inventory changed")
        (staged / "rustbox-procps-nightly.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    print(json.dumps({
        "repairs": manifest["semantic_repairs"],
        "duplicate_exports_mangled": len(manifest["duplicate_exports_mangled"]),
        "thread_local_attributes_preserved": manifest["thread_local_attributes_preserved"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
