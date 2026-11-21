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

ISOLATION_CACHE_VERSION = 1


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


def namespace_file_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep File's libmagic and internal C surface private to its applet."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] != "rustbox_file_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("File archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-file"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_file_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_file_main") != 1:
        raise RuntimeError("File symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("File symbol isolation left an unprefixed definition")
    if any(f"rustbox_file_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("File symbol isolation lost a definition")
    return mapped, symbols


def namespace_patch_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU patch's configured gnulib/internal C surface private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
            or fields[-1] in {"__xargmatch_internal", "_gl_alloc_nomem"}
        )
        and fields[-1] != "rustbox_patch_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU patch archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-patch"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_patch_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_patch_main") != 1:
        raise RuntimeError("GNU patch symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU patch symbol isolation left an unprefixed definition")
    if any(f"rustbox_patch_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU patch symbol isolation lost a definition")
    return mapped, symbols


def namespace_sed_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU sed's configured gnulib/internal C surface private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
            or fields[-1].startswith("_gl_")
        )
        and fields[-1] != "rustbox_sed_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU sed archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-sed"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_sed_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_sed_main") != 1:
        raise RuntimeError("GNU sed symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU sed symbol isolation left an unprefixed definition")
    if any(f"rustbox_sed_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU sed symbol isolation lost a definition")
    return mapped, symbols


