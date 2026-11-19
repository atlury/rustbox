#!/usr/bin/env python3
"""Link every verified Coreutils translation into one Rustbox dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


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


def defined_symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return [line.split()[-1] for line in output.splitlines() if line.split()]


def namespace_duplicate_c_symbols(
    libraries: list[Path], public_symbols: set[str], build: Path
) -> tuple[list[Path], dict[str, list[str]]]:
    """Give repeated C2Rust extern symbols crate-local link names.

    Rust-mangled/runtime/compiler-builtins symbols retain their normal COMDAT
    handling.  Public applet entrypoints remain unchanged.
    """
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    by_symbol: dict[str, set[int]] = {}
    library_symbols: list[set[str]] = []
    for index, library in enumerate(libraries):
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(library)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
        symbols: set[str] = set()
        for line in output.splitlines():
            fields = line.split()
            if len(fields) < 3 or fields[-2] not in strong_types:
                continue
            symbol = fields[-1]
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", symbol):
                symbols.add(symbol)
                by_symbol.setdefault(symbol, set()).add(index)
        library_symbols.append(symbols)
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    duplicates = {
        symbol
        for symbol, owners in by_symbol.items()
        if len(owners) > 1
        and symbol not in public_symbols
        and not symbol.startswith("rust_")
        and not compiler_math.fullmatch(symbol)
    }
    rewritten: list[Path] = []
    report: dict[str, list[str]] = {}
    for index, library in enumerate(libraries):
        selected = sorted(library_symbols[index] & duplicates)
        if not selected:
            rewritten.append(library)
            continue
        prefix = f"rustbox_batch_{index:02d}_"
        output = build / "src" / f".rustbox-namespaced-{index:02d}-{library.name}"
        mapping = build / "src" / f".rustbox-namespaced-{index:02d}.map"
        shutil.copy2(library, output)
        mapping.write_text(
            "".join(f"{symbol} {prefix}{symbol}\n" for symbol in selected),
            encoding="utf-8",
        )
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(output)], check=True)
        rewritten.append(output)
        report[library.name] = selected
    return rewritten, report


def compile_typed_bridges(
    repository: Path, build: Path, manifests: list[dict[str, object]]
) -> list[Path]:
    database = json.loads((build / "compile_commands.json").read_text(encoding="utf-8"))
    outputs: list[Path] = []
    for manifest in manifests:
        batch = str(manifest["name"])
        for declaration in manifest.get("typed_c_bridges", []):
            source = repository / declaration["source"]
            reference = declaration["reference_output"]
            matches = [
                entry
                for entry in database
                if entry.get("output") == reference
                or str(entry.get("output", "")).endswith("/" + reference)
            ]
            if len(matches) != 1:
                raise RuntimeError(f"typed bridge reference is not unique: {reference}")
            entry = matches[0]
            arguments = list(entry["arguments"])
            canonical_source = str(entry["file"])
            if arguments.count(canonical_source) != 1 or arguments.count("-o") != 1:
                raise RuntimeError("typed bridge reference compile action is malformed")
            output = build / "src" / f".rustbox-{batch}-{declaration['object']}"
            arguments[arguments.index(canonical_source)] = str(source)
            arguments[arguments.index("-o") + 1] = str(output)
            subprocess.run(arguments, cwd=entry["directory"], check=True)
            if sorted(defined_symbols(output)) != sorted(declaration["symbols"]):
                raise RuntimeError(f"typed bridge exports the wrong symbols: {source}")
            outputs.append(output)
    return outputs


def write_dispatcher(path: Path, applets: list[str]) -> None:
    names = "\n".join(f'    "{name}",' for name in sorted(applets))
    path.write_text(
        """/* Generated by link_rustbox_multicall.py. */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_coreutils_dispatch(int, char **);

static const char *const coreutils_applets[] = {
"""
        + names
        + """
};

static int is_coreutils(const char *name)
{
    size_t index;
    for (index = 0; index < sizeof coreutils_applets / sizeof coreutils_applets[0]; index++)
        if (strcmp(name, coreutils_applets[index]) == 0)
            return 1;
    return 0;
}

