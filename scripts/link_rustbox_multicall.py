#!/usr/bin/env python3
"""Link all verified utility translations into one Rustbox dispatcher."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    libraries: list[Path], public_symbols: set[str], reserved_symbols: set[str], build: Path
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
        if (len(owners) > 1 or symbol in reserved_symbols)
        and symbol not in public_symbols
        and not symbol.startswith("rust_")
        and not compiler_math.fullmatch(symbol)
    }
    rewritten: list[Path] = []
    report: dict[str, list[str]] = {}
    owners = {symbol: sorted(by_symbol[symbol]) for symbol in duplicates}
    for index, library in enumerate(libraries):
        selected = sorted(
            symbol
            for symbol in library_symbols[index] & duplicates
            if symbol in reserved_symbols or index != owners[symbol][0]
        )
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


def namespace_m4_support(
    rust_library: Path, support_library: Path, build: Path
) -> tuple[Path, Path, list[str]]:
    """Keep M4's configured gnulib closure private to its translated applet."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(support_library)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU M4 support archive exports no namespaceable symbols")
    destination = build / "src/.rustbox-m4-support"
    destination.mkdir(parents=True, exist_ok=True)
    mapped_rust = destination / rust_library.name
    mapped_support = destination / support_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_m4_support_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped_rust)
    shutil.copy2(support_library, mapped_support)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped_rust)], check=True)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped_support)], check=True)
    if defined_symbols(mapped_rust).count("rustbox_m4_main") != 1:
        raise RuntimeError("M4 support isolation damaged its public entrypoint")
    mapped_definitions = set(defined_symbols(mapped_support))
    if any(symbol in mapped_definitions for symbol in symbols):
        raise RuntimeError("M4 support isolation left an unprefixed definition")
    if any(f"rustbox_m4_support_{symbol}" not in mapped_definitions for symbol in symbols):
        raise RuntimeError("M4 support isolation lost a definition")
    return mapped_rust, mapped_support, symbols


def util_linux_link_inputs(
    repository: Path, build: Path, rust_defined: set[str]
) -> tuple[list[Path], list[str], dict[str, list[str]]]:
    text = (repository / "scripts/build_util_linux_batch_hybrid.sh").read_text(encoding="utf-8")
    declarations = re.findall(
        r"util-linux-small-[0-9]+\).*?extra_objects='([^']*)'.*?extra_libraries='([^']*)'",
        text,
        flags=re.DOTALL,
    )
    if len(declarations) != 14:
        raise RuntimeError(f"expected 14 util-linux linker declarations, found {len(declarations)}")
    tokens: list[str] = []
    link_libraries: list[str] = []
    for objects, libraries in declarations:
        for token in objects.split():
            if token not in tokens:
                tokens.append(token)
        for token in libraries.split():
            if token not in link_libraries:
                link_libraries.append(token)
    paths = [(build / token).resolve() for token in tokens]
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"util-linux support input is missing: {path}")

    objects = [path for path in paths if path.suffix == ".o"]
    archives = [path for path in paths if path.suffix == ".a"]
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    claimed = set(rust_defined)
    rewritten_objects: list[Path] = []
    report: dict[str, list[str]] = {}
    for index, path in enumerate(objects):
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(path)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        defined = {
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3 and fields[-2] in strong_types
        }
        duplicates = sorted(defined & claimed)
        if duplicates:
            copy = build / f"rustbox-support-all/{index:03d}-{path.name}"
            mapping = copy.with_suffix(copy.suffix + ".map")
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copy)
            mapping.write_text(
                "".join(
                    f"{symbol} rustbox_support_{index:03d}_{symbol}\n"
                    for symbol in duplicates
                ),
                encoding="utf-8",
            )
            subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(copy)], check=True)
            rewritten_objects.append(copy)
            report[str(path.relative_to(build))] = duplicates
        else:
            rewritten_objects.append(path)
        claimed.update(defined - set(duplicates))
    rewritten_archives: list[Path] = []
    for path in archives:
        if path.name == "libsmartcols.a":
            copy = build / "rustbox-support-all/libsmartcols-parser-namespaced.a"
            shutil.copy2(path, copy)
            subprocess.run(
                ["objcopy", "--redefine-sym", "yyparse=rustbox_smartcols_yyparse", str(copy)],
                check=True,
            )
            rewritten_archives.append(copy)
            report[str(path.relative_to(build))] = ["yyparse"]
        else:
            rewritten_archives.append(path)
    return rewritten_objects + rewritten_archives, link_libraries, report


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