def namespace_diffutils_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU Diffutils' configured gnulib/internal C surface private."""
    public = {
        "rustbox_cmp_main", "rustbox_diff_main",
        "rustbox_diff3_main", "rustbox_sdiff_main",
    }
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
            or fields[-1].startswith("_gl_")
            or fields[-1] in {"__gl_setmode", "__xargmatch_internal"}
        )
        and fields[-1] not in public
        and fields[-1] not in {"program_name", "set_program_name"}
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU Diffutils archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-diffutils"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_diffutils_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    subprocess.run(
        ["objcopy", "--weaken-symbol", "program_name", "--weaken-symbol", "set_program_name", str(mapped)],
        check=True,
    )
    subprocess.run(
        ["objcopy", "--redefine-sym", "error=rustbox_diffutils_error", str(mapped)],
        check=True,
    )
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"GNU Diffutils symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU Diffutils symbol isolation left an unprefixed definition")
    if any(f"rustbox_diffutils_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU Diffutils symbol isolation lost a definition")
    undefined = subprocess.run(
        ["nm", "-u", str(mapped)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.split()
    if "error" in undefined or "rustbox_diffutils_error" not in undefined:
        raise RuntimeError("GNU Diffutils error ABI redirection is incomplete")
    return mapped, symbols


def namespace_grep_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU Grep's configured gnulib/internal C surface private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
            or fields[-1].startswith("_gl_")
            or fields[-1] in {"__gl_setmode", "__xargmatch_internal"}
        )
        and fields[-1] != "rustbox_grep_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU Grep archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-grep"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_grep_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    subprocess.run(
        ["objcopy", "--redefine-sym", "error=rustbox_grep_error", str(mapped)],
        check=True,
    )
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_grep_main") != 1:
        raise RuntimeError("GNU Grep symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU Grep symbol isolation left an unprefixed definition")
    if any(f"rustbox_grep_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU Grep symbol isolation lost a definition")
    undefined = subprocess.run(
        ["nm", "-u", str(mapped)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout.split()
    if "error" in undefined or "rustbox_grep_error" not in undefined:
        raise RuntimeError("GNU Grep error ABI redirection is incomplete")
    return mapped, symbols


def namespace_bc_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU bc and dc's parser, scanner, and arithmetic C surface private."""
    public = {"rustbox_bc_main", "rustbox_dc_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU bc archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-bc"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_bc_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"GNU bc symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU bc symbol isolation left an unprefixed definition")
    if any(f"rustbox_bc_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU bc symbol isolation lost a definition")
    return mapped, symbols


def namespace_attr_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep attr, getfattr, setfattr, libattr, and walk support private."""
    public = {"rustbox_attr_main", "rustbox_getfattr_main", "rustbox_setfattr_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("attr archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-attr"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_attr_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"attr symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("attr symbol isolation left an unprefixed definition")
    if any(f"rustbox_attr_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("attr symbol isolation lost a definition")
    return mapped, symbols


def namespace_acl_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep chacl, getfacl, setfacl, libacl, and helper support private."""
    public = {"rustbox_chacl_main", "rustbox_getfacl_main", "rustbox_setfacl_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("acl archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-acl"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_acl_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"acl symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("acl symbol isolation left an unprefixed definition")
    if any(f"rustbox_acl_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("acl symbol isolation lost a definition")
    return mapped, symbols


def namespace_lz4_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep LZ4's CLI, embedded liblz4, and XXH C surface private."""
    public = {"rustbox_lz4_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("LZ4 archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-lz4"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_lz4_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_lz4_main") != 1:
        raise RuntimeError("LZ4 symbol isolation damaged rustbox_lz4_main")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("LZ4 symbol isolation left an unprefixed definition")
    if any(f"rustbox_lz4_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("LZ4 symbol isolation lost a definition")
    return mapped, symbols


def namespace_less_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Less's terminal, regex, and pager implementation private."""
    public = {"rustbox_less_main", "rustbox_lessecho_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(rust_library)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    symbols = sorted({
        fields[-1]
        for line in output.splitlines()
        if len(fields := line.split()) >= 3
        and fields[-2] in strong_types
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("Less archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-less"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_less_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"Less symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Less symbol isolation left an unprefixed definition")
    if any(f"rustbox_less_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Less symbol isolation lost a definition")
    return mapped, symbols


def namespace_gzip_libraries(
    rust_library: Path, support_library: Path, build: Path
) -> tuple[Path, Path, list[str]]:
    """Keep Gzip's engine and three variadic support members private."""
    public = {"rustbox_gzip_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    symbols: set[str] = set()
    for library in (rust_library, support_library):
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(library)], check=True, text=True,
            stdout=subprocess.PIPE,
        ).stdout
        symbols.update({
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
            and fields[-1] not in public
            and (
                not fields[-1].startswith("rust_")
                or fields[-1] == "rust_eh_personality"
            )
            and not compiler_math.fullmatch(fields[-1])
        })
    selected = sorted(symbols)
    if not selected:
        raise RuntimeError("GNU Gzip archives export no namespaceable C symbols")
    destination = build / "src/.rustbox-gzip"
    destination.mkdir(parents=True, exist_ok=True)
    mapped_rust = destination / rust_library.name
    mapped_support = destination / support_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_gzip_private_{symbol}\n" for symbol in selected),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped_rust)
    shutil.copy2(support_library, mapped_support)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped_rust)], check=True)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped_support)], check=True)
    if defined_symbols(mapped_rust).count("rustbox_gzip_main") != 1:
        raise RuntimeError("GNU Gzip symbol isolation damaged rustbox_gzip_main")
    definitions = set(defined_symbols(mapped_rust)) | set(defined_symbols(mapped_support))
    if any(symbol in definitions for symbol in selected):
        raise RuntimeError("GNU Gzip symbol isolation left an unprefixed definition")
    return mapped_rust, mapped_support, selected


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


