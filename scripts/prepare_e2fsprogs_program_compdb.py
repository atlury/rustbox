#!/usr/bin/env python3
"""Select exact per-engine E2fsprogs source closures from GNU linker maps."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import re
import shlex
from pathlib import Path

from normalize_e2fsprogs import ENTRYPOINTS


SOURCE_ROOT = Path("/work/work/normalized/e2fsprogs-1.47.4")
BUILD_ROOT = Path("/rustbox-e2fsprogs/normalized-clang-18")
MAP_BUILD_ROOT = Path("/rustbox-e2fsprogs/normalized-gcc")
ARCHIVE_MEMBER = re.compile(r"^(?P<archive>\S+\.a)\((?P<member>[^)]+)\)$")
ARCHIVE_OBJECT_DIRECTORIES = {
    "libcom_err.a": "lib/et",
    "libe2p.a": "lib/e2p",
    "libext2fs.a": "lib/ext2fs",
    "libss.a": "lib/ss",
    "libsupport.a": "lib/support",
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


def output_path(record: dict[str, object]) -> Path:
    if record.get("output"):
        return rooted_path(record, "output")
    source = rooted_path(record, "file")
    return (Path(str(record["directory"])) / source.with_suffix(".o").name).resolve()


def source_key(path: Path) -> str:
    path = path.resolve()
    if path.is_relative_to(SOURCE_ROOT):
        return path.relative_to(SOURCE_ROOT).as_posix()
    if path.is_relative_to(BUILD_ROOT):
        return "@build/" + path.relative_to(BUILD_ROOT).as_posix()
    raise RuntimeError(f"E2fsprogs compile source escaped normalized roots: {path}")


def action_sha256(record: dict[str, object]) -> str:
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def index_database(records: list[dict[str, object]]) -> tuple[
    dict[str, dict[str, object]], dict[str, dict[str, object]]
]:
    by_object: dict[str, dict[str, object]] = {}
    by_source: dict[str, dict[str, object]] = {}
    for original in records:
        record = copy.deepcopy(original)
        compile_args = arguments(record)
        if "-cc1" in compile_args:
            continue
        if compile_args.count("-c") != 1:
            raise RuntimeError("E2fsprogs database contains a non-compile action")
        output = output_path(record)
        if not output.is_relative_to(BUILD_ROOT):
            raise RuntimeError(f"E2fsprogs compile output escaped build root: {output}")
        # gen_crc32ctable is compiled with -c directly to a runnable build
        # helper name and then compiled again to its production .o.  It is not
        # a linker input; retain only actual object-producing actions here.
        if output.suffix != ".o":
            continue
        relative_object = output.relative_to(BUILD_ROOT).as_posix()
        if relative_object in by_object:
            raise RuntimeError(f"duplicate E2fsprogs object action: {relative_object}")
        key = source_key(rooted_path(record, "file"))
        by_object[relative_object] = record
        # Multiple build variants legitimately compile the same source.  The
        # linker map selects the exact object; retain this index only for the
        # transformed-entrypoint inclusion assertion below.
        by_source.setdefault(key, record)
    return by_object, by_source


def internal_object(path: str, program_directory: str) -> str | None:
    candidate = Path(path)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved.is_relative_to(MAP_BUILD_ROOT):
            resolved = BUILD_ROOT / resolved.relative_to(MAP_BUILD_ROOT)
    else:
        relative = posixpath.normpath(posixpath.join(program_directory, path))
        resolved = (BUILD_ROOT / relative).resolve()
    if not resolved.is_relative_to(BUILD_ROOT):
        return None
    return resolved.relative_to(BUILD_ROOT).as_posix()


def archive_object(
    archive_path: str, member: str, program_directory: str
) -> str | None:
    archive = Path(archive_path)
    if archive.is_absolute():
        resolved = archive.resolve()
        if resolved.is_relative_to(MAP_BUILD_ROOT):
            resolved = BUILD_ROOT / resolved.relative_to(MAP_BUILD_ROOT)
    else:
        relative = posixpath.normpath(
            posixpath.join(program_directory, archive_path)
        )
        resolved = (BUILD_ROOT / relative).resolve()
    if not resolved.is_relative_to(BUILD_ROOT):
        return None
    directory = ARCHIVE_OBJECT_DIRECTORIES.get(resolved.name)
    if directory is None:
        raise RuntimeError(f"unknown internal E2fsprogs archive: {resolved}")
    return f"{directory}/{member}"


def prepare_engine(
    program: str,
    main_source: str,
    map_path: Path,
    output_directory: Path,
    by_object: dict[str, dict[str, object]],
    database_sha256: str,
) -> dict[str, object]:
    if not map_path.is_file() or map_path.stat().st_size == 0:
        raise RuntimeError(f"missing E2fsprogs linker map: {map_path}")
    program_directory = main_source.rsplit("/", 1)[0]
    selected_objects: dict[str, dict[str, object]] = {}
    archive_objects: list[str] = []
    direct_objects: list[str] = []
    lines = map_path.read_text(errors="replace").splitlines()

    for line in lines:
        if line == "Merging program properties":
            break
        token = line.strip().split(maxsplit=1)[0] if line.strip() else ""
        match = ARCHIVE_MEMBER.match(token)
        if match is None:
            continue
        relative_object = archive_object(
            match.group("archive"), match.group("member"), program_directory
        )
        if relative_object is None:
            continue
        record = by_object.get(relative_object)
        if record is None:
            raise RuntimeError(
                f"no E2fsprogs compile action for archive member: {token} "
                f"(expected {relative_object})"
            )
        selected_objects[relative_object] = record
        archive_objects.append(relative_object)

    for line in lines:
        if not line.startswith("LOAD "):
            continue
        load_path = line.removeprefix("LOAD ").strip()
        if not load_path.endswith(".o"):
            continue
        relative_object = internal_object(load_path, program_directory)
        if relative_object is None:
            continue
        record = by_object.get(relative_object)
        if record is None:
            raise RuntimeError(
                f"no E2fsprogs compile action for direct object: {relative_object}"
            )
        selected_objects[relative_object] = record
        direct_objects.append(relative_object)

    selected_sources = {
        source_key(rooted_path(record, "file")) for record in selected_objects.values()
    }
    if main_source not in selected_sources:
        raise RuntimeError(
            f"E2fsprogs closure lost normalized entrypoint source: {program}: {main_source}"
        )

    output_records = []
    source_paths: dict[str, Path] = {}
    compile_action_hashes: dict[str, str] = {}
    for relative_object in sorted(selected_objects):
        record = copy.deepcopy(selected_objects[relative_object])
        compile_args = arguments(record)
        compile_args.insert(compile_args.index("-c"), "-DRUSTBOX_MULTICALL=1")
        record.pop("command", None)
        record["arguments"] = compile_args
        record["file"] = str(rooted_path(record, "file"))
        record["output"] = str(output_path(record))
        output_records.append(record)
        key = source_key(Path(record["file"]))
        source_paths[key] = Path(record["file"])
        compile_action_hashes[relative_object] = action_sha256(record)

    output_directory.mkdir(parents=True, exist_ok=True)
    database_path = output_directory / "compile_commands.json"
    database_path.write_text(json.dumps(output_records, indent=2) + "\n")
    manifest = {
        "schema": 1,
        "release": "1.47.4",
        "program": program,
        "main_source": main_source,
        "sources": sorted(selected_sources),
        "source_sha256": {
            source: hashlib.sha256(source_paths[source].read_bytes()).hexdigest()
            for source in sorted(selected_sources)
        },
        "source_count": len(selected_sources),
        "objects": sorted(selected_objects),
        "object_count": len(selected_objects),
        "archive_objects": sorted(set(archive_objects)),
        "direct_objects": sorted(set(direct_objects)),
        "generated_sources": sorted(
            source for source in selected_sources if source.startswith("@build/")
        ),
        "compile_commands": len(output_records),
        "compile_action_sha256": compile_action_hashes,
        "multicall_define": True,
        "compile_database_input_sha256": database_sha256,
        "compile_database_sha256": hashlib.sha256(database_path.read_bytes()).hexdigest(),
        "linker_map_sha256": hashlib.sha256(map_path.read_bytes()).hexdigest(),
    }
    (output_directory / "closure.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--maps-directory", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--program", action="append", choices=[name for name, _ in ENTRYPOINTS])
    args = parser.parse_args()

    database_bytes = args.database.read_bytes()
    records = json.loads(database_bytes)
    by_object, _ = index_database(records)
    inventory = dict(ENTRYPOINTS)
    programs = args.program or sorted(inventory)
    manifests = {}
    for program in programs:
        manifests[program] = prepare_engine(
            program,
            inventory[program],
            args.maps_directory / f"{program}.map",
            args.output_directory / program,
            by_object,
            hashlib.sha256(database_bytes).hexdigest(),
        )

    source_union = sorted({
        source for manifest in manifests.values() for source in manifest["sources"]
    })
    object_union = sorted({
        obj for manifest in manifests.values() for obj in manifest["objects"]
    })
    summary = {
        "schema": 1,
        "release": "1.47.4",
        "engines": len(programs),
        "source_counts": {
            program: manifests[program]["source_count"] for program in programs
        },
        "object_counts": {
            program: manifests[program]["object_count"] for program in programs
        },
        "sum_of_engine_source_counts": sum(
            manifests[program]["source_count"] for program in programs
        ),
        "unique_sources": len(source_union),
        "unique_objects": len(object_union),
        "sources": source_union,
        "objects": object_union,
    }
    args.output_directory.mkdir(parents=True, exist_ok=True)
    (args.output_directory / "closure-counts.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary | {"sources": len(source_union), "objects": len(object_union)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