def write_dispatcher(
    path: Path, applets: list[str], util_linux: dict[str, str]
) -> None:
    names = "\n".join(f'    "{name}",' for name in sorted(applets))
    util_symbols = sorted(set(util_linux.values()))
    declarations = "\n".join(
        f"extern int rustbox_{symbol}_main(int, char **);" for symbol in util_symbols
    )
    selection_lines = []
    for name, symbol in sorted(util_linux.items()):
        if name == "util-linux-kill":
            selection_lines.append(
                '    if (strcmp(name, "util-linux-kill") == 0) {'
                ' argv[0] = "kill"; program_invocation_name = argv[0];'
                ' program_invocation_short_name = argv[0];'
                f' return rustbox_{symbol}_main(argc, argv); }}'
            )
        else:
            selection_lines.append(
                f'    if (strcmp(name, "{name}") == 0) return rustbox_{symbol}_main(argc, argv);'
            )
    selections = "\n".join(selection_lines)
    path.write_text(
        """/* Generated by link_rustbox_multicall.py. */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_coreutils_dispatch(int, char **);
extern int rustbox_m4_main(int, char **);
extern int rustbox_pkgconf_main(int, char **);
extern int rustbox_bomtool_main(int, char **);
extern int rustbox_pccritic_main(int, char **);
extern int rustbox_spdxtool_main(int, char **);
"""
        + declarations
        + """

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
    int force_util_linux = 0;
    if (strcmp(name, "rustbox") == 0) {
        if (argc < 2) {
            fputs("usage: rustbox APPLET [ARGUMENT]...\\n", stderr);
            return 127;
        }
        if (strncmp(argv[1], "--coreutils-prog=", 17) == 0) {
            argv[0] = "coreutils";
            program_invocation_name = argv[0];
            program_invocation_short_name = argv[0];
            return rustbox_coreutils_dispatch(argc, argv);
        }
        argc--;
        argv++;
        name = basename(argv[0]);
        program_invocation_name = argv[0];
        program_invocation_short_name = name;
    }
    else if (strncmp(name, "rustbox-util-linux-small-", sizeof "rustbox-util-linux-small-" - 1) == 0) {
        if (argc < 2) {
            fputs("usage: rustbox-util-linux-small-NN APPLET [ARGUMENT]...\\n", stderr);
            return 127;
        }
        argc--;
        argv++;
        name = basename(argv[0]);
        program_invocation_name = argv[0];
        program_invocation_short_name = name;
        force_util_linux = 1;
    }
    if (!force_util_linux && is_coreutils(name))
        return rustbox_coreutils_dispatch(argc, argv);
    if (!force_util_linux && strcmp(name, "m4") == 0)
        return rustbox_m4_main(argc, argv);
    if (!force_util_linux && (strcmp(name, "pkgconf") == 0 || strcmp(name, "pkg-config") == 0))
        return rustbox_pkgconf_main(argc, argv);
    if (!force_util_linux && strcmp(name, "bomtool") == 0)
        return rustbox_bomtool_main(argc, argv);
    if (!force_util_linux && strcmp(name, "pccritic") == 0)
        return rustbox_pccritic_main(argc, argv);
    if (!force_util_linux && strcmp(name, "spdxtool") == 0)
        return rustbox_spdxtool_main(argc, argv);
"""
        + selections
        + """
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
    parser.add_argument("--util-linux-build", type=Path, required=True)
    parser.add_argument("--m4-rust-library", type=Path, required=True)
    parser.add_argument("--m4-support-library", type=Path, required=True)
    parser.add_argument("--pkgconf-rust-library", type=Path, required=True)
    parser.add_argument("--link-report", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    build = args.coreutils_build.resolve()
    util_build = args.util_linux_build.resolve()
    m4_rust_library = args.m4_rust_library.resolve()
    m4_support_library = args.m4_support_library.resolve()
    pkgconf_rust_library = args.pkgconf_rust_library.resolve()
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

    util_manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((repository / "batches").glob("util-linux-small-*.json"))
    ]
    util_dispatch: dict[str, str] = {}
    util_libraries: list[Path] = []
    for manifest in util_manifests:
        suffix = str(manifest["name"]).removeprefix("util-linux-small-")
        util_libraries.append(
            repository
            / "work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1"
            / f"util-linux-small-{suffix}-stable/target/release/libutil_linux_small_{suffix}_normalized_reachable.a"
        )
        entrypoints = manifest.get("entrypoints")
        if entrypoints:
            for record in entrypoints.values():
                for public_name in record["public_names"]:
                    util_dispatch[public_name] = record["symbol"]
        else:
            for applet in manifest["applets"]:
                util_dispatch[applet] = re.sub(r"[^a-z0-9_]", "_", applet)
    if len(util_dispatch) != 155:
        raise RuntimeError(f"expected 155 util-linux public names, found {len(util_dispatch)}")
    for library in util_libraries:
        if not library.is_file():
            raise RuntimeError(f"translated util-linux library is missing: {library}")
    duplicate_names = sorted(set(applets) & set(util_dispatch))
    if duplicate_names != ["kill"]:
        raise RuntimeError(f"unexpected cross-suite public-name collisions: {duplicate_names}")
    util_public_count = len(util_dispatch)
    util_dispatch["util-linux-kill"] = util_dispatch["kill"]
    libraries.extend(util_libraries)
    for path in (m4_rust_library, m4_support_library, pkgconf_rust_library):
        if not path.is_file():
            raise RuntimeError(f"multicall input is missing: {path}")
    libraries.append(m4_rust_library)
    m4_library_index = len(libraries) - 1
    libraries.append(pkgconf_rust_library)
    source_library_hashes = {str(path.relative_to(repository)): sha256(path) for path in libraries}
    source_library_hashes[str(m4_support_library)] = sha256(m4_support_library)
    expected_symbols.update(f"rustbox_{symbol}_main" for symbol in util_dispatch.values())
    expected_symbols.add("rustbox_m4_main")
    expected_symbols.update({
        "rustbox_pkgconf_main",
        "rustbox_bomtool_main",
        "rustbox_pccritic_main",
        "rustbox_spdxtool_main",
    })

    canonical_dispatch_symbols = set(defined_symbols(build / "src/coreutils-coreutils.o"))
    libraries, namespaced_symbols = namespace_duplicate_c_symbols(
        libraries, expected_symbols, canonical_dispatch_symbols, build
    )
    mapped_m4_rust, mapped_m4_support, m4_support_symbols = namespace_m4_support(
        libraries[m4_library_index], m4_support_library, build
    )
    libraries[m4_library_index] = mapped_m4_rust
    rust_defined = canonical_dispatch_symbols | set().union(
        *(set(defined_symbols(path)) for path in libraries)
    )
    util_inputs, util_link_libraries, namespaced_support = util_linux_link_inputs(
        repository, util_build, rust_defined
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

    canonical_coreutils = build / "lib/libcoreutils.a"
    namespaced_coreutils = build / "lib/.rustbox-libcoreutils.a"
    shutil.copy2(canonical_coreutils, namespaced_coreutils)
    subprocess.run(
        [
            "objcopy", "--redefine-sym",
            "crc32=rustbox_coreutils_gnulib_crc32",
            str(namespaced_coreutils),
        ],
        check=True,
    )
    namespaced_coreutils_symbols = defined_symbols(namespaced_coreutils)
    if "crc32" in namespaced_coreutils_symbols or "rustbox_coreutils_gnulib_crc32" not in namespaced_coreutils_symbols:
        raise RuntimeError("failed to isolate Coreutils' gnulib crc32 symbol")

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
                rewritten.extend(str(path) for path in util_inputs)
                rewritten.append(str(mapped_m4_support))
                inserted = True
            if dependency in bridge_archives:
                rewritten.append(str(bridge_archives[dependency]))
        elif dependency == "lib/libcoreutils.a":
            rewritten.append(str(namespaced_coreutils))
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
    write_dispatcher(dispatcher_source, applets, util_dispatch)
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
        "src_coreutils_LDADD=$(single_binary_deps) $(LDADD) $(single_binary_libs) "
        + " ".join(util_link_libraries),
        "src_coreutils_LINK=" + link,
    ]
    canonical = build / "src/coreutils"
    saved = build / "src/.rustbox-canonical-coreutils"
    saved_coreutils_archive = build / "lib/.rustbox-canonical-libcoreutils.a"
    shutil.copy2(canonical, saved)
    shutil.copy2(canonical_coreutils, saved_coreutils_archive)
    shutil.copy2(namespaced_coreutils, canonical_coreutils)
    for path in libraries:
        os.utime(path)
    try:
        subprocess.run(command, cwd=build, check=True)
    finally:
        os.replace(saved, canonical)
        os.replace(saved_coreutils_archive, canonical_coreutils)
    if not output.is_file() or not link_map.is_file():
        raise RuntimeError("combined Coreutils multicall was not produced")
    symbols = defined_symbols(output)
    for symbol in expected_symbols:
        if symbols.count(symbol) != 1:
            raise RuntimeError(f"combined output does not define {symbol} exactly once")
    if symbols.count("main") != 1 or symbols.count("rustbox_coreutils_dispatch") != 1:
        raise RuntimeError("combined dispatcher symbols are incomplete")
    report = {
        "schema": 1,
        "coreutils_applets": len(applets),
        "util_linux_applets": 155,
        "m4_applets": 1,
        "pkgconf_public_names": 5,
        "total_dispatch_names": len(
            set(applets)
            | set(util_dispatch)
            | {"m4", "pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool"}
        ),
        "excluded": ["chcon", "runcon"],
        "public_name_precedence": {"kill": "GNU Coreutils", "util-linux-kill": "util-linux"},
        "namespaced_canonical_symbols": {
            "lib/libcoreutils.a": {
                "crc32": "rustbox_coreutils_gnulib_crc32",
                "reason": "isolate zlib's incompatible crc32 ABI used by mkfs.cramfs",
            }
        },
        "source_library_sha256": source_library_hashes,
        "namespaced_symbols": namespaced_symbols,
        "namespaced_support_symbols": namespaced_support,
        "m4_namespaced_support_symbols": m4_support_symbols,
        "binary": {
            "bytes": output.stat().st_size,
            "sha256": sha256(output),
            "link_map_sha256": sha256(link_map),
        },
    }
    args.link_report.parent.mkdir(parents=True, exist_ok=True)
    args.link_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "applets": len(applets),
        "bytes": output.stat().st_size,
        "namespaced_libraries": len(namespaced_symbols),
        "namespaced_symbols": sum(len(items) for items in namespaced_symbols.values()),
        "namespaced_support_objects": len(namespaced_support),
        "util_linux_applets": util_public_count,
        "m4_applets": 1,
        "pkgconf_public_names": 5,
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