def cached_util_linux_link_inputs(
    repository: Path, build: Path, report: dict[str, list[str]]
) -> tuple[list[Path], list[str]]:
    """Reuse verified util-linux support objects when all source hashes match."""
    text = (repository / "scripts/build_util_linux_batch_hybrid.sh").read_text(
        encoding="utf-8"
    )
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
    objects = [path for path in paths if path.suffix == ".o"]
    archives = [path for path in paths if path.suffix == ".a"]
    reused: list[Path] = []
    for index, path in enumerate(objects):
        relative = str(path.relative_to(build))
        reused.append(
            build / f"rustbox-support-all/{index:03d}-{path.name}"
            if relative in report
            else path
        )
    for path in archives:
        relative = str(path.relative_to(build))
        reused.append(
            build / "rustbox-support-all/libsmartcols-parser-namespaced.a"
            if relative in report
            else path
        )
    missing = [str(path) for path in reused if not path.is_file()]
    if missing:
        raise RuntimeError(f"cached util-linux support inputs are missing: {missing}")
    return reused, link_libraries


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
extern int rustbox_file_main(int, char **);
extern int rustbox_patch_main(int, char **);
extern int rustbox_sed_main(int, char **);
extern int rustbox_cmp_main(int, char **);
extern int rustbox_diff_main(int, char **);
extern int rustbox_diff3_main(int, char **);
extern int rustbox_sdiff_main(int, char **);
extern int rustbox_grep_main(int, char **);
extern int rustbox_bc_main(int, char **);
extern int rustbox_dc_main(int, char **);
extern int rustbox_attr_main(int, char **);
extern int rustbox_getfattr_main(int, char **);
extern int rustbox_setfattr_main(int, char **);
extern int rustbox_chacl_main(int, char **);
extern int rustbox_getfacl_main(int, char **);
extern int rustbox_setfacl_main(int, char **);
extern int rustbox_lz4_main(int, char **);
extern int rustbox_less_main(int, char **);
extern int rustbox_lessecho_main(int, char **);
extern int rustbox_gzip_main(int, char **);
extern int rustbox_gunzip_main(int, char **);
extern int rustbox_zcat_main(int, char **);
extern int rustbox_zcmp_main(int, char **);
extern int rustbox_zdiff_main(int, char **);
extern int rustbox_zforce_main(int, char **);
extern int rustbox_zgrep_main(int, char **);
extern int rustbox_zegrep_main(int, char **);
extern int rustbox_zfgrep_main(int, char **);
extern int rustbox_zless_main(int, char **);
extern int rustbox_zmore_main(int, char **);
extern int rustbox_znew_main(int, char **);
extern int rustbox_gzexe_main(int, char **);
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