int main(int argc, char **argv)
{
    char *name = basename(argv[0]);
    if (strcmp(name, "rustbox") == 0) {
        if (argc < 2) {
            fputs("usage: rustbox APPLET [ARGUMENT]...\\n", stderr);
            return 127;
        }
        argc--;
        argv++;
        name = basename(argv[0]);
        program_invocation_name = argv[0];
        program_invocation_short_name = name;
    }
    if (is_coreutils(name))
        return rustbox_coreutils_dispatch(argc, argv);
    errno = ENOENT;
    fprintf(stderr, "rustbox: unknown applet: %s\\n", name);
    return 127;
}
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--coreutils-build", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    build = args.coreutils_build.resolve()
    makefile = build / "Makefile"
    if not makefile.is_file():
        raise RuntimeError("canonical Coreutils build is missing")

    manifest_paths = sorted((repository / "batches").glob("coreutils-small-*.json"))
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in manifest_paths]
    applets: list[str] = ["true", "false"]
    removed = {"src/libsinglebin_true.a", "src/libsinglebin_false.a"}
    expected_symbols = {"single_binary_main_true", "single_binary_main_false"}
    libraries = [
        repository
        / "work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false-stable/target/release/libtrue_false_reachable.a"
    ]
    bridge_members: dict[str, list[str]] = {}
    for manifest in manifests:
        batch = manifest["name"]
        applet_linkage = manifest.get("applet_linkage", {})
        for applet in manifest["applets"]:
            if applet == "runcon":
                # GNU runcon is SELinux-specific and is excluded together with
                # chcon from the final no-security multicall surface.
                continue
            linkage = applet_linkage.get(applet, {})
            archive = linkage.get("archive", f"src/libsinglebin_{applet}.a")
            symbol = linkage.get("symbol", "single_binary_main_" + applet.replace("-", "_"))
            if archive in removed or symbol in expected_symbols:
                raise RuntimeError(f"duplicate Coreutils linkage: {applet}")
            applets.append(applet)
            removed.add(archive)
            expected_symbols.add(symbol)
        libraries.append(
            repository
            / "work/analysis/coreutils-9.12/translations/c2rust-0.22.1"
            / f"{batch}-stable/target/release/{manifest['reachable_staticlib']}"
        )
        for declaration in manifest.get("canonical_bridge_members", []):
            archive = declaration["archive"]
            if archive in bridge_members:
                raise RuntimeError(f"duplicate canonical bridge archive: {archive}")
            bridge_members[archive] = declaration["members"]
    if len(applets) != 106 or len(set(applets)) != 106:
        raise RuntimeError(f"expected 106 unique no-security Coreutils applets, found {len(set(applets))}")
    for library in libraries:
        if not library.is_file():
            raise RuntimeError(f"translated Coreutils library is missing: {library}")

    libraries, namespaced_symbols = namespace_duplicate_c_symbols(
        libraries, expected_symbols, build
    )

    typed_bridge_objects = compile_typed_bridges(repository, build, manifests)
    bridge_archives: dict[str, Path] = {}
    for archive, members in bridge_members.items():
        source = build / archive
        before = subprocess.run(
            ["ar", "t", str(source)], check=True, text=True, stdout=subprocess.PIPE
        ).stdout.splitlines()
        if any(before.count(member) != 1 for member in members):
            raise RuntimeError(f"canonical bridge member is missing from {archive}")
        output = build / "src" / f".rustbox-all-bridge-{Path(archive).name}"
        shutil.copy2(source, output)
        discard = [member for member in before if member not in members]
        if discard:
            subprocess.run(["ar", "d", str(output), *discard], check=True)
        bridge_archives[archive] = output

    dependencies = make_assignment(makefile, "single_binary_deps").split()
    for archive in removed:
        if dependencies.count(archive) != 1:
            raise RuntimeError(f"expected one canonical applet archive: {archive}")
    rewritten: list[str] = []
    inserted = False
    for dependency in dependencies:
        if dependency in removed:
            if not inserted:
                rewritten.extend(str(path) for path in libraries)
                rewritten.extend(str(path) for path in typed_bridge_objects)
                inserted = True
            if dependency in bridge_archives:
                rewritten.append(str(bridge_archives[dependency]))
        else:
            rewritten.append(dependency)

    canonical_dispatch = build / "src/coreutils-coreutils.o"
    renamed_dispatch = build / "src/.rustbox-coreutils-dispatch.o"
    shutil.copy2(canonical_dispatch, renamed_dispatch)
    subprocess.run(
        ["objcopy", "--redefine-sym", "main=rustbox_coreutils_dispatch", str(renamed_dispatch)],
        check=True,
    )
    if defined_symbols(renamed_dispatch).count("rustbox_coreutils_dispatch") != 1:
        raise RuntimeError("renamed canonical Coreutils dispatcher is incomplete")

    dispatcher_source = build / "src/.rustbox-dispatch.c"
    dispatcher_object = build / "src/.rustbox-dispatch.o"
    write_dispatcher(dispatcher_source, applets)
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(dispatcher_source), "-o", str(dispatcher_object)],
        cwd=build,
        check=True,
    )

    output = build / "src/rustbox"
    link_map = output.with_suffix(".map")
    link = (
        "$(CCLD) $(src_coreutils_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) "
        "$(LDFLAGS) -Wl,--gc-sections -Wl,-Map=src/rustbox.map -o src/rustbox"
    )
    command = [
        "make",
        "V=1",
        "src/coreutils",
        "single_binary_deps=" + " ".join(rewritten),
        "src_coreutils_OBJECTS=" + str(dispatcher_object) + " " + str(renamed_dispatch),
        "src_libsinglebin_false_a_ldadd=$(src_true_LDADD) -ldl -lpthread -lm -lrt -lutil",
        "src_coreutils_LDADD=$(single_binary_deps) $(LDADD) $(single_binary_libs)",
        "src_coreutils_LINK=" + link,
    ]
    canonical = build / "src/coreutils"
    saved = build / "src/.rustbox-canonical-coreutils"
    shutil.copy2(canonical, saved)
    for path in libraries:
        os.utime(path)
    try:
        subprocess.run(command, cwd=build, check=True)
    finally:
        os.replace(saved, canonical)
    if not output.is_file() or not link_map.is_file():
        raise RuntimeError("combined Coreutils multicall was not produced")
    symbols = defined_symbols(output)
    for symbol in expected_symbols:
        if symbols.count(symbol) != 1:
            raise RuntimeError(f"combined output does not define {symbol} exactly once")
    if symbols.count("main") != 1 or symbols.count("rustbox_coreutils_dispatch") != 1:
        raise RuntimeError("combined dispatcher symbols are incomplete")
    print(json.dumps({
        "applets": len(applets),
        "bytes": output.stat().st_size,
        "namespaced_libraries": len(namespaced_symbols),
        "namespaced_symbols": sum(len(items) for items in namespaced_symbols.values()),
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
