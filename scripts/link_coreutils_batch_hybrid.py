#!/usr/bin/env python3
"""Relink canonical Coreutils with one declared applet batch supplied by Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_APPLET = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_LINK_LIBRARY = re.compile(r"^-l[A-Za-z0-9_+.-]+$")
SAFE_ARCHIVE = re.compile(r"^src/libsinglebin_[A-Za-z0-9_-]+\.a$")
SAFE_MEMBER = re.compile(r"^[A-Za-z0-9_.+-]+\.o$")
SAFE_SYMBOL = re.compile(r"^[A-Za-z0-9_]+$")
SAFE_BRIDGE_SOURCE = re.compile(r"^bridges/coreutils/[A-Za-z0-9_.+-]+\.c$")
SAFE_OBJECT = re.compile(r"^[A-Za-z0-9_.+-]+\.o$")
SAFE_REFERENCE_OUTPUT = re.compile(r"^src/[A-Za-z0-9_.+-]+\.o$")


def make_assignment(path: Path, name: str) -> str:
    prefix = name + " = "
    matches = [
        line[len(prefix) :]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} assignment, found {len(matches)}")
    return matches[0]


def ar_members(path: Path) -> list[str]:
    return subprocess.run(
        ["ar", "t", str(path)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.splitlines()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--rust-library", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()

    build = args.build.resolve()
    rust_library = args.rust_library.resolve()
    repository = args.repository.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    batch = manifest.get("name")
    applets = manifest.get("applets")
    applet_linkage = manifest.get("applet_linkage", {})
    extra_link_libraries = manifest.get("extra_link_libraries", [])
    archive_exclusions = manifest.get("canonical_archive_member_exclusions", [])
    bridge_declarations = manifest.get("canonical_bridge_members", [])
    typed_bridge_declarations = manifest.get("typed_c_bridges", [])
    if not isinstance(batch, str) or not SAFE_NAME.fullmatch(batch):
        raise RuntimeError("batch manifest has an unsafe name")
    if (
        not isinstance(applets, list)
        or not applets
        or not all(
            isinstance(item, str) and (item == "[" or SAFE_APPLET.fullmatch(item))
            for item in applets
        )
        or len(set(applets)) != len(applets)
    ):
        raise RuntimeError("batch manifest has invalid or duplicate applets")
    if (
        not isinstance(applet_linkage, dict)
        or not set(applet_linkage).issubset(applets)
        or any(
            not isinstance(item, dict)
            or set(item) != {"archive", "symbol"}
            or not isinstance(item["archive"], str)
            or not SAFE_ARCHIVE.fullmatch(item["archive"])
            or not isinstance(item["symbol"], str)
            or not SAFE_SYMBOL.fullmatch(item["symbol"])
            for item in applet_linkage.values()
        )
    ):
        raise RuntimeError("batch manifest has invalid applet linkage aliases")
    if (
        not isinstance(extra_link_libraries, list)
        or not all(
            isinstance(item, str) and SAFE_LINK_LIBRARY.fullmatch(item)
            for item in extra_link_libraries
        )
        or len(set(extra_link_libraries)) != len(extra_link_libraries)
    ):
        raise RuntimeError("batch manifest has invalid or duplicate extra link libraries")
    if not isinstance(archive_exclusions, list):
        raise RuntimeError("batch manifest has invalid canonical archive exclusions")
    exclusion_map: dict[str, list[str]] = {}
    for item in archive_exclusions:
        if not isinstance(item, dict):
            raise RuntimeError("canonical archive exclusion must be an object")
        archive = item.get("archive")
        members = item.get("members")
        if (
            not isinstance(archive, str)
            or not SAFE_ARCHIVE.fullmatch(archive)
            or archive in exclusion_map
            or not isinstance(members, list)
            or not members
            or not all(isinstance(member, str) and SAFE_MEMBER.fullmatch(member) for member in members)
            or len(set(members)) != len(members)
        ):
            raise RuntimeError("batch manifest has unsafe or duplicate canonical archive exclusions")
        exclusion_map[archive] = members
    if not isinstance(bridge_declarations, list):
        raise RuntimeError("batch manifest has invalid canonical bridge members")
    bridge_map: dict[str, list[str]] = {}
    for item in bridge_declarations:
        if not isinstance(item, dict):
            raise RuntimeError("canonical bridge declaration must be an object")
        archive = item.get("archive")
        members = item.get("members")
        reason = item.get("reason")
        if (
            not isinstance(archive, str)
            or not SAFE_ARCHIVE.fullmatch(archive)
            or archive in bridge_map
            or not isinstance(members, list)
            or not members
            or not all(isinstance(member, str) and SAFE_MEMBER.fullmatch(member) for member in members)
            or len(set(members)) != len(members)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise RuntimeError("canonical bridge declaration is unsafe or duplicated")
        bridge_map[archive] = members
    if not isinstance(typed_bridge_declarations, list):
        raise RuntimeError("batch manifest has invalid typed C bridges")
    typed_bridges: list[dict[str, object]] = []
    for item in typed_bridge_declarations:
        if not isinstance(item, dict) or set(item) != {
            "source", "reference_output", "object", "symbols", "reason"
        }:
            raise RuntimeError("typed C bridge declaration has invalid keys")
        source = item["source"]
        reference_output = item["reference_output"]
        object_name = item["object"]
        symbols = item["symbols"]
        reason = item["reason"]
        if (
            not isinstance(source, str)
            or not SAFE_BRIDGE_SOURCE.fullmatch(source)
            or not isinstance(reference_output, str)
            or not SAFE_REFERENCE_OUTPUT.fullmatch(reference_output)
            or not isinstance(object_name, str)
            or not SAFE_OBJECT.fullmatch(object_name)
            or not isinstance(symbols, list)
            or not symbols
            or not all(isinstance(symbol, str) and SAFE_SYMBOL.fullmatch(symbol) for symbol in symbols)
            or len(set(symbols)) != len(symbols)
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise RuntimeError("typed C bridge declaration is unsafe")
        typed_bridges.append(item)

    makefile = build / "Makefile"
    if not makefile.is_file() or not rust_library.is_file():
        raise RuntimeError("canonical build or generated Rust static library is missing")

    typed_bridge_objects: list[tuple[dict[str, object], Path]] = []
    if typed_bridges:
        compile_database_path = build / "compile_commands.json"
        if not compile_database_path.is_file():
            raise RuntimeError("typed C bridge requires the canonical compile database")
        compile_database = json.loads(compile_database_path.read_text(encoding="utf-8"))
        for declaration in typed_bridges:
            source = repository / str(declaration["source"])
            if not source.is_file():
                raise RuntimeError(f"typed C bridge source is missing: {source}")
            matches = [
                entry for entry in compile_database
                if entry.get("output") == str(declaration["reference_output"])
                or str(entry.get("output", "")).endswith("/" + str(declaration["reference_output"]))
            ]
            if len(matches) != 1:
                raise RuntimeError("typed C bridge reference compile action is not unique")
            entry = matches[0]
            arguments = list(entry["arguments"])
            canonical_source = str(entry["file"])
            if arguments.count(canonical_source) != 1 or arguments.count("-o") != 1:
                raise RuntimeError("typed C bridge reference compile action is malformed")
            bridge_object = build / "src" / f".rustbox-{batch}-{declaration['object']}"
            arguments[arguments.index(canonical_source)] = str(source)
            arguments[arguments.index("-o") + 1] = str(bridge_object)
            subprocess.run(arguments, cwd=entry["directory"], check=True)
            defined_output = subprocess.run(
                ["nm", "-g", "--defined-only", str(bridge_object)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout
            defined_symbols = sorted(
                line.split()[-1] for line in defined_output.splitlines() if line.split()
            )
            if defined_symbols != sorted(declaration["symbols"]):
                raise RuntimeError(
                    f"typed C bridge exports the wrong symbols: {defined_symbols}"
                )
            typed_bridge_objects.append((declaration, bridge_object))

    dependencies = make_assignment(makefile, "single_binary_deps").split()
    removed = {
        applet_linkage.get(applet, {}).get(
            "archive", f"src/libsinglebin_{applet}.a"
        )
        for applet in applets
    }
    if len(removed) != len(applets):
        raise RuntimeError("batch applets do not map to distinct canonical archives")
    for archive in sorted(removed):
        count = dependencies.count(archive)
        if count != 1:
            raise RuntimeError(f"expected one {archive} dependency, found {count}")
    if not set(bridge_map).issubset(removed):
        raise RuntimeError("canonical bridge archive is not replaced by this batch")

    bridge_archives: dict[str, Path] = {}
    for archive, members in sorted(bridge_map.items()):
        source = build / archive
        if not source.is_file():
            raise RuntimeError(f"canonical bridge archive is missing: {archive}")
        before = ar_members(source)
        if any(before.count(member) != 1 for member in members):
            raise RuntimeError(f"canonical bridge archive lacks one declared member: {archive}")
        retained = [member for member in before if member in members]
        bridge = build / "src" / f".rustbox-{batch}-bridge-{Path(archive).name}"
        shutil.copy2(source, bridge)
        removed_members = [member for member in before if member not in members]
        if removed_members:
            subprocess.run(["ar", "d", str(bridge), *removed_members], check=True)
        if ar_members(bridge) != retained:
            raise RuntimeError(f"canonical bridge member set is wrong: {archive}")
        bridge_archives[archive] = bridge

    filtered_archives: dict[str, Path] = {}
    for archive, members in sorted(exclusion_map.items()):
        if archive in removed or dependencies.count(archive) != 1:
            raise RuntimeError(f"cannot filter undeclared or replaced archive: {archive}")
        source = build / archive
        if not source.is_file():
            raise RuntimeError(f"canonical archive is missing: {archive}")
        original_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        before = ar_members(source)
        if any(before.count(member) != 1 for member in members):
            raise RuntimeError(f"canonical archive lacks one declared member: {archive}")
        filtered = build / "src" / f".rustbox-{batch}-{Path(archive).name}"
        shutil.copy2(source, filtered)
        subprocess.run(["ar", "d", str(filtered), *members], check=True)
        after = ar_members(filtered)
        if after != [member for member in before if member not in members]:
            raise RuntimeError(f"filtered archive member set is wrong: {archive}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != original_sha256:
            raise RuntimeError(f"canonical archive changed while filtering: {archive}")
        filtered_archives[archive] = filtered

    rewritten: list[str] = []
    inserted = False
    for dependency in dependencies:
        if dependency in removed:
            if not inserted:
                rewritten.append(str(rust_library))
                rewritten.extend(str(path) for _, path in typed_bridge_objects)
                inserted = True
            if dependency in bridge_archives:
                rewritten.append(str(bridge_archives[dependency]))
        elif dependency in filtered_archives:
            rewritten.append(str(filtered_archives[dependency]))
        else:
            rewritten.append(dependency)

    output_name = f"coreutils-rust-{batch}"
    output = build / "src" / output_name
    link_map = output.with_suffix(".map")
    link = (
        "$(CCLD) $(src_coreutils_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) "
        f"$(LDFLAGS) -Wl,-Map=src/{output_name}.map -o src/{output_name}"
    )
    command = [
        "make",
        "V=1",
        "src/coreutils",
        "single_binary_deps=" + " ".join(rewritten),
        "src_coreutils_LDADD=$(single_binary_deps) $(LDADD) $(single_binary_libs) "
        + " ".join(extra_link_libraries),
        "src_coreutils_LINK=" + link,
    ]
    canonical = build / "src/coreutils"
    saved = build / "src/.coreutils-rustbox-canonical"
    if not canonical.is_file():
        subprocess.run(["make", "src/coreutils"], cwd=build, check=True)
    shutil.copy2(canonical, saved)
    os.utime(rust_library)
    try:
        subprocess.run(command, cwd=build, check=True)
    finally:
        os.replace(saved, canonical)

    if not output.is_file() or not link_map.is_file():
        raise RuntimeError("hybrid linker did not produce its isolated output")
    map_text = link_map.read_text(encoding="utf-8", errors="replace")
    if str(rust_library) not in map_text:
        raise RuntimeError("link map does not contain the generated Rust library")
    for archive in removed:
        # GNU's link variables can mention an archive again as support for a
        # different applet (notably uname for arch/hostname/uptime).  A LOAD
        # directive alone does not contribute code.  Reject any extracted
        # member, which GNU ld records as archive(member), and then verify the
        # final public entry point below.
        if archive + "(" in map_text:
            raise RuntimeError(f"link map contains a member from original {archive}")
    for archive, bridge in bridge_archives.items():
        for member in bridge_map[archive]:
            if f"{bridge}({member})" not in map_text:
                raise RuntimeError(f"link map omits declared canonical bridge member {member}")
    for declaration, bridge_object in typed_bridge_objects:
        if f"LOAD {bridge_object}" not in map_text:
            raise RuntimeError(f"link map omits typed C bridge object: {bridge_object}")
        for symbol in declaration["symbols"]:
            if map_text.count(symbol) < 1:
                raise RuntimeError(f"link map omits typed C bridge symbol: {symbol}")
    for archive, filtered in filtered_archives.items():
        if archive + "(" in map_text:
            raise RuntimeError(f"link map contains unfiltered canonical archive {archive}")
        for member in exclusion_map[archive]:
            if f"{filtered}({member})" in map_text:
                raise RuntimeError(f"link map contains excluded canonical member {member}")

    defined = subprocess.run(
        ["nm", "-g", "--defined-only", str(output)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = [line.split()[-1] for line in defined.splitlines() if line.split()]
    for applet in applets:
        symbol = applet_linkage.get(applet, {}).get(
            "symbol", "single_binary_main_" + applet.replace("-", "_")
        )
        if symbols.count(symbol) != 1:
            raise RuntimeError(f"hybrid output does not define {symbol} exactly once")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