static char *base_name(char *path)
{
    char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

int main(int argc, char **argv)
{
    char *name = base_name(argv[0]);
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
        name = base_name(argv[0]);
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
        name = base_name(argv[0]);
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
    if (!force_util_linux && strcmp(name, "file") == 0)
        return rustbox_file_main(argc, argv);
    if (!force_util_linux && strcmp(name, "patch") == 0)
        return rustbox_patch_main(argc, argv);
    if (!force_util_linux && strcmp(name, "sed") == 0)
        return rustbox_sed_main(argc, argv);
    if (!force_util_linux && strcmp(name, "cmp") == 0) {
        return rustbox_cmp_main(argc, argv);
    }
    if (!force_util_linux && strcmp(name, "diff") == 0) {
        return rustbox_diff_main(argc, argv);
    }
    if (!force_util_linux && strcmp(name, "diff3") == 0) {
        return rustbox_diff3_main(argc, argv);
    }
    if (!force_util_linux && strcmp(name, "sdiff") == 0) {
        return rustbox_sdiff_main(argc, argv);
    }
    if (!force_util_linux && strcmp(name, "grep") == 0) {
        return rustbox_grep_main(argc, argv);
    }
    if (!force_util_linux && (strcmp(name, "egrep") == 0 || strcmp(name, "fgrep") == 0)) {
        const char *option = name[0] == 'e' ? "-E" : "-F";
        char *alias_argv[argc + 2];
        int index;
        fprintf(stderr, "%s: warning: %s is obsolescent; using grep %s\\n",
                name, name, option);
        alias_argv[0] = "grep";
        alias_argv[1] = (char *) option;
        for (index = 1; index <= argc; index++)
            alias_argv[index + 1] = argv[index];
        program_invocation_name = alias_argv[0];
        program_invocation_short_name = alias_argv[0];
        return rustbox_grep_main(argc + 1, alias_argv);
    }
    if (!force_util_linux && strcmp(name, "bc") == 0)
        return rustbox_bc_main(argc, argv);
    if (!force_util_linux && strcmp(name, "dc") == 0)
        return rustbox_dc_main(argc, argv);
    if (!force_util_linux && strcmp(name, "attr") == 0)
        return rustbox_attr_main(argc, argv);
    if (!force_util_linux && strcmp(name, "getfattr") == 0)
        return rustbox_getfattr_main(argc, argv);
    if (!force_util_linux && strcmp(name, "setfattr") == 0)
        return rustbox_setfattr_main(argc, argv);
    if (!force_util_linux && strcmp(name, "chacl") == 0)
        return rustbox_chacl_main(argc, argv);
    if (!force_util_linux && strcmp(name, "getfacl") == 0)
        return rustbox_getfacl_main(argc, argv);
    if (!force_util_linux && strcmp(name, "setfacl") == 0)
        return rustbox_setfacl_main(argc, argv);
    if (!force_util_linux && (strcmp(name, "lz4") == 0 || strcmp(name, "lz4c") == 0 ||
                              strcmp(name, "lz4cat") == 0 || strcmp(name, "unlz4") == 0))
        return rustbox_lz4_main(argc, argv);
    if (!force_util_linux && strcmp(name, "less") == 0)
        return rustbox_less_main(argc, argv);
    if (!force_util_linux && strcmp(name, "lessecho") == 0)
        return rustbox_lessecho_main(argc, argv);
    if (!force_util_linux && strcmp(name, "gzip") == 0)
        return rustbox_gzip_main(argc, argv);
    if (!force_util_linux && (strcmp(name, "gunzip") == 0 || strcmp(name, "uncompress") == 0))
        return rustbox_gunzip_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zcat") == 0)
        return rustbox_zcat_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zcmp") == 0)
        return rustbox_zcmp_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zdiff") == 0)
        return rustbox_zdiff_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zforce") == 0)
        return rustbox_zforce_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zgrep") == 0)
        return rustbox_zgrep_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zegrep") == 0)
        return rustbox_zegrep_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zfgrep") == 0)
        return rustbox_zfgrep_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zless") == 0)
        return rustbox_zless_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zmore") == 0)
        return rustbox_zmore_main(argc, argv);
    if (!force_util_linux && strcmp(name, "znew") == 0)
        return rustbox_znew_main(argc, argv);
    if (!force_util_linux && strcmp(name, "gzexe") == 0)
        return rustbox_gzexe_main(argc, argv);
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
    parser.add_argument("--file-rust-library", type=Path, required=True)
    parser.add_argument("--patch-rust-library", type=Path, required=True)
    parser.add_argument("--sed-rust-library", type=Path, required=True)
    parser.add_argument("--diffutils-rust-library", type=Path, required=True)
    parser.add_argument("--grep-rust-library", type=Path, required=True)
    parser.add_argument("--bc-rust-library", type=Path, required=True)
    parser.add_argument("--attr-rust-library", type=Path, required=True)
    parser.add_argument("--acl-rust-library", type=Path, required=True)
    parser.add_argument("--lz4-rust-library", type=Path, required=True)
    parser.add_argument("--less-rust-library", type=Path, required=True)
    parser.add_argument("--gzip-rust-library", type=Path, required=True)
    parser.add_argument("--gzip-support-library", type=Path, required=True)
    parser.add_argument("--link-report", type=Path, required=True)
    parser.add_argument("--reuse-isolation", action="store_true")
    args = parser.parse_args()
    repository = args.repository.resolve()
    build = args.coreutils_build.resolve()
    util_build = args.util_linux_build.resolve()
    m4_rust_library = args.m4_rust_library.resolve()
    m4_support_library = args.m4_support_library.resolve()
    pkgconf_rust_library = args.pkgconf_rust_library.resolve()
    file_rust_library = args.file_rust_library.resolve()
    patch_rust_library = args.patch_rust_library.resolve()
    sed_rust_library = args.sed_rust_library.resolve()
    diffutils_rust_library = args.diffutils_rust_library.resolve()
    grep_rust_library = args.grep_rust_library.resolve()
    bc_rust_library = args.bc_rust_library.resolve()
    attr_rust_library = args.attr_rust_library.resolve()
    acl_rust_library = args.acl_rust_library.resolve()
    lz4_rust_library = args.lz4_rust_library.resolve()
    less_rust_library = args.less_rust_library.resolve()
    gzip_rust_library = args.gzip_rust_library.resolve()
    gzip_support_library = args.gzip_support_library.resolve()
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
    for path in (
        m4_rust_library, m4_support_library, pkgconf_rust_library,
        file_rust_library, patch_rust_library, sed_rust_library,
        diffutils_rust_library, grep_rust_library, bc_rust_library,
        attr_rust_library, acl_rust_library, lz4_rust_library, less_rust_library,
        gzip_rust_library,
        gzip_support_library,
    ):
        if not path.is_file():
            raise RuntimeError(f"multicall input is missing: {path}")
    libraries.append(m4_rust_library)
    m4_library_index = len(libraries) - 1
    libraries.append(pkgconf_rust_library)
    libraries.append(file_rust_library)
    file_library_index = len(libraries) - 1
    libraries.append(patch_rust_library)
    patch_library_index = len(libraries) - 1
    libraries.append(sed_rust_library)
    sed_library_index = len(libraries) - 1
    libraries.append(diffutils_rust_library)
    diffutils_library_index = len(libraries) - 1
    libraries.append(grep_rust_library)
    grep_library_index = len(libraries) - 1
    libraries.append(bc_rust_library)
    bc_library_index = len(libraries) - 1
    libraries.append(attr_rust_library)
    attr_library_index = len(libraries) - 1
    libraries.append(acl_rust_library)
    acl_library_index = len(libraries) - 1
    libraries.append(lz4_rust_library)
    lz4_library_index = len(libraries) - 1
    libraries.append(less_rust_library)
    less_library_index = len(libraries) - 1
    libraries.append(gzip_rust_library)
    gzip_library_index = len(libraries) - 1
    source_library_hashes = {str(path.relative_to(repository)): sha256(path) for path in libraries}
    source_library_hashes[str(m4_support_library)] = sha256(m4_support_library)
    source_library_hashes[str(gzip_support_library)] = sha256(gzip_support_library)
    expected_symbols.update(f"rustbox_{symbol}_main" for symbol in util_dispatch.values())
    expected_symbols.add("rustbox_m4_main")
    expected_symbols.update({
        "rustbox_pkgconf_main",
        "rustbox_bomtool_main",
        "rustbox_pccritic_main",
        "rustbox_spdxtool_main",
        "rustbox_file_main",
        "rustbox_patch_main",
        "rustbox_sed_main",
        "rustbox_cmp_main",
        "rustbox_diff_main",
        "rustbox_diff3_main",
        "rustbox_sdiff_main",
        "rustbox_grep_main",
        "rustbox_bc_main",
        "rustbox_dc_main",
        "rustbox_attr_main",
        "rustbox_getfattr_main",
        "rustbox_setfattr_main",
        "rustbox_chacl_main",
        "rustbox_getfacl_main",
        "rustbox_setfacl_main",
        "rustbox_lz4_main",
        "rustbox_less_main",
        "rustbox_lessecho_main",
        "rustbox_gzip_main",
        "rustbox_gunzip_main",
        "rustbox_zcat_main",
        "rustbox_zcmp_main",
        "rustbox_zdiff_main",
        "rustbox_zforce_main",
        "rustbox_zgrep_main",
        "rustbox_zegrep_main",
        "rustbox_zfgrep_main",
        "rustbox_zless_main",
        "rustbox_zmore_main",
        "rustbox_znew_main",
        "rustbox_gzexe_main",
    })

    cached_report = None
    if args.reuse_isolation and args.link_report.is_file():
        candidate = json.loads(args.link_report.read_text(encoding="utf-8"))
        if (
            candidate.get("source_library_sha256") == source_library_hashes
            and candidate.get("isolation_cache_version", 1) == ISOLATION_CACHE_VERSION
        ):
            cached_report = candidate

    if cached_report:
        mapped_file_rust = build / "src/.rustbox-file" / libraries[file_library_index].name
        file_symbols = cached_report["file_namespaced_symbols"]
    else:
        mapped_file_rust, file_symbols = namespace_file_library(
            libraries[file_library_index], build
        )
    libraries[file_library_index] = mapped_file_rust

    if cached_report:
        mapped_patch_rust = build / "src/.rustbox-patch" / libraries[patch_library_index].name
        patch_symbols = cached_report["patch_namespaced_symbols"]
    else:
        mapped_patch_rust, patch_symbols = namespace_patch_library(
            libraries[patch_library_index], build
        )
    libraries[patch_library_index] = mapped_patch_rust

    if cached_report:
        mapped_sed_rust = build / "src/.rustbox-sed" / libraries[sed_library_index].name
        sed_symbols = cached_report["sed_namespaced_symbols"]
    else:
        mapped_sed_rust, sed_symbols = namespace_sed_library(
            libraries[sed_library_index], build
        )
    libraries[sed_library_index] = mapped_sed_rust

    if cached_report:
        mapped_diffutils_rust = build / "src/.rustbox-diffutils" / libraries[diffutils_library_index].name
        diffutils_symbols = cached_report["diffutils_namespaced_symbols"]
    else:
        mapped_diffutils_rust, diffutils_symbols = namespace_diffutils_library(
            libraries[diffutils_library_index], build
        )
    libraries[diffutils_library_index] = mapped_diffutils_rust

    if cached_report:
        mapped_grep_rust = build / "src/.rustbox-grep" / libraries[grep_library_index].name
        grep_symbols = cached_report["grep_namespaced_symbols"]
    else:
        mapped_grep_rust, grep_symbols = namespace_grep_library(
            libraries[grep_library_index], build
        )
    libraries[grep_library_index] = mapped_grep_rust

    if cached_report:
        mapped_bc_rust = build / "src/.rustbox-bc" / libraries[bc_library_index].name
        bc_symbols = cached_report["bc_namespaced_symbols"]
    else:
        mapped_bc_rust, bc_symbols = namespace_bc_library(
            libraries[bc_library_index], build
        )
    libraries[bc_library_index] = mapped_bc_rust

    if cached_report:
        mapped_attr_rust = build / "src/.rustbox-attr" / libraries[attr_library_index].name
        attr_symbols = cached_report["attr_namespaced_symbols"]
    else:
        mapped_attr_rust, attr_symbols = namespace_attr_library(
            libraries[attr_library_index], build
        )
    libraries[attr_library_index] = mapped_attr_rust

    if cached_report:
        mapped_acl_rust = build / "src/.rustbox-acl" / libraries[acl_library_index].name
        acl_symbols = cached_report["acl_namespaced_symbols"]
    else:
        mapped_acl_rust, acl_symbols = namespace_acl_library(
            libraries[acl_library_index], build
        )
    libraries[acl_library_index] = mapped_acl_rust

    if cached_report:
        mapped_lz4_rust = build / "src/.rustbox-lz4" / libraries[lz4_library_index].name
        lz4_symbols = cached_report["lz4_namespaced_symbols"]
    else:
        mapped_lz4_rust, lz4_symbols = namespace_lz4_library(
            libraries[lz4_library_index], build
        )
    libraries[lz4_library_index] = mapped_lz4_rust

    if cached_report:
        mapped_less_rust = build / "src/.rustbox-less" / libraries[less_library_index].name
        less_symbols = cached_report["less_namespaced_symbols"]
    else:
        mapped_less_rust, less_symbols = namespace_less_library(
            libraries[less_library_index], build
        )
    libraries[less_library_index] = mapped_less_rust

    if cached_report:
        mapped_gzip_rust = build / "src/.rustbox-gzip" / libraries[gzip_library_index].name
        mapped_gzip_support = build / "src/.rustbox-gzip" / gzip_support_library.name
        gzip_symbols = cached_report["gzip_namespaced_symbols"]
    else:
        mapped_gzip_rust, mapped_gzip_support, gzip_symbols = namespace_gzip_libraries(
            libraries[gzip_library_index], gzip_support_library, build
        )
    libraries[gzip_library_index] = mapped_gzip_rust

    canonical_dispatch_symbols = set(defined_symbols(build / "src/coreutils-coreutils.o"))
    if cached_report:
        namespaced_symbols = cached_report["namespaced_symbols"]
        libraries = [
            build / "src" / f".rustbox-namespaced-{index:02d}-{library.name}"
            if library.name in namespaced_symbols
            else library
            for index, library in enumerate(libraries)
        ]
    else:
        libraries, namespaced_symbols = namespace_duplicate_c_symbols(
            libraries, expected_symbols, canonical_dispatch_symbols, build
        )
    if cached_report:
        mapped_m4_rust = build / "src/.rustbox-m4-support" / libraries[m4_library_index].name
        mapped_m4_support = build / "src/.rustbox-m4-support" / m4_support_library.name
        m4_support_symbols = cached_report["m4_namespaced_support_symbols"]
    else:
        mapped_m4_rust, mapped_m4_support, m4_support_symbols = namespace_m4_support(
            libraries[m4_library_index], m4_support_library, build
        )
    libraries[m4_library_index] = mapped_m4_rust
    if cached_report:
        namespaced_support = cached_report["namespaced_support_symbols"]
        util_inputs, util_link_libraries = cached_util_linux_link_inputs(
            repository, util_build, namespaced_support
        )
    else:
        rust_defined = canonical_dispatch_symbols | set().union(
            *(set(defined_symbols(path)) for path in libraries)
        )
        util_inputs, util_link_libraries, namespaced_support = util_linux_link_inputs(
            repository, util_build, rust_defined
        )

    cached_paths = [*libraries, mapped_m4_support, mapped_gzip_support, *util_inputs]
    missing_cached = [str(path) for path in cached_paths if not path.is_file()]
    if missing_cached:
        raise RuntimeError(f"isolated linker inputs are missing: {missing_cached}")

    typed_bridge_objects = compile_typed_bridges(repository, build, manifests)
    sed_abi_object = build / "src/.rustbox-sed-abi.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/sed_abi.c"),
         "-o", str(sed_abi_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(sed_abi_object) != ["__wctob_alias"]:
        raise RuntimeError("GNU sed ABI bridge exports the wrong symbols")
    diffutils_error_object = build / "src/.rustbox-diffutils-error.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/diffutils_error.c"),
         "-o", str(diffutils_error_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(diffutils_error_object) != ["rustbox_diffutils_error"]:
        raise RuntimeError("GNU Diffutils error ABI bridge exports the wrong symbols")
    grep_abi_object = build / "src/.rustbox-grep-abi.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-DRUSTBOX_BTOWC_ONLY=1", "-c",
         str(repository / "bridges/grep_abi.c"),
         "-o", str(grep_abi_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(grep_abi_object) != ["__btowc_alias"]:
        raise RuntimeError("GNU Grep ABI bridge exports the wrong symbols")
    grep_error_object = build / "src/.rustbox-grep-error.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/grep_error.c"),
         "-o", str(grep_error_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(grep_error_object) != ["rustbox_grep_error"]:
        raise RuntimeError("GNU Grep error ABI bridge exports the wrong symbols")
    gzip_aliases_object = build / "src/.rustbox-gzip-aliases.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/gzip_aliases.c"),
         "-o", str(gzip_aliases_object)],
        cwd=build,
        check=True,
    )
    if set(defined_symbols(gzip_aliases_object)) != {
        "rustbox_gunzip_main", "rustbox_zcat_main",
        "rustbox_zcmp_main", "rustbox_zdiff_main", "rustbox_zforce_main",
        "rustbox_zgrep_main", "rustbox_zegrep_main", "rustbox_zfgrep_main",
        "rustbox_zless_main",
        "rustbox_zmore_main",
        "rustbox_znew_main",
        "rustbox_gzexe_main",
    }:
        raise RuntimeError("GNU Gzip alias bridge exports the wrong symbols")
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
                rewritten.append(str(sed_abi_object))
                rewritten.append(str(diffutils_error_object))
                rewritten.append(str(grep_abi_object))
                rewritten.append(str(grep_error_object))
                rewritten.append(str(gzip_aliases_object))
                rewritten.extend(str(path) for path in util_inputs)
                rewritten.append(str(mapped_m4_support))
                rewritten.append(str(mapped_gzip_support))
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
        "src_libsinglebin_false_a_ldadd=$(src_true_LDADD) -ldl -lpthread -lm -lrt -lutil -ltinfo "
        "-lbz2 -llz -llzma -lseccomp -lz -lzstd -lattr -lpcre2-8",
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
        "isolation_cache_version": ISOLATION_CACHE_VERSION,
        "coreutils_applets": len(applets),
        "util_linux_applets": 155,
        "m4_applets": 1,
        "pkgconf_public_names": 5,
        "file_applets": 1,
        "patch_applets": 1,
        "sed_applets": 1,
        "diffutils_applets": 4,
        "grep_applets": 3,
        "bc_applets": 2,
        "attr_applets": 3,
        "acl_applets": 3,
        "lz4_public_names": 4,
        "less_public_names": 2,
        "gzip_public_names": 14,
        "total_dispatch_names": len(
            set(applets)
            | set(util_dispatch)
            | {"m4", "pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool", "file", "patch", "sed",
               "cmp", "diff", "diff3", "sdiff", "grep", "egrep", "fgrep", "bc", "dc",
               "attr", "getfattr", "setfattr", "chacl", "getfacl", "setfacl",
               "lz4", "lz4c", "lz4cat", "unlz4", "less", "lessecho",
               "gzip", "gunzip", "zcat", "uncompress",
               "zcmp", "zdiff", "zforce", "zgrep", "zegrep", "zfgrep", "zless",
               "zmore", "znew", "gzexe"}
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
        "file_namespaced_symbols": file_symbols,
        "patch_namespaced_symbols": patch_symbols,
        "sed_namespaced_symbols": sed_symbols,
        "diffutils_namespaced_symbols": diffutils_symbols,
        "grep_namespaced_symbols": grep_symbols,
        "bc_namespaced_symbols": bc_symbols,
        "attr_namespaced_symbols": attr_symbols,
        "acl_namespaced_symbols": acl_symbols,
        "lz4_namespaced_symbols": lz4_symbols,
        "less_namespaced_symbols": less_symbols,
        "gzip_namespaced_symbols": gzip_symbols,
        "diffutils_error_bridge": {
            "object": str(diffutils_error_object.relative_to(build)),
            "symbols": ["rustbox_diffutils_error"],
        },
        "grep_abi_bridge": {
            "object": str(grep_abi_object.relative_to(build)),
            "symbols": ["__btowc_alias"],
            "shared_existing_symbol": "__wctob_alias",
        },
        "grep_error_bridge": {
            "object": str(grep_error_object.relative_to(build)),
            "symbols": ["rustbox_grep_error"],
        },
        "gzip_alias_bridge": {
            "object": str(gzip_aliases_object.relative_to(build)),
            "symbols": ["rustbox_gunzip_main", "rustbox_zcat_main",
                        "rustbox_zcmp_main", "rustbox_zdiff_main", "rustbox_zforce_main",
                        "rustbox_zgrep_main", "rustbox_zegrep_main", "rustbox_zfgrep_main",
                        "rustbox_zless_main",
                        "rustbox_zmore_main", "rustbox_znew_main", "rustbox_gzexe_main"],
            "public_names": ["gunzip", "uncompress", "zcat", "zcmp", "zdiff", "zforce",
                             "zgrep", "zegrep", "zfgrep", "zless", "zmore", "znew", "gzexe"],
        },
        "sed_abi_bridge": {
            "object": str(sed_abi_object.relative_to(build)),
            "symbols": ["__wctob_alias"],
        },
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
        "file_applets": 1,
        "patch_applets": 1,
        "sed_applets": 1,
        "diffutils_applets": 4,
        "grep_applets": 3,
        "bc_applets": 2,
        "attr_applets": 3,
        "acl_applets": 3,
        "lz4_public_names": 4,
        "less_public_names": 2,
        "gzip_public_names": 14,
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
