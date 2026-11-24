#!/usr/bin/env python3
"""Select exact per-engine IPRoute2 source closures from GNU linker maps."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import re
import shlex
from collections import defaultdict
from pathlib import Path

from normalize_iproute2 import ENTRYPOINTS


SOURCE_ROOT = Path("/rustbox-iproute2/normalized-clang-18")
MAP_BUILD_ROOT = Path("/rustbox-iproute2/normalized-gcc")
ARCHIVE_MEMBER = re.compile(r"^(?P<archive>\S+\.a)\((?P<member>[^)]+)\)$")
GENERATED_ACTION_TEMPLATES = {
    "tc/emp_ematch.lex.c": "tc/emp_ematch.tab.c",
}


def arguments(record: dict[str, object]) -> list[str]:
    values = record.get("arguments")
    if values is None:
        values = shlex.split(str(record["command"]))
    return [str(value) for value in values]


def rooted_path(record: dict[str, object], field: str) -> Path:
    path = Path(str(record[field]))
    if not path.is_absolute():
        path = Path(str(record["directory"])) / path
    return path.resolve()


def choose_compile_action(
    source: str, candidates: list[dict[str, object]]
) -> dict[str, object]:
    record = max(
        candidates,
        key=lambda item: (
            int(arguments(item).count("-c") == 1),
            int("-cc1" not in arguments(item)),
            len(arguments(item)),
            "\0".join(arguments(item)),
        ),
    )
    if arguments(record).count("-c") != 1:
        raise RuntimeError(f"no driver compile action for IPRoute2 source: {source}")
    return record


def index_database(records: list[dict[str, object]]) -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    dict[str, int],
    set[str],
]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for original in records:
        source = rooted_path(original, "file")
        if not source.is_relative_to(SOURCE_ROOT):
            raise RuntimeError(f"IPRoute2 compile action escaped normalized root: {source}")
        grouped[source.relative_to(SOURCE_ROOT).as_posix()].append(dict(original))

    by_source = {
        source: choose_compile_action(source, candidates)
        for source, candidates in grouped.items()
    }
    variants = {source: len(candidates) for source, candidates in grouped.items()}
    synthesized = set()
    for source, template_source in GENERATED_ACTION_TEMPLATES.items():
        generated_path = SOURCE_ROOT / source
        if source in by_source or template_source not in by_source:
            raise RuntimeError(f"IPRoute2 generated-action inventory changed: {source}")
        record = copy.deepcopy(by_source[template_source])
        source_name = Path(source).name
        object_name = Path(source).with_suffix(".o").name
        template_name = Path(template_source).name
        template_object = Path(template_source).with_suffix(".o").name
        compile_args = arguments(record)
        if compile_args.count(template_name) != 1 or compile_args.count(template_object) != 1:
            raise RuntimeError(f"generated-action template changed: {template_source}")
        record["arguments"] = [
            source_name if value == template_name
            else object_name if value == template_object
            else value
            for value in compile_args
        ]
        record["file"] = str(generated_path)
        record["output"] = str(generated_path.with_suffix(".o"))
        by_source[source] = record
        variants[source] = 1
        synthesized.add(source)

    by_object: dict[str, dict[str, object]] = {}
    for source, record in by_source.items():
        output = rooted_path(record, "output")
        # Four misc utilities are compiled and linked in one invocation.  Bear
        # reports their executable as the output; their source is included as
        # the main source below and must not masquerade as an object file.
        if output.suffix != ".o" or not output.is_relative_to(SOURCE_ROOT):
            continue
        relative_object = output.relative_to(SOURCE_ROOT).as_posix()
        if relative_object in by_object:
            raise RuntimeError(f"duplicate IPRoute2 object action: {relative_object}")
        by_object[relative_object] = record
    return by_source, by_object, variants, synthesized


def internal_object(
    map_path: str, program_directory: str, by_object: dict[str, dict[str, object]]
) -> tuple[str, dict[str, object]] | None:
    path = Path(map_path)
    if path.is_absolute():
        resolved = path.resolve()
        if resolved.is_relative_to(MAP_BUILD_ROOT):
            resolved = SOURCE_ROOT / resolved.relative_to(MAP_BUILD_ROOT)
    else:
        relative = posixpath.normpath(posixpath.join(program_directory, map_path))
        resolved = (SOURCE_ROOT / relative).resolve()
    if not resolved.is_relative_to(SOURCE_ROOT):
        return None
    relative_object = resolved.relative_to(SOURCE_ROOT).as_posix()
    record = by_object.get(relative_object)
    if record is None:
        raise RuntimeError(f"no compile action for internal map object: {relative_object}")
    return relative_object, record


def prepare_engine(
    program: str,
    main_source: str,
    map_path: Path,
    output_directory: Path,
    by_source: dict[str, dict[str, object]],
    by_object: dict[str, dict[str, object]],
    variants: dict[str, int],
    synthesized: set[str],
    database_sha256: str,
) -> dict[str, object]:
    if main_source not in by_source:
        raise RuntimeError(f"missing IPRoute2 main source: {main_source}")
    if not map_path.is_file() or map_path.stat().st_size == 0:
        raise RuntimeError(f"missing IPRoute2 linker map: {map_path}")

    selected = {main_source: by_source[main_source]}
    archive_objects: list[str] = []
    map_lines = map_path.read_text(errors="replace").splitlines()
    program_directory = Path(main_source).parent.as_posix()

    # GNU ld lists only archive members actually selected by symbol resolution
    # in this opening section.  Resolve an archive relative to the engine build
    # directory, then resolve its member beside that archive.
    for line in map_lines:
        if line == "Merging program properties":
            break
        token = line.strip().split(maxsplit=1)[0] if line.strip() else ""
        match = ARCHIVE_MEMBER.match(token)
        if match is None:
            continue
        archive = Path(match.group("archive"))
        if archive.is_absolute():
            archive_path = archive.resolve()
            if archive_path.is_relative_to(MAP_BUILD_ROOT):
                archive_path = SOURCE_ROOT / archive_path.relative_to(MAP_BUILD_ROOT)
        else:
            relative_archive = posixpath.normpath(
                posixpath.join(program_directory, match.group("archive"))
            )
            archive_path = (SOURCE_ROOT / relative_archive).resolve()
        if not archive_path.is_relative_to(SOURCE_ROOT):
            continue
        member_path = archive_path.parent / match.group("member")
        resolved = internal_object(str(member_path), program_directory, by_object)
        if resolved is None:
            raise RuntimeError(f"internal archive member escaped root: {token}")
        relative_object, record = resolved
        relative_source = rooted_path(record, "file").relative_to(SOURCE_ROOT).as_posix()
        selected[relative_source] = record
        archive_objects.append(relative_object)

    direct_objects: list[str] = []
    compiler_temporary_objects: list[str] = []
    for line in map_lines:
        if not line.startswith("LOAD "):
            continue
        load_path = line.removeprefix("LOAD ").strip()
        if not load_path.endswith(".o"):
            continue
        saved_main_object = f"{program}-{Path(main_source).stem}.o"
        if not Path(load_path).is_absolute() and Path(load_path).name == saved_main_object:
            compiler_temporary_objects.append(
                posixpath.normpath(posixpath.join(program_directory, load_path))
            )
            continue
        resolved = internal_object(load_path, program_directory, by_object)
        if resolved is None:
            continue
        relative_object, record = resolved
        relative_source = rooted_path(record, "file").relative_to(SOURCE_ROOT).as_posix()
        selected[relative_source] = record
        direct_objects.append(relative_object)

    for source in selected:
        if not (SOURCE_ROOT / source).is_file():
            raise RuntimeError(f"selected IPRoute2 source is absent: {source}")

    output_records = []
    for source in sorted(selected):
        record = json.loads(json.dumps(selected[source]))
        compile_args = arguments(record)
        if compile_args.count("-c") != 1:
            raise RuntimeError(f"malformed IPRoute2 compile action: {source}")
        compile_args.insert(compile_args.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record.pop("command", None)
        record["arguments"] = compile_args
        record["file"] = str(SOURCE_ROOT / source)
        output_records.append(record)

    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / "compile_commands.json"
    output.write_text(json.dumps(output_records, indent=2) + "\n")
    manifest = {
        "schema": 1,
        "release": "7.3.0",
        "program": program,
        "main_source": main_source,
        "sources": sorted(selected),
        "source_count": len(selected),
        "archive_objects": sorted(set(archive_objects)),
        "direct_objects": sorted(set(direct_objects)),
        "compiler_temporary_objects": sorted(set(compiler_temporary_objects)),
        "compile_commands": len(output_records),
        "duplicate_actions_collapsed": sum(variants[source] - 1 for source in selected),
        "generated_actions": sorted(set(selected) & synthesized),
        "multicall_define": True,
        "source_root": str(SOURCE_ROOT),
        "compile_database_input_sha256": database_sha256,
        "compile_database_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "linker_map_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
    }
    manifest_path = output_directory / "closure.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--maps-directory", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--program", action="append", choices=sorted(ENTRYPOINTS))
    args = parser.parse_args()

    database_bytes = args.database.read_bytes()
    records = json.loads(database_bytes)
    by_source, by_object, variants, synthesized = index_database(records)
    programs = args.program or sorted(ENTRYPOINTS)
    manifests = {}
    for program in programs:
        main_source = ENTRYPOINTS[program][0]
        manifests[program] = prepare_engine(
            program,
            main_source,
            args.maps_directory / f"{program}.map",
            args.output_directory / program,
            by_source,
            by_object,
            variants,
            synthesized,
            hashlib.sha256(database_bytes).hexdigest(),
        )

    counts = {program: manifests[program]["source_count"] for program in programs}
    union = sorted({source for manifest in manifests.values() for source in manifest["sources"]})
    summary = {
        "schema": 1,
        "release": "7.3.0",
        "engines": len(programs),
        "source_counts": counts,
        "sum_of_engine_source_counts": sum(counts.values()),
        "unique_sources": len(union),
        "sources": union,
    }
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "closure-counts.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary | {"sources": len(union)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
