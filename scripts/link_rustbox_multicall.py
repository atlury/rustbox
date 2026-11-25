#!/usr/bin/env python3
"""Link all verified utility translations into one Rustbox dispatcher."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import curl_manual_archive
from tar_timespec_archive import selection as tar_timestamps
from bison_length_archive import selection as bison_lengths
import lz4_dictionary_archive
import prepare_identical_archives
import iproute2_address_protocol_archive as address_protocols
import iproute2_route_name_archives as route_names
import stage_routing_protocol_archives as routing_protocols
from build_iproute2_bridge import build_bridge
from build_e2fsprogs_checksums import build_shared, BITCOUNT_SYMBOL, CRC_SYMBOLS
from batch_cargo_private_inlines import release_archives
from prepare_second_inline_layers import linked_layers
from e2fsprogs_foreign_declarations import prepare_release as prepare_foreign_declarations
from e2fsprogs_dirhash_archives import candidate_path as array_archive, prepare as prepare_dirhash
from prune_private_inlines import prepare_archive

ISOLATION_CACHE_VERSION = 18
INETUTILS_PROGRAMS = (
    "dnsdomainname", "ftp", "ftpd", "hostname", "ifconfig", "inetd",
    "logger", "ping", "ping6", "rcp", "rexec", "rexecd", "rlogin",
    "rlogind", "rsh", "rshd", "syslogd", "talk", "talkd", "telnet",
    "telnetd", "tftp", "tftpd", "traceroute", "uucpd", "whois",
)
IPROUTE2_PROGRAMS = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
IPROUTE2_PUBLIC_NAMES = (*IPROUTE2_PROGRAMS, "ctstat", "rtstat", "routel")
E2FSPROGS_PROGRAMS = (
    "badblocks", "chattr", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck",
    "e2image", "e2initrd_helper", "e2undo", "e4crypt", "e4defrag", "filefrag",
    "fsck", "fuse2fs", "logsave", "lsattr", "mke2fs", "mklost_found",
    "resize2fs", "tune2fs",
)
E2FSPROGS_ALIASES = {
    "e2label": "tune2fs",
    "e2mmpstatus": "dumpe2fs",
    "fsck.ext2": "e2fsck",
    "fsck.ext3": "e2fsck",
    "fsck.ext4": "e2fsck",
    "mkfs.ext2": "mke2fs",
    "mkfs.ext3": "mke2fs",
    "mkfs.ext4": "mke2fs",
}
E2FSPROGS_FRONTENDS = ("compile_et", "e2scrub", "e2scrub_all", "mk_cmds")
E2FSPROGS_PUBLIC_NAMES = (
    *(
        "e2fsprogs-fsck" if name == "fsck"
        else "mklost+found" if name == "mklost_found"
        else name
        for name in E2FSPROGS_PROGRAMS
    ),
    *E2FSPROGS_ALIASES,
    *E2FSPROGS_FRONTENDS,
)
E2FSPROGS_RUNTIME_MEMBER_COUNTS = {
    "badblocks": 211,
    "chattr": 193,
    "debugfs": 211,
    "dumpe2fs": 195,
    "e2freefrag": 195,
    "e2fsck": 195,
    "e2image": 195,
    "e2initrd_helper": 195,
    "e2undo": 195,
    "e4crypt": 193,
    "e4defrag": 195,
    "filefrag": 193,
    "fsck": 193,
    "fuse2fs": 211,
    "logsave": 193,
    "lsattr": 193,
    "mke2fs": 211,
    "mklost_found": 193,
    "resize2fs": 195,
    "tune2fs": 211,
}
PROCPS_PROGRAMS = (
    "free", "hugetop", "kill", "pgrep", "pidof", "pidwait", "pkill",
    "pmap", "ps", "pwdx", "skill", "slabtop", "snice", "sysctl",
    "tload", "top", "uptime", "vmstat", "w", "watch",
)
PROCPS_ENTRYPOINT = {
    name: (
        "pgrep" if name in {"pgrep", "pidwait", "pkill"}
        else "skill" if name in {"skill", "snice"}
        else name
    )
    for name in PROCPS_PROGRAMS
}
SHADOW_PROGRAMS = (
    "chage", "chfn", "chgpasswd", "chpasswd", "chsh", "faillog",
    "getsubids", "gpasswd", "groupadd", "groupdel", "groupmod", "grpck",
    "grpconv", "grpunconv", "lastlog", "login", "newgidmap", "newgrp",
    "newuidmap", "newusers", "nologin", "passwd", "pwck", "pwconv",
    "pwunconv", "su", "useradd", "userdel", "usermod", "vipw", "sg",
    "vigr",
)
SHADOW_COLLISIONS = {
    "chfn", "chsh", "login", "newgrp", "nologin", "su", "vigr", "vipw",
}
SHADOW_ENTRYPOINT = {
    name: "newgrp" if name == "sg" else "vipw" if name == "vigr" else name
    for name in SHADOW_PROGRAMS
}


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


def undefined_symbols(path: Path) -> set[str]:
    output = subprocess.run(
        ["nm", "-u", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {
        fields[-1]
        for line in output.splitlines()
        if (fields := line.split())
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
    }


def verified_cargo_inline_proofs(repository, package, archives, source_hashes):
    index = repository / f"work/analysis/{package}-cargo-inline-proofs.json"
    proofs = json.loads(index.read_text())
    if set(proofs) != {str(path.relative_to(repository)) for path in archives}:
        raise RuntimeError(f"private-inline evidence does not match the selected {package} engines")
    for relative, selected in proofs.items():
        archive = repository / relative
        proof = archive.with_name(selected["file"])
        if sha256(proof) != selected["sha256"] or json.loads(proof.read_text())["archive_sha256"] != source_hashes[relative]:
            raise RuntimeError(f"stale private-inline provenance for {relative}")
    return proofs


def namespace_duplicate_c_symbols(
    libraries: list[Path], public_symbols: set[str], reserved_symbols: set[str], build: Path
) -> tuple[list[Path], dict[str, list[str]]]:
    """Give repeated C2Rust extern symbols crate-local link names.

    Rust-mangled/runtime/compiler-builtins symbols retain their normal COMDAT
    handling.  Public applet entrypoints remain unchanged.
    """
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    by_symbol: dict[str, set[int]] = {}

    def scan(library: Path) -> set[str]:
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
        return symbols

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        library_symbols = list(executor.map(scan, libraries))
    for index, symbols in enumerate(library_symbols):
        for symbol in symbols:
            by_symbol.setdefault(symbol, set()).add(index)
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
    owners = {symbol: sorted(by_symbol[symbol]) for symbol in duplicates}

    def rewrite(item: tuple[int, Path]) -> tuple[int, Path, list[str]]:
        index, library = item
        selected = sorted(
            symbol
            for symbol in library_symbols[index] & duplicates
            if symbol in reserved_symbols or index != owners[symbol][0]
        )
        if not selected:
            return index, library, selected
        prefix = f"rustbox_batch_{index:02d}_"
        output = build / "src" / f".rustbox-namespaced-{index:02d}-{library.name}"
        mapping = build / "src" / f".rustbox-namespaced-{index:02d}.map"
        shutil.copy2(library, output)
        mapping.write_text(
            "".join(f"{symbol} {prefix}{symbol}\n" for symbol in selected),
            encoding="utf-8",
        )
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(output)], check=True)
        return index, output, selected

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(rewrite, enumerate(libraries)))
    rewritten = [path for _, path, _ in results]
    report = {
        libraries[index].name: selected
        for index, _, selected in results
        if selected
    }
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


def namespace_bison_inputs(
    rust_library: Path, residue_objects: list[Path], build: Path
) -> tuple[Path, list[Path], list[str]]:
    """Keep Bison's translated/C hybrid surface private behind its bridge."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    inputs = [rust_library, *residue_objects]
    symbols: set[str] = set()
    for path in inputs:
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(path)], check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols.update(
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
            and not fields[-1].startswith(("_R", "rust_", "__rust", "__llvm"))
        )
    if "rustbox_bison_main" not in symbols:
        raise RuntimeError("Bison archive exports no translated entrypoint")
    destination = build / "src/.rustbox-bison"
    destination.mkdir(parents=True, exist_ok=True)
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(
            f"{symbol} "
            + ("rustbox_bison_engine_main" if symbol == "rustbox_bison_main"
               else f"rustbox_bison_private_{symbol}")
            + "\n"
            for symbol in sorted(symbols)
        ),
        encoding="utf-8",
    )
    mapped = []
    for path in inputs:
        output = destination / path.name
        shutil.copy2(path, output)
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(output)], check=True)
        mapped.append(output)
    definitions = set().union(*(set(defined_symbols(path)) for path in mapped))
    if "rustbox_bison_engine_main" not in definitions:
        raise RuntimeError("Bison isolation lost its translated engine entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Bison isolation left an unprefixed private definition")
    return mapped[0], mapped[1:], sorted(symbols)


def namespace_curl_inputs(
    rust_library: Path, residue_objects: list[Path], build: Path
) -> tuple[Path, list[Path], list[str]]:
    """Keep curl/libcurl's translated and C ABI surface private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    inputs = [rust_library, *residue_objects]
    symbols: set[str] = set()
    for path in inputs:
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(path)], check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols.update(
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
            and fields[-1] != "rustbox_curl_main"
            and not fields[-1].startswith(("_R", "rust_", "__rust", "__llvm"))
        )
    if "rustbox_curl_main" not in set(defined_symbols(rust_library)):
        raise RuntimeError("curl archive exports no translated entrypoint")
    destination = build / "src/.rustbox-curl"
    destination.mkdir(parents=True, exist_ok=True)
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(
            f"{symbol} rustbox_curl_private_{symbol}\n"
            for symbol in sorted(symbols)
        ),
        encoding="utf-8",
    )
    mapped = []
    for path in inputs:
        output = destination / path.name
        shutil.copy2(path, output)
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(output)], check=True)
        mapped.append(output)
    definitions = set().union(*(set(defined_symbols(path)) for path in mapped))
    if "rustbox_curl_main" not in definitions:
        raise RuntimeError("curl isolation lost its translated entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("curl isolation left an unprefixed private definition")
    return mapped[0], mapped[1:], sorted(symbols)


def namespace_inetutils_programs(
    libraries: dict[str, Path], telnet_boundary: Path, build: Path
) -> tuple[dict[str, Path], Path, dict[str, list[str]]]:
    """Keep each formerly separate Inetutils program namespace private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    destination = build / "src/.rustbox-inetutils"

    def isolate(name: str) -> tuple[str, Path, Path | None, list[str]]:
        entrypoint = f"rustbox_inetutils_{name}_main"
        inputs = [libraries[name]]
        if name == "telnet":
            inputs.append(telnet_boundary)
        symbols: set[str] = set()
        for path in inputs:
            output = subprocess.run(
                ["nm", "-g", "--defined-only", str(path)], check=True,
                text=True, stdout=subprocess.PIPE,
            ).stdout
            symbols.update(
                fields[-1]
                for line in output.splitlines()
                if len(fields := line.split()) >= 3
                and fields[-2] in strong_types
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
                and fields[-1] != entrypoint
                and not fields[-1].startswith(("_R", "rust_", "__rust", "__llvm"))
            )
        if entrypoint not in set(defined_symbols(libraries[name])):
            raise RuntimeError(f"Inetutils {name} archive exports no entrypoint")
        program_directory = destination / name
        program_directory.mkdir(parents=True, exist_ok=True)
        mapping = program_directory / "symbols.map"
        mapping.write_text(
            "".join(
                f"{symbol} rustbox_inetutils_{name}_private_{symbol}\n"
                for symbol in sorted(symbols)
            ),
            encoding="utf-8",
        )
        mapped = []
        for path in inputs:
            output = program_directory / path.name
            shutil.copy2(path, output)
            subprocess.run(
                ["objcopy", "--redefine-syms", str(mapping), str(output)], check=True
            )
            mapped.append(output)
        definitions = set().union(*(set(defined_symbols(path)) for path in mapped))
        if entrypoint not in definitions or any(symbol in definitions for symbol in symbols):
            raise RuntimeError(f"Inetutils {name} isolation is incomplete")
        boundary = mapped[1] if name == "telnet" else None
        return name, mapped[0], boundary, sorted(symbols)

    mapped_libraries: dict[str, Path] = {}
    report: dict[str, list[str]] = {}
    mapped_boundary: Path | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(isolate, INETUTILS_PROGRAMS))
    for name, mapped, boundary, symbols in results:
        mapped_libraries[name] = mapped
        if boundary is not None:
            mapped_boundary = boundary
        report[name] = symbols
    if mapped_boundary is None:
        raise RuntimeError("Inetutils telnet boundary was not isolated")
    return mapped_libraries, mapped_boundary, report


def namespace_iproute2_programs(
    libraries: dict[str, Path], build: Path
) -> tuple[dict[str, Path], dict[str, list[str]]]:
    """Keep every separately translated IPRoute2 engine namespace private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    destination = build / "src/.rustbox-iproute2"

    def isolate(name: str) -> tuple[str, Path, list[str]]:
        library = libraries[name]
        entrypoint = f"rustbox_iproute2_{name}_main"
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(library)], check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols = sorted({
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
            and fields[-1] != entrypoint
            and not fields[-1].startswith(("_R", "rust_", "__rust", "__llvm"))
            and not compiler_math.fullmatch(fields[-1])
        })
        if entrypoint not in set(defined_symbols(library)):
            raise RuntimeError(f"IPRoute2 {name} archive exports no entrypoint")
        program_directory = destination / name
        program_directory.mkdir(parents=True, exist_ok=True)
        mapping = program_directory / "symbols.map"
        mapping.write_text(
            "".join(
                f"{symbol} rustbox_iproute2_{name}_private_{symbol}\n"
                for symbol in symbols
            ),
            encoding="utf-8",
        )
        mapped = program_directory / library.name
        shutil.copy2(library, mapped)
        if symbols:
            subprocess.run(
                ["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True
            )
        definitions = set(defined_symbols(mapped))
        if entrypoint not in definitions or any(symbol in definitions for symbol in symbols):
            raise RuntimeError(f"IPRoute2 {name} isolation is incomplete")
        return name, mapped, symbols

    mapped_libraries: dict[str, Path] = {}
    report: dict[str, list[str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(isolate, IPROUTE2_PROGRAMS))
    for name, mapped, symbols in results:
        mapped_libraries[name] = mapped
        report[name] = symbols
    return mapped_libraries, report


def namespace_e2fsprogs_programs(
    libraries: dict[str, Path], build: Path
) -> tuple[dict[str, Path], dict[str, list[str]]]:
    """Keep every separately translated E2fsprogs engine namespace private."""
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    destination = build / "src/.rustbox-e2fsprogs"

    def isolate(name: str) -> tuple[str, Path, list[str]]:
        library = libraries[name]
        entrypoint = f"rustbox_e2fsprogs_{name}_main"
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(library)], check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols = sorted({
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", fields[-1])
            and fields[-1] != entrypoint
            and not fields[-1].startswith(("_R", "rust_", "__rust", "__llvm"))
            and not compiler_math.fullmatch(fields[-1])
        })
        if entrypoint not in set(defined_symbols(library)):
            raise RuntimeError(f"E2fsprogs {name} archive exports no entrypoint")
        program_directory = destination / name
        program_directory.mkdir(parents=True, exist_ok=True)
        mapping = program_directory / "symbols.map"
        mapping.write_text(
            "".join(
                f"{symbol} rustbox_e2fsprogs_{name}_private_{symbol}\n"
                for symbol in symbols
            ),
            encoding="utf-8",
        )
        mapped = program_directory / library.name
        shutil.copy2(library, mapped)
        if symbols:
            subprocess.run(
                ["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True
            )
        definitions = set(defined_symbols(mapped))
        if entrypoint not in definitions or any(symbol in definitions for symbol in symbols):
            raise RuntimeError(f"E2fsprogs {name} isolation is incomplete")
        return name, mapped, symbols

    mapped_libraries: dict[str, Path] = {}
    report: dict[str, list[str]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(isolate, E2FSPROGS_PROGRAMS))
    for name, mapped, symbols in results:
        mapped_libraries[name] = mapped
        report[name] = symbols
    return mapped_libraries, report


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


def namespace_gawk_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep GNU Gawk's parser, runtime, and bundled gnulib surface private."""
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
        )
        and fields[-1] != "rustbox_gawk_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("GNU Gawk archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-gawk"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_gawk_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_gawk_main") != 1:
        raise RuntimeError("GNU Gawk symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("GNU Gawk symbol isolation left an unprefixed definition")
    if any(f"rustbox_gawk_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("GNU Gawk symbol isolation lost a definition")
    return mapped, symbols


def namespace_flex_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Flex's generated scanner, parser, and generator state private."""
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
        and fields[-1] != "rustbox_flex_main"
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("Flex archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-flex"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_flex_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_flex_main") != 1:
        raise RuntimeError("Flex symbol isolation damaged its public entrypoint")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Flex symbol isolation left an unprefixed definition")
    if any(f"rustbox_flex_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Flex symbol isolation lost a definition")
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


def namespace_ncurses_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Ncurses' programs, terminal database, and tty engine private."""
    public = {
        "rustbox_clear_main", "rustbox_infocmp_main", "rustbox_tabs_main",
        "rustbox_tic_main", "rustbox_toe_main", "rustbox_tput_main",
        "rustbox_tset_main",
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
            or re.fullmatch(r"_[a-z][A-Za-z0-9_]*", fields[-1])
        )
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("Ncurses archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-ncurses"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_ncurses_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"Ncurses symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Ncurses symbol isolation left an unprefixed definition")
    if any(f"rustbox_ncurses_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Ncurses symbol isolation lost a definition")
    return mapped, symbols


def namespace_xz_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep XZ's four programs and embedded liblzma implementation private."""
    public = {
        "rustbox_xz_main", "rustbox_xzdec_main",
        "rustbox_lzmadec_main", "rustbox_lzmainfo_main",
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
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and not fields[-1].startswith("rust_")
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("XZ archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-xz"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_xz_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"XZ symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("XZ symbol isolation left an unprefixed definition")
    if any(f"rustbox_xz_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("XZ symbol isolation lost a definition")
    return mapped, symbols


def namespace_zstd_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep zstd's CLI and embedded compression implementation private."""
    public = {"rustbox_zstd_main"}
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
        raise RuntimeError("zstd archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-zstd"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_zstd_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_zstd_main") != 1:
        raise RuntimeError("zstd symbol isolation damaged rustbox_zstd_main")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("zstd symbol isolation left an unprefixed definition")
    if any(f"rustbox_zstd_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("zstd symbol isolation lost a definition")
    return mapped, symbols


def namespace_kmod_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Kmod's library, module parsers, and seven-program engine private."""
    public = {"rustbox_kmod_main"}
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
        raise RuntimeError("Kmod archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-kmod"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_kmod_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    if mapped_definitions.count("rustbox_kmod_main") != 1:
        raise RuntimeError("Kmod symbol isolation damaged rustbox_kmod_main")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Kmod symbol isolation left an unprefixed definition")
    if any(f"rustbox_kmod_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Kmod symbol isolation lost a definition")
    return mapped, symbols


def namespace_procps_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Procps's libproc2 implementation and 17 engines private."""
    public = {
        f"rustbox_procps_{name}_main" for name in set(PROCPS_ENTRYPOINT.values())
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
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and (
            not fields[-1].startswith("rust_")
            or fields[-1] == "rust_eh_personality"
        )
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("Procps archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-procps"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_procps_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"Procps symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Procps symbol isolation left an unprefixed definition")
    if any(f"rustbox_procps_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Procps symbol isolation lost a definition")
    return mapped, symbols


def namespace_shadow_library(
    rust_library: Path, build: Path
) -> tuple[Path, list[str]]:
    """Keep Shadow's libshadow/libsubid implementation and engines private."""
    public = {
        f"rustbox_shadow_{name}_main" for name in set(SHADOW_ENTRYPOINT.values())
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
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
        and fields[-1] not in public
        and (
            not fields[-1].startswith("rust_")
            or fields[-1] == "rust_eh_personality"
        )
        and not compiler_math.fullmatch(fields[-1])
    })
    if not symbols:
        raise RuntimeError("Shadow archive exports no namespaceable C symbols")
    destination = build / "src/.rustbox-shadow"
    destination.mkdir(parents=True, exist_ok=True)
    mapped = destination / rust_library.name
    mapping = destination / "symbols.map"
    mapping.write_text(
        "".join(f"{symbol} rustbox_shadow_private_{symbol}\n" for symbol in symbols),
        encoding="utf-8",
    )
    shutil.copy2(rust_library, mapped)
    subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
    mapped_definitions = defined_symbols(mapped)
    definitions = set(mapped_definitions)
    for symbol in public:
        if mapped_definitions.count(symbol) != 1:
            raise RuntimeError(f"Shadow symbol isolation damaged {symbol}")
    if any(symbol in definitions for symbol in symbols):
        raise RuntimeError("Shadow symbol isolation left an unprefixed definition")
    if any(f"rustbox_shadow_private_{symbol}" not in definitions for symbol in symbols):
        raise RuntimeError("Shadow symbol isolation lost a definition")
    return mapped, symbols


def coalesce_identical_archive_members(
    provider: Path,
    consumer: Path,
    destination: Path,
    label: str,
) -> tuple[Path, list[str], int]:
    """Remove byte-identical Rust runtime members from a later staticlib."""
    def members(path: Path) -> list[str]:
        return subprocess.run(
            ["ar", "t", str(path)], check=True, text=True, stdout=subprocess.PIPE
        ).stdout.splitlines()

    provider_members = members(provider)
    consumer_members = members(consumer)
    if len(provider_members) != len(set(provider_members)):
        raise RuntimeError(f"{label} provider archive has duplicate member names")
    if len(consumer_members) != len(set(consumer_members)):
        raise RuntimeError(f"{label} consumer archive has duplicate member names")
    common = sorted(set(provider_members) & set(consumer_members))
    if not common:
        raise RuntimeError(f"{label} archives expose no common runtime members")

    with tempfile.TemporaryDirectory(prefix="rustbox-runtime-coalesce-") as temporary:
        temporary_root = Path(temporary)
        provider_root = temporary_root / "provider"
        consumer_root = temporary_root / "consumer"
        provider_root.mkdir()
        consumer_root.mkdir()
        subprocess.run(
            ["ar", "x", str(provider), *common], cwd=provider_root, check=True
        )
        subprocess.run(
            ["ar", "x", str(consumer), *common], cwd=consumer_root, check=True
        )
        different = [
            name for name in common
            if sha256(provider_root / name) != sha256(consumer_root / name)
        ]
        common_bytes = sum(
            (provider_root / name).stat().st_size for name in common
        )
    if different:
        raise RuntimeError(
            f"{label} archive members differ: {different[:5]}"
        )

    destination.mkdir(parents=True, exist_ok=True)
    coalesced = destination / consumer.name
    shutil.copy2(consumer, coalesced)
    subprocess.run(["ar", "d", str(coalesced), *common], check=True)
    remaining = members(coalesced)
    if set(common) & set(remaining):
        raise RuntimeError(f"{label} coalescing retained a shared member")
    if len(remaining) != len(consumer_members) - len(common):
        raise RuntimeError(f"{label} coalescing removed the wrong member count")
    return coalesced, common, common_bytes


def namespace_tar_inputs(
    rust_library: Path,
    residue_objects: list[Path],
    acl_symbols: list[str],
    build: Path,
) -> tuple[Path, list[Path], list[str], list[str]]:
    """Keep GNU tar private and bind its ACL calls to translated libacl."""
    public = {"rustbox_tar_main", "rustbox_rmt_main"}
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    inputs = [rust_library, *residue_objects]
    symbols: set[str] = set()
    for source in inputs:
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(source)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols.update(
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and (
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
                or re.fullmatch(r"_[a-z][A-Za-z0-9_]*", fields[-1])
                or fields[-1] == "__xargmatch_internal"
            )
            and fields[-1] not in public
            and not fields[-1].startswith("rust_")
            and not compiler_math.fullmatch(fields[-1])
        )
    if not symbols:
        raise RuntimeError("GNU tar inputs export no namespaceable C symbols")

    acl_imports = sorted(
        (
            set().union(*(undefined_symbols(source) for source in inputs))
            & set(acl_symbols)
        )
        - symbols
    )
    expected_acl_imports = {
        "acl_delete_def_file", "acl_entries", "acl_free", "acl_from_mode",
        "acl_from_text", "acl_get_entry", "acl_get_fd", "acl_get_file",
        "acl_get_tag_type", "acl_set_fd", "acl_set_file", "acl_to_any_text",
        "acl_to_text",
    }
    if set(acl_imports) != expected_acl_imports:
        raise RuntimeError(
            f"GNU tar ACL import closure changed: {acl_imports}"
        )

    destination = build / "src/.rustbox-tar"
    destination.mkdir(parents=True, exist_ok=True)
    mapping = destination / "symbols.map"
    private_symbols = sorted(symbols)
    mapping.write_text(
        "".join(
            [f"{symbol} rustbox_tar_private_{symbol}\n" for symbol in private_symbols]
            + [f"{symbol} rustbox_acl_private_{symbol}\n" for symbol in acl_imports]
        ),
        encoding="utf-8",
    )
    mapped_inputs: list[Path] = []
    for source in inputs:
        mapped = destination / source.name
        shutil.copy2(source, mapped)
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
        mapped_inputs.append(mapped)

    mapped_library, *mapped_residue = mapped_inputs
    mapped_definitions = set().union(
        *(set(defined_symbols(source)) for source in mapped_inputs)
    )
    for symbol in public:
        if sum(defined_symbols(source).count(symbol) for source in mapped_inputs) != 1:
            raise RuntimeError(f"GNU tar symbol isolation damaged {symbol}")
    if symbols & mapped_definitions:
        raise RuntimeError("GNU tar symbol isolation left an unprefixed definition")
    if any(f"rustbox_tar_private_{symbol}" not in mapped_definitions for symbol in symbols):
        raise RuntimeError("GNU tar symbol isolation lost a definition")
    mapped_undefined = set().union(
        *(undefined_symbols(source) for source in mapped_inputs)
    )
    if set(acl_imports) & mapped_undefined:
        raise RuntimeError("GNU tar retained unbound system libacl imports")
    if any(f"rustbox_acl_private_{symbol}" not in mapped_undefined for symbol in acl_imports):
        raise RuntimeError("GNU tar lost a translated libacl import")
    return mapped_library, mapped_residue, private_symbols, acl_imports


def namespace_findutils_inputs(
    rust_library: Path, residue_objects: list[Path], build: Path
) -> tuple[Path, list[Path], list[str]]:
    """Keep Findutils and its C long-double variadic ABI units private."""
    public = {
        "rustbox_find_main", "rustbox_xargs_main",
        "rustbox_locate_main", "rustbox_frcode_main",
    }
    strong_types = {"B", "C", "D", "G", "R", "S", "T"}
    compiler_math = re.compile(
        r"^(?:cbrt|ceil|copysign|fabs|fdim|floor|fma|fmax|fmaximum|fmin|fminimum|fmod|rint|round|sqrt|trunc)(?:f|f16|f128)?$"
    )
    inputs = [rust_library, *residue_objects]
    symbols: set[str] = set()
    for source in inputs:
        output = subprocess.run(
            ["nm", "-g", "--defined-only", str(source)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        symbols.update(
            fields[-1]
            for line in output.splitlines()
            if len(fields := line.split()) >= 3
            and fields[-2] in strong_types
            and (
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", fields[-1])
                or re.fullmatch(r"_[a-z][A-Za-z0-9_]*", fields[-1])
                or fields[-1] == "__xargmatch_internal"
            )
            and fields[-1] not in public
            and not fields[-1].startswith("rust_")
            and not compiler_math.fullmatch(fields[-1])
        )
    if not symbols:
        raise RuntimeError("GNU Findutils inputs export no namespaceable C symbols")
    destination = build / "src/.rustbox-findutils"
    destination.mkdir(parents=True, exist_ok=True)
    mapping = destination / "symbols.map"
    private_symbols = sorted(symbols)
    mapping.write_text(
        "".join(
            f"{symbol} rustbox_findutils_private_{symbol}\n"
            for symbol in private_symbols
        ),
        encoding="utf-8",
    )
    mapped_inputs: list[Path] = []
    for source in inputs:
        mapped = destination / source.name
        shutil.copy2(source, mapped)
        subprocess.run(["objcopy", "--redefine-syms", str(mapping), str(mapped)], check=True)
        mapped_inputs.append(mapped)
    mapped_library, *mapped_residue = mapped_inputs
    mapped_definitions = set().union(
        *(set(defined_symbols(source)) for source in mapped_inputs)
    )
    for symbol in public:
        if sum(defined_symbols(source).count(symbol) for source in mapped_inputs) != 1:
            raise RuntimeError(f"GNU Findutils symbol isolation damaged {symbol}")
    if symbols & mapped_definitions:
        raise RuntimeError("GNU Findutils symbol isolation left an unprefixed definition")
    if any(
        f"rustbox_findutils_private_{symbol}" not in mapped_definitions
        for symbol in symbols
    ):
        raise RuntimeError("GNU Findutils symbol isolation lost a definition")
    return mapped_library, mapped_residue, private_symbols


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
    inetutils_declarations = "\n".join(
        f"extern int rustbox_inetutils_{name}_main(int, char **);"
        for name in INETUTILS_PROGRAMS
    )
    inetutils_selection_lines = []
    for name in INETUTILS_PROGRAMS:
        public_name = f"inetutils-{name}" if name in {"hostname", "logger"} else name
        prefix = f'    if (!force_util_linux && strcmp(name, "{public_name}") == 0) '
        if public_name == name:
            inetutils_selection_lines.append(
                prefix + f"return rustbox_inetutils_{name}_main(argc, argv);"
            )
        else:
            inetutils_selection_lines.append(
                prefix + "{ argv[0] = \"" + name + "\"; "
                "program_invocation_name = argv[0]; program_invocation_short_name = argv[0]; "
                f"return rustbox_inetutils_{name}_main(argc, argv); }}"
            )
    inetutils_selections = "\n".join(inetutils_selection_lines)
    iproute2_declarations = "\n".join(
        f"extern int rustbox_iproute2_{name}_main(int, char **);"
        for name in IPROUTE2_PROGRAMS
    ) + "\nextern int rustbox_iproute2_routel_main(int, char **);"
    iproute2_selection_lines = []
    for name in IPROUTE2_PUBLIC_NAMES:
        target = "lnstat" if name in {"ctstat", "rtstat"} else name
        iproute2_selection_lines.append(
            f'    if (!force_util_linux && strcmp(name, "{name}") == 0) '
            f'return rustbox_iproute2_{target}_main(argc, argv);'
        )
    iproute2_selections = "\n".join(iproute2_selection_lines)
    e2fsprogs_declarations = "\n".join(
        f"extern int rustbox_e2fsprogs_{name}_main(int, char **);"
        for name in (*E2FSPROGS_PROGRAMS, *E2FSPROGS_FRONTENDS)
    )
    e2fsprogs_selection_lines = []
    for engine in E2FSPROGS_PROGRAMS:
        public_name = (
            "e2fsprogs-fsck" if engine == "fsck"
            else "mklost+found" if engine == "mklost_found"
            else engine
        )
        if engine == "fsck":
            e2fsprogs_selection_lines.append(
                '    if (!force_util_linux && strcmp(name, "e2fsprogs-fsck") == 0) {'
                ' argv[0] = "fsck"; program_invocation_name = argv[0];'
                ' program_invocation_short_name = argv[0];'
                ' return rustbox_e2fsprogs_fsck_main(argc, argv); }'
            )
        else:
            e2fsprogs_selection_lines.append(
                f'    if (!force_util_linux && strcmp(name, "{public_name}") == 0) '
                f'return rustbox_e2fsprogs_{engine}_main(argc, argv);'
            )
    for public_name, engine in sorted(E2FSPROGS_ALIASES.items()):
        e2fsprogs_selection_lines.append(
            f'    if (!force_util_linux && strcmp(name, "{public_name}") == 0) '
            f'return rustbox_e2fsprogs_{engine}_main(argc, argv);'
        )
    for name in E2FSPROGS_FRONTENDS:
        e2fsprogs_selection_lines.append(
            f'    if (!force_util_linux && strcmp(name, "{name}") == 0) '
            f'return rustbox_e2fsprogs_{name}_main(argc, argv);'
        )
    e2fsprogs_selections = "\n".join(e2fsprogs_selection_lines)
    procps_declarations = "\n".join(
        f"extern int rustbox_procps_{name}_main(int, char **);"
        for name in sorted(set(PROCPS_ENTRYPOINT.values()))
    )
    procps_selection_lines = []
    for name in PROCPS_PROGRAMS:
        public_name = f"procps-{name}" if name in {"kill", "uptime"} else name
        symbol = PROCPS_ENTRYPOINT[name]
        prefix = f'    if (!force_util_linux && strcmp(name, "{public_name}") == 0) '
        if public_name == name:
            procps_selection_lines.append(
                prefix + f"return rustbox_procps_{symbol}_main(argc, argv);"
            )
        else:
            procps_selection_lines.append(
                prefix + f"{{ argv[0] = \"{name}\"; "
                "program_invocation_name = argv[0]; program_invocation_short_name = argv[0]; "
                f"return rustbox_procps_{symbol}_main(argc, argv); }}"
            )
    procps_selections = "\n".join(procps_selection_lines)
    shadow_declarations = "\n".join(
        f"extern int rustbox_shadow_{name}_main(int, char **);"
        for name in sorted(set(SHADOW_ENTRYPOINT.values()))
    )
    shadow_selection_lines = []
    for name in SHADOW_PROGRAMS:
        public_name = f"shadow-{name}" if name in SHADOW_COLLISIONS else name
        symbol = SHADOW_ENTRYPOINT[name]
        prefix = f'    if (!force_util_linux && strcmp(name, "{public_name}") == 0) '
        if public_name == name:
            shadow_selection_lines.append(
                prefix + f"return rustbox_shadow_{symbol}_main(argc, argv);"
            )
        else:
            shadow_selection_lines.append(
                prefix + f'{{ argv[0] = "{name}"; '
                "program_invocation_name = argv[0]; program_invocation_short_name = argv[0]; "
                f"return rustbox_shadow_{symbol}_main(argc, argv); }}"
            )
    shadow_selections = "\n".join(shadow_selection_lines)
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
extern int rustbox_gawk_main(int, char **);
extern int rustbox_gawkbug_main(int, char **);
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
extern int rustbox_xz_main(int, char **);
extern int rustbox_xzdec_main(int, char **);
extern int rustbox_lzmadec_main(int, char **);
extern int rustbox_lzmainfo_main(int, char **);
extern int rustbox_xzdiff_main(int, char **);
extern int rustbox_xzgrep_main(int, char **);
extern int rustbox_xzless_main(int, char **);
extern int rustbox_xzmore_main(int, char **);
extern int rustbox_zstd_main(int, char **);
extern int rustbox_zstdgrep_main(int, char **);
extern int rustbox_zstdless_main(int, char **);
extern int rustbox_tar_main(int, char **);
extern int rustbox_rmt_main(int, char **);
extern int rustbox_clear_main(int, char **);
extern int rustbox_infocmp_main(int, char **);
extern int rustbox_tabs_main(int, char **);
extern int rustbox_tic_main(int, char **);
extern int rustbox_toe_main(int, char **);
extern int rustbox_tput_main(int, char **);
extern int rustbox_tset_main(int, char **);
extern int rustbox_ncursesw6_config_main(int, char **);
extern int rustbox_find_main(int, char **);
extern int rustbox_xargs_main(int, char **);
extern int rustbox_locate_main(int, char **);
extern int rustbox_updatedb_main(int, char **);
extern int rustbox_flex_main(int, char **);
extern int rustbox_flexpp_main(int, char **);
extern int rustbox_lex_main(int, char **);
extern int rustbox_bison_main(int, char **);
extern int rustbox_yacc_main(int, char **);
extern int rustbox_curl_main(int, char **);
extern int rustbox_curl_config_main(int, char **);
extern int rustbox_kmod_main(int, char **);
"""
        + inetutils_declarations
        + """
"""
        + iproute2_declarations
        + """
"""
        + e2fsprogs_declarations
        + """
"""
        + procps_declarations
        + """
"""
        + shadow_declarations
        + """
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
    if (!force_util_linux && (strcmp(name, "gawk") == 0 || strcmp(name, "awk") == 0))
        return rustbox_gawk_main(argc, argv);
    if (!force_util_linux && strcmp(name, "gawkbug") == 0)
        return rustbox_gawkbug_main(argc, argv);
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
    if (!force_util_linux &&
        (strcmp(name, "xz") == 0 || strcmp(name, "unxz") == 0 ||
         strcmp(name, "xzcat") == 0 || strcmp(name, "lzma") == 0 ||
         strcmp(name, "unlzma") == 0 || strcmp(name, "lzcat") == 0))
        return rustbox_xz_main(argc, argv);
    if (!force_util_linux && strcmp(name, "xzdec") == 0)
        return rustbox_xzdec_main(argc, argv);
    if (!force_util_linux && strcmp(name, "lzmadec") == 0)
        return rustbox_lzmadec_main(argc, argv);
    if (!force_util_linux && strcmp(name, "lzmainfo") == 0)
        return rustbox_lzmainfo_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "xzdiff") == 0 || strcmp(name, "xzcmp") == 0 ||
         strcmp(name, "lzdiff") == 0 || strcmp(name, "lzcmp") == 0))
        return rustbox_xzdiff_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "xzgrep") == 0 || strcmp(name, "xzegrep") == 0 ||
         strcmp(name, "xzfgrep") == 0 || strcmp(name, "lzgrep") == 0 ||
         strcmp(name, "lzegrep") == 0 || strcmp(name, "lzfgrep") == 0))
        return rustbox_xzgrep_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "xzless") == 0 || strcmp(name, "lzless") == 0))
        return rustbox_xzless_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "xzmore") == 0 || strcmp(name, "lzmore") == 0))
        return rustbox_xzmore_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "zstd") == 0 || strcmp(name, "zstdmt") == 0 ||
         strcmp(name, "unzstd") == 0 || strcmp(name, "zstdcat") == 0))
        return rustbox_zstd_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zstdgrep") == 0)
        return rustbox_zstdgrep_main(argc, argv);
    if (!force_util_linux && strcmp(name, "zstdless") == 0)
        return rustbox_zstdless_main(argc, argv);
    if (!force_util_linux && strcmp(name, "tar") == 0)
        return rustbox_tar_main(argc, argv);
    if (!force_util_linux && strcmp(name, "rmt") == 0)
        return rustbox_rmt_main(argc, argv);
    if (!force_util_linux && strcmp(name, "clear") == 0)
        return rustbox_clear_main(argc, argv);
    if (!force_util_linux && strcmp(name, "infocmp") == 0)
        return rustbox_infocmp_main(argc, argv);
    if (!force_util_linux && strcmp(name, "tabs") == 0)
        return rustbox_tabs_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "tic") == 0 || strcmp(name, "captoinfo") == 0 ||
         strcmp(name, "infotocap") == 0))
        return rustbox_tic_main(argc, argv);
    if (!force_util_linux && strcmp(name, "toe") == 0)
        return rustbox_toe_main(argc, argv);
    if (!force_util_linux && strcmp(name, "tput") == 0)
        return rustbox_tput_main(argc, argv);
    if (!force_util_linux && (strcmp(name, "tset") == 0 || strcmp(name, "reset") == 0))
        return rustbox_tset_main(argc, argv);
    if (!force_util_linux && strcmp(name, "ncursesw6-config") == 0)
        return rustbox_ncursesw6_config_main(argc, argv);
    if (!force_util_linux && strcmp(name, "find") == 0)
        return rustbox_find_main(argc, argv);
    if (!force_util_linux && strcmp(name, "xargs") == 0)
        return rustbox_xargs_main(argc, argv);
    if (!force_util_linux && strcmp(name, "locate") == 0)
        return rustbox_locate_main(argc, argv);
    if (!force_util_linux && strcmp(name, "updatedb") == 0)
        return rustbox_updatedb_main(argc, argv);
    if (!force_util_linux && strcmp(name, "flex") == 0)
        return rustbox_flex_main(argc, argv);
    if (!force_util_linux && strcmp(name, "flex++") == 0)
        return rustbox_flexpp_main(argc, argv);
    if (!force_util_linux && strcmp(name, "lex") == 0)
        return rustbox_lex_main(argc, argv);
    if (!force_util_linux && strcmp(name, "bison") == 0)
        return rustbox_bison_main(argc, argv);
    if (!force_util_linux && strcmp(name, "yacc") == 0)
        return rustbox_yacc_main(argc, argv);
    if (!force_util_linux && strcmp(name, "curl") == 0)
        return rustbox_curl_main(argc, argv);
    if (!force_util_linux && strcmp(name, "curl-config") == 0)
        return rustbox_curl_config_main(argc, argv);
    if (!force_util_linux &&
        (strcmp(name, "kmod") == 0 || strcmp(name, "depmod") == 0 ||
         strcmp(name, "insmod") == 0 || strcmp(name, "lsmod") == 0 ||
         strcmp(name, "modinfo") == 0 || strcmp(name, "modprobe") == 0 ||
         strcmp(name, "rmmod") == 0))
        return rustbox_kmod_main(argc, argv);
"""
        + procps_selections
        + """
"""
        + shadow_selections
        + """
"""
        + inetutils_selections
        + """
"""
        + iproute2_selections
        + """
"""
        + e2fsprogs_selections
        + """
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
    parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
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
    parser.add_argument("--gawk-rust-library", type=Path, required=True)
    parser.add_argument("--gawk-pma-residue", type=Path, required=True)
    parser.add_argument("--bc-rust-library", type=Path, required=True)
    parser.add_argument("--attr-rust-library", type=Path, required=True)
    parser.add_argument("--acl-rust-library", type=Path, required=True)
    parser.add_argument("--lz4-rust-library", type=Path, required=True)
    parser.add_argument("--less-rust-library", type=Path, required=True)
    parser.add_argument("--gzip-rust-library", type=Path, required=True)
    parser.add_argument("--gzip-support-library", type=Path, required=True)
    parser.add_argument("--xz-rust-library", type=Path, required=True)
    parser.add_argument("--zstd-rust-library", type=Path, required=True)
    parser.add_argument("--tar-rust-library", type=Path, required=True)
    parser.add_argument("--ncurses-rust-library", type=Path, required=True)
    parser.add_argument("--tar-c-residue-directory", type=Path, required=True)
    parser.add_argument("--findutils-rust-library", type=Path, required=True)
    parser.add_argument("--findutils-c-residue-directory", type=Path, required=True)
    parser.add_argument("--flex-rust-library", type=Path, required=True)
    parser.add_argument("--bison-rust-library", type=Path, required=True)
    parser.add_argument("--bison-c-residue-directory", type=Path, required=True)
    parser.add_argument("--curl-rust-library", type=Path, required=True)
    parser.add_argument("--curl-c-residue-directory", type=Path, required=True)
    parser.add_argument("--inetutils-rust-directory", type=Path, required=True)
    parser.add_argument("--inetutils-telnet-c-boundary", type=Path, required=True)
    parser.add_argument("--shared-stdio", type=Path)
    parser.add_argument("--native-c-strings", type=Path)
    parser.add_argument("--va-list-layouts", type=Path)
    parser.add_argument("--iproute2-routing-protocols", action="store_true")
    parser.add_argument("--ncurses-termtypes", type=Path)
    parser.add_argument("--curl-manual", action="store_true")
    parser.add_argument("--tar-borrowed-timestamps", action="store_true")
    parser.add_argument("--lz4-benchmark-dictionary", action="store_true")
    parser.add_argument("--bison-literal-lengths", action="store_true")
    parser.add_argument("--iproute2-netlink-protocols", action="store_true")
    parser.add_argument("--iproute2-route-names", action="store_true")
    parser.add_argument("--iproute2-address-protocols", action="store_true")
    parser.add_argument("--iproute2-address-protocol-copies", action="store_true")
    parser.add_argument("--iproute2-rust-directory", type=Path, required=True)
    parser.add_argument("--e2fsprogs-rust-directory", type=Path, required=True)
    parser.add_argument("--e2fsprogs-dirhash-arrays", type=Path,
                        help="pinned fixed-array directory hash candidates for the staged E2fsprogs archives")
    parser.add_argument("--kmod-rust-library", type=Path, required=True)
    parser.add_argument("--procps-rust-library", type=Path, required=True)
    parser.add_argument("--shadow-rust-library", type=Path, required=True)
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
    gawk_rust_library = args.gawk_rust_library.resolve()
    gawk_pma_residue = args.gawk_pma_residue.resolve()
    bc_rust_library = args.bc_rust_library.resolve()
    attr_rust_library = args.attr_rust_library.resolve()
    acl_rust_library = args.acl_rust_library.resolve()
    lz4_rust_library = args.lz4_rust_library.resolve()
    less_rust_library = args.less_rust_library.resolve()
    gzip_rust_library = args.gzip_rust_library.resolve()
    gzip_support_library = args.gzip_support_library.resolve()
    xz_rust_library = args.xz_rust_library.resolve()
    zstd_rust_library = args.zstd_rust_library.resolve()
    tar_rust_library = args.tar_rust_library.resolve()
    ncurses_rust_library = args.ncurses_rust_library.resolve()
    tar_residue_directory = args.tar_c_residue_directory.resolve()
    tar_residue_objects = [
        tar_residue_directory / name
        for name in ("human.o", "printf-args.o", "printf-parse.o", "vasnprintf.o")
    ]
    findutils_rust_library = args.findutils_rust_library.resolve()
    flex_rust_library = args.flex_rust_library.resolve()
    bison_rust_library = args.bison_rust_library.resolve()
    bison_residue_directory = args.bison_c_residue_directory.resolve()
    bison_residue_objects = [
        bison_residue_directory / name
        for name in ("printf-args.o", "printf-frexpl.o", "printf-parse.o", "vasnprintf.o")
    ]
    curl_rust_library = args.curl_rust_library.resolve()
    curl_residue_directory = args.curl_c_residue_directory.resolve()
    curl_residue_objects = [curl_residue_directory / "mprintf.o"]
    inetutils_rust_directory = args.inetutils_rust_directory.resolve()
    inetutils_libraries = {
        name: inetutils_rust_directory / f"lib{name}_audit.a"
        for name in INETUTILS_PROGRAMS
    }
    inetutils_telnet_boundary = args.inetutils_telnet_c_boundary.resolve()
    iproute2_rust_directory = args.iproute2_rust_directory.resolve()
    iproute2_libraries = {
        name: iproute2_rust_directory / name / "release" / f"lib{name}_audit.a"
        for name in IPROUTE2_PROGRAMS
    }
    # Keep the canonical translation archive available as a differential oracle.
    bridge_archive = iproute2_rust_directory.parent / "rustbox-bridge/libbridge_audit.a"
    bridge_raw_types = build_bridge(iproute2_rust_directory, bridge_archive, prune_inlines=True)
    bridge_inline_proof = bridge_raw_types.pop("inline_proof")
    iproute2_libraries["bridge"] = bridge_archive
    e2fsprogs_rust_directory = args.e2fsprogs_rust_directory.resolve()
    e2fsprogs_libraries = {
        name: e2fsprogs_rust_directory / name / "release" / f"lib{name}_audit.a"
        for name in E2FSPROGS_PROGRAMS
    }
    checksum_consumers, checksum_objects = build_shared(
        e2fsprogs_rust_directory.parent, e2fsprogs_rust_directory.parent / "rustbox-e2fsprogs-shared"
    )
    # Each proof binds the trimmed compiler inputs to the exact pre-cleanup release archive.
    selected_archives = list(checksum_consumers.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
        inline_proofs = {
            str(archive.relative_to(repository)): {"file": proof.name, "sha256": sha256(proof)}
            for archive, proof in zip(selected_archives, workers.map(prepare_archive, selected_archives))
        }
    # Verify the C-facing interface before namespace isolation or section GC.
    # Rust compiler-internal symbols may change when a translation unit is removed.
    exports_by_sha = {}

    def c_exports(path):
        # An archive can serve as the candidate of one conversion and the
        # control of the next. Read GNU nm once for each distinct set of bytes.
        checksum = sha256(path)
        if checksum not in exports_by_sha:
            names = frozenset(name for name in defined_symbols(path) if not name.startswith(("_ZN", "_R"))
                              and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))
            if sha256(path) != checksum:
                raise ValueError(f"archive changed during symbol comparison: {path}")
            exports_by_sha[checksum] = names
        return exports_by_sha[checksum]
    bitmap_callers = []
    for name, archive in checksum_consumers.items():
        original = c_exports(e2fsprogs_libraries[name])
        hardened = c_exports(archive)
        if original - hardened != set(CRC_SYMBOLS) | {"ext2fs_bitcount"} or hardened - original:
            raise RuntimeError(f"unexpected C export changes in checksum consumer {name}")
        references = undefined_symbols(archive)
        if "ext2fs_bitcount" in references:
            raise RuntimeError(f"stale bitmap reference in {name}")
        if BITCOUNT_SYMBOL in references:
            bitmap_callers.append(name)
        if references.intersection(CRC_SYMBOLS) or not {
                CRC_SYMBOLS["ext2fs_crc16"], CRC_SYMBOLS["ext2fs_crc32c_le"]} <= references:
            raise RuntimeError(f"unexpected checksum linkage in {name}")
    if sorted(bitmap_callers) != ["e2fsck", "resize2fs"]:
        raise RuntimeError(f"unexpected bitmap counter callers: {bitmap_callers}")
    e2fsprogs_libraries.update(checksum_consumers)
    kmod_rust_library = args.kmod_rust_library.resolve()
    procps_rust_library = args.procps_rust_library.resolve()
    shadow_rust_library = args.shadow_rust_library.resolve()
    findutils_residue_directory = args.findutils_c_residue_directory.resolve()
    findutils_residue_objects = [
        findutils_residue_directory / name
        for name in ("printf-args.o", "printf-parse.o", "vasnprintf.o")
    ]
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
    coreutils_runtime_provider_index = 1
    coreutils_runtime_provider = libraries[coreutils_runtime_provider_index]
    if coreutils_runtime_provider.name != "libcoreutils_small_01_reachable.a":
        raise RuntimeError("pinned Coreutils Rust runtime provider changed")

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
        gawk_rust_library, gawk_pma_residue,
        attr_rust_library, acl_rust_library, lz4_rust_library, less_rust_library,
        gzip_rust_library, xz_rust_library, zstd_rust_library, tar_rust_library,
        ncurses_rust_library, findutils_rust_library,
        flex_rust_library,
        bison_rust_library, *bison_residue_objects,
        curl_rust_library, *curl_residue_objects,
        *inetutils_libraries.values(), inetutils_telnet_boundary,
        *iproute2_libraries.values(),
        *e2fsprogs_libraries.values(),
        kmod_rust_library, procps_rust_library, shadow_rust_library,
        gzip_support_library,
        *tar_residue_objects,
        *findutils_residue_objects,
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
    libraries.append(gawk_rust_library)
    gawk_library_index = len(libraries) - 1
    libraries.append(gawk_pma_residue)
    libraries.append(bc_rust_library)
    bc_library_index = len(libraries) - 1
    libraries.append(attr_rust_library)
    attr_library_index = len(libraries) - 1
    libraries.append(tar_rust_library)
    tar_library_index = len(libraries) - 1
    libraries.append(acl_rust_library)
    acl_library_index = len(libraries) - 1
    libraries.append(lz4_rust_library)
    lz4_library_index = len(libraries) - 1
    libraries.append(less_rust_library)
    less_library_index = len(libraries) - 1
    libraries.append(gzip_rust_library)
    gzip_library_index = len(libraries) - 1
    libraries.append(xz_rust_library)
    xz_library_index = len(libraries) - 1
    libraries.append(zstd_rust_library)
    zstd_library_index = len(libraries) - 1
    libraries.append(ncurses_rust_library)
    ncurses_library_index = len(libraries) - 1
    libraries.append(findutils_rust_library)
    findutils_library_index = len(libraries) - 1
    libraries.append(flex_rust_library)
    flex_library_index = len(libraries) - 1
    libraries.append(bison_rust_library)
    bison_library_index = len(libraries) - 1
    libraries.append(curl_rust_library)
    curl_library_index = len(libraries) - 1
    inetutils_library_indices = {}
    for name in INETUTILS_PROGRAMS:
        libraries.append(inetutils_libraries[name])
        inetutils_library_indices[name] = len(libraries) - 1
    iproute2_library_indices = {}
    for name in IPROUTE2_PROGRAMS:
        libraries.append(iproute2_libraries[name])
        iproute2_library_indices[name] = len(libraries) - 1
    e2fsprogs_library_indices = {}
    for name in E2FSPROGS_PROGRAMS:
        libraries.append(e2fsprogs_libraries[name])
        e2fsprogs_library_indices[name] = len(libraries) - 1
    libraries.extend(checksum_objects)
    libraries.append(kmod_rust_library)
    kmod_library_index = len(libraries) - 1
    libraries.append(procps_rust_library)
    procps_library_index = len(libraries) - 1
    libraries.append(shadow_rust_library)
    shadow_library_index = len(libraries) - 1
    source_library_hashes = {str(path.relative_to(repository)): sha256(path) for path in libraries}
    source_library_hashes[str(m4_support_library)] = sha256(m4_support_library)
    source_library_hashes[str(gzip_support_library)] = sha256(gzip_support_library)
    source_library_hashes.update(
        {str(path.relative_to(repository)): sha256(path) for path in tar_residue_objects}
    )
    source_library_hashes.update(
        {str(path.relative_to(repository)): sha256(path) for path in findutils_residue_objects}
    )
    source_library_hashes.update(
        {str(path.relative_to(repository)): sha256(path) for path in bison_residue_objects}
    )
    source_library_hashes.update(
        {str(path.relative_to(repository)): sha256(path) for path in curl_residue_objects}
    )
    source_library_hashes[str(inetutils_telnet_boundary)] = sha256(inetutils_telnet_boundary)
    # Bind receipts to the same archive digests recorded in the release manifest.
    inline_proofs.update(verified_cargo_inline_proofs(
        repository, "e2fsprogs", (p for n, p in e2fsprogs_libraries.items() if n not in checksum_consumers),
        source_library_hashes,
    ))
    inline_proofs.update(verified_cargo_inline_proofs(
        repository, "iproute2", (p for n, p in iproute2_libraries.items() if n != "bridge"), source_library_hashes,
    ))
    inline_proofs.update(verified_cargo_inline_proofs(
        repository, "inetutils", inetutils_libraries.values(), source_library_hashes
    ))
    for option, (package, _) in release_archives(repository / "batches/multicall-inline-archives.args").items():
        archive = getattr(args, option.replace("-", "_") + "_rust_library").resolve()
        inline_proofs.update(verified_cargo_inline_proofs(repository, package, [archive], source_library_hashes))
    inline_proofs[str(bridge_archive.relative_to(repository))] = bridge_inline_proof
    second_inline_proofs = linked_layers(repository, inline_proofs, source_library_hashes)
    foreign_proofs = prepare_foreign_declarations(repository, source_library_hashes, inline_proofs, second_inline_proofs)
    dirhash_arrays = {}
    if args.e2fsprogs_dirhash_arrays:
        control = {
            "source_library_sha256": source_library_hashes.copy(),
            "linked_private_inline_proofs": inline_proofs,
            "linked_second_inline_proofs": second_inline_proofs,
            "linked_foreign_declaration_proofs": foreign_proofs,
        }
        dirhash_arrays = prepare_dirhash(control, args.e2fsprogs_dirhash_arrays, repository)
        shared_symbols = {BITCOUNT_SYMBOL, *CRC_SYMBOLS.values()}
        for key, record in dirhash_arrays.items():
            base = Path(key)
            name = base.parent.name
            relative = array_archive(base, record["candidate_sha256"])
            candidate_archive = repository / relative
            original = e2fsprogs_libraries[name]
            shared_references = undefined_symbols(original) & shared_symbols
            if (c_exports(candidate_archive) != c_exports(original)
                    or undefined_symbols(candidate_archive) & shared_symbols != shared_references):
                raise RuntimeError(f"E2fsprogs directory hash changed the C interface of {name}")
            e2fsprogs_libraries[name] = candidate_archive
            libraries[e2fsprogs_library_indices[name]] = candidate_archive
            del source_library_hashes[key]
            source_library_hashes[str(relative)] = record["candidate_sha256"]
    address_record = address_protocols.pinned(repository) if args.iproute2_address_protocols else None
    address_copies = address_protocols.pinned_copies(repository) if args.iproute2_address_protocol_copies else {}
    if address_copies and not address_record:
        raise ValueError("the IPRoute2 address-protocol batch requires the ip archive")
    selected_addresses = ([address_record] if address_record else []) + list(address_copies.values())
    for record in selected_addresses:
        address_control = {
            "source_library_sha256": source_library_hashes, "linked_private_inline_proofs": inline_proofs,
            "linked_second_inline_proofs": second_inline_proofs, "linked_foreign_declaration_proofs": foreign_proofs,
        }
        address_protocols.validate_control(address_control, record)
        relative = address_protocols.candidate_path(record)
        candidate = repository / relative
        original = Path(record["archive"])
        name = "bridge" if original == address_protocols.BRIDGE else original.parent.parent.name
        if name == "bridge":
            address_protocols.prepare_bridge_for_link(address_control, record, repository)
        parent = iproute2_libraries[name]
        if (parent.relative_to(repository) != original or sha256(candidate) != record["candidate_sha256"]
                or c_exports(candidate) != c_exports(parent)):
            raise RuntimeError(f"IPRoute2 {name} archive or its C exports differ from the verified conversion")
        del source_library_hashes[str(original)]
        source_library_hashes[str(relative)] = record["candidate_sha256"]
        iproute2_libraries[name] = libraries[iproute2_library_indices[name]] = candidate
    cargo_changes = {}
    archive_parent = {"source_library_sha256": source_library_hashes, "linked_private_inline_proofs": inline_proofs,
                      "linked_second_inline_proofs": second_inline_proofs, "linked_foreign_declaration_proofs": foreign_proofs}
    for enabled, selection, index in ((args.curl_manual, curl_manual_archive.selection, curl_library_index),
                                      (args.tar_borrowed_timestamps, tar_timestamps, tar_library_index),
                                      (args.bison_literal_lengths, bison_lengths, bison_library_index)):
        if not enabled:
            continue
        record = selection.pinned()
        selection.validate_parent(archive_parent, record)
        row = record["pilot"]
        relative = selection.candidate_path(row)
        candidate = repository / relative
        if (libraries[index] != repository / row["archive"] or sha256(candidate) != row["candidate_sha256"]
                or c_exports(candidate) != c_exports(libraries[index])):
            raise ValueError(f"{selection.field} archive or exported C interface differs")
        del source_library_hashes[row["archive"]]
        source_library_hashes[str(relative)] = row["candidate_sha256"]
        libraries[index] = candidate
        cargo_changes[selection.field] = record
    parent_link = {"iproute2_address_protocols": address_record, "iproute2_address_protocol_copies": address_copies}
    route_selections = {}
    for field, enabled, archive_path in (
        ("iproute2_route_names", args.iproute2_route_names, route_names.candidate_path),
        ("iproute2_netlink_protocols", args.iproute2_netlink_protocols, route_names.netlink_path),
    ):
        if not enabled:
            continue
        netlink = field == "iproute2_netlink_protocols"
        rows = route_names.verified_records(parent_link, route_names.manifest(netlink=netlink), netlink=netlink)
        parent_link[field] = route_selections[field] = rows
        for key, record in rows.items():
            name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
            old = iproute2_libraries[name]
            if name == "bridge":
                route_names.prepare(record, mounted_bridge=True, netlink=netlink)
            relative = archive_path(record)
            candidate = repository / relative
            if (source_library_hashes[str(old.relative_to(repository))] != record["control_sha256"]
                    or sha256(candidate) != record["candidate_sha256"] or c_exports(candidate) != c_exports(old)):
                raise ValueError(f"scope/realm archive or its C exports differ for {name}")
            del source_library_hashes[str(old.relative_to(repository))]
            source_library_hashes[str(relative)] = record["candidate_sha256"]
            iproute2_libraries[name] = libraries[iproute2_library_indices[name]] = candidate
    proofs = {"linked_private_inline_proofs": inline_proofs, "linked_second_inline_proofs": second_inline_proofs,
              "linked_foreign_declaration_proofs": foreign_proofs}
    identical_layers = {}
    for manifest, layer in ((args.shared_stdio, "shared_stdio_layouts"), (args.native_c_strings, "native_c_strings"),
                            (args.iproute2_routing_protocols, routing_protocols.FIELD),
                            (args.lz4_benchmark_dictionary, lz4_dictionary_archive.selection.field),
                            (args.va_list_layouts, "shared_va_list_layouts"), (args.ncurses_termtypes, "shared_ncurses_termtypes")):
        if manifest and layer == routing_protocols.FIELD:
            context = dict(source_library_sha256=source_library_hashes, **identical_layers)
            resolved = routing_protocols.select(context)
            rows = resolved[layer]
            for name, old in iproute2_libraries.items():
                row = rows[str(old.relative_to(repository))]
                new = repository / routing_protocols.candidate_path(row)
                if sha256(new) != row["candidate_sha256"] or c_exports(new) != c_exports(old):
                    raise ValueError(f"routing protocol archive or C exports differ for {name}")
                iproute2_libraries[name] = libraries[iproute2_library_indices[name]] = new
            source_library_hashes = resolved["source_library_sha256"]
            route_selections[layer] = rows
        elif manifest and layer == lz4_dictionary_archive.selection.field:
            context = dict(source_library_sha256=source_library_hashes, **proofs, **identical_layers)
            resolved = lz4_dictionary_archive.selected_link(context)
            record = resolved[layer]
            row = record["pilot"]
            candidate = repository / lz4_dictionary_archive.selection.candidate_path(row)
            original = libraries[lz4_library_index]
            if (original != repository / row["archive"] or sha256(candidate) != row["candidate_sha256"]
                    or c_exports(candidate) != c_exports(original)):
                raise ValueError("packed LZ4 dictionary archive or exported C interface differs")
            libraries[lz4_library_index] = candidate
            source_library_hashes = resolved["source_library_sha256"]
            cargo_changes[layer] = record
        elif manifest:
            items = json.loads(manifest.read_bytes())
            if layer in ("native_c_strings", "shared_va_list_layouts"):
                # Direct-rustc parents are materialized in this Linux process.
                direct = {k: item for k, item in items.items() if "rustc_archive" in item["pilot"]}
                prepare_identical_archives.prepare(direct, layer, mounted_direct=True)
            context = {**proofs, **identical_layers, **route_selections,
                       "e2fsprogs_dirhash_arrays": dirhash_arrays, **cargo_changes}
            identical_layers[layer] = prepare_identical_archives.validate_link(items, source_library_hashes, context, layer)
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
        "rustbox_gawk_main",
        "rustbox_gawkbug_main",
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
        "rustbox_xz_main",
        "rustbox_xzdec_main",
        "rustbox_lzmadec_main",
        "rustbox_lzmainfo_main",
        "rustbox_xzdiff_main",
        "rustbox_xzgrep_main",
        "rustbox_xzless_main",
        "rustbox_xzmore_main",
        "rustbox_zstd_main",
        "rustbox_zstdgrep_main",
        "rustbox_zstdless_main",
        "rustbox_tar_main",
        "rustbox_rmt_main",
        "rustbox_clear_main",
        "rustbox_infocmp_main",
        "rustbox_tabs_main",
        "rustbox_tic_main",
        "rustbox_toe_main",
        "rustbox_tput_main",
        "rustbox_tset_main",
        "rustbox_ncursesw6_config_main",
        "rustbox_find_main",
        "rustbox_xargs_main",
        "rustbox_locate_main",
        "rustbox_frcode_main",
        "rustbox_updatedb_main",
        "rustbox_flex_main",
        "rustbox_flexpp_main",
        "rustbox_lex_main",
        "rustbox_bison_main",
        "rustbox_yacc_main",
        "rustbox_curl_main",
        "rustbox_curl_config_main",
        "rustbox_kmod_main",
    })
    expected_symbols.update(
        f"rustbox_procps_{name}_main" for name in set(PROCPS_ENTRYPOINT.values())
    )
    expected_symbols.update(
        f"rustbox_shadow_{name}_main" for name in set(SHADOW_ENTRYPOINT.values())
    )
    expected_symbols.update(
        f"rustbox_inetutils_{name}_main" for name in INETUTILS_PROGRAMS
    )
    expected_symbols.update(
        f"rustbox_iproute2_{name}_main" for name in IPROUTE2_PROGRAMS
    )
    expected_symbols.add("rustbox_iproute2_routel_main")
    expected_symbols.update(
        f"rustbox_e2fsprogs_{name}_main"
        for name in (*E2FSPROGS_PROGRAMS, *E2FSPROGS_FRONTENDS)
    )

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
        mapped_gawk_rust = build / "src/.rustbox-gawk" / libraries[gawk_library_index].name
        gawk_symbols = cached_report["gawk_namespaced_symbols"]
    else:
        mapped_gawk_rust, gawk_symbols = namespace_gawk_library(
            libraries[gawk_library_index], build
        )
    libraries[gawk_library_index] = mapped_gawk_rust

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
        mapped_tar_rust = build / "src/.rustbox-tar" / libraries[tar_library_index].name
        mapped_tar_residue = [
            build / "src/.rustbox-tar" / path.name for path in tar_residue_objects
        ]
        tar_symbols = cached_report["tar_namespaced_symbols"]
        tar_acl_imports = cached_report["tar_acl_imports"]
    else:
        mapped_tar_rust, mapped_tar_residue, tar_symbols, tar_acl_imports = namespace_tar_inputs(
            libraries[tar_library_index], tar_residue_objects, acl_symbols, build
        )
    libraries[tar_library_index] = mapped_tar_rust

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
        gzip_runtime_members = cached_report["gzip_coalesced_runtime_members"]
        gzip_runtime_member_bytes = cached_report[
            "gzip_coalesced_runtime_member_bytes"
        ]
    else:
        (
            coalesced_gzip_rust,
            gzip_runtime_members,
            gzip_runtime_member_bytes,
        ) = coalesce_identical_archive_members(
            coreutils_runtime_provider,
            libraries[gzip_library_index],
            build / "src/.rustbox-gzip-runtime",
            "Gzip/Coreutils pinned stable Rust runtime",
        )
        mapped_gzip_rust, mapped_gzip_support, gzip_symbols = namespace_gzip_libraries(
            coalesced_gzip_rust, gzip_support_library, build
        )
    if (
        len(gzip_runtime_members) != 328
        or gzip_runtime_member_bytes != 23087912
    ):
        raise RuntimeError(
            "Gzip/Coreutils pinned runtime overlap changed: "
            f"{len(gzip_runtime_members)} members/{gzip_runtime_member_bytes} bytes"
        )
    if "rust_eh_personality" in gzip_symbols:
        raise RuntimeError("Gzip namespace mapping retained a removed runtime definition")
    libraries[gzip_library_index] = mapped_gzip_rust

    if cached_report:
        mapped_xz_rust = build / "src/.rustbox-xz" / libraries[xz_library_index].name
        xz_symbols = cached_report["xz_namespaced_symbols"]
    else:
        mapped_xz_rust, xz_symbols = namespace_xz_library(
            libraries[xz_library_index], build
        )
    libraries[xz_library_index] = mapped_xz_rust

    if cached_report:
        mapped_zstd_rust = build / "src/.rustbox-zstd" / libraries[zstd_library_index].name
        zstd_symbols = cached_report["zstd_namespaced_symbols"]
    else:
        mapped_zstd_rust, zstd_symbols = namespace_zstd_library(
            libraries[zstd_library_index], build
        )
    libraries[zstd_library_index] = mapped_zstd_rust

    if cached_report:
        mapped_ncurses_rust = build / "src/.rustbox-ncurses" / libraries[ncurses_library_index].name
        ncurses_symbols = cached_report["ncurses_namespaced_symbols"]
    else:
        mapped_ncurses_rust, ncurses_symbols = namespace_ncurses_library(
            libraries[ncurses_library_index], build
        )
    libraries[ncurses_library_index] = mapped_ncurses_rust

    if cached_report:
        mapped_findutils_rust = (
            build / "src/.rustbox-findutils" / libraries[findutils_library_index].name
        )
        mapped_findutils_residue = [
            build / "src/.rustbox-findutils" / path.name
            for path in findutils_residue_objects
        ]
        findutils_symbols = cached_report["findutils_namespaced_symbols"]
    else:
        (
            mapped_findutils_rust,
            mapped_findutils_residue,
            findutils_symbols,
        ) = namespace_findutils_inputs(
            libraries[findutils_library_index], findutils_residue_objects, build
        )
    libraries[findutils_library_index] = mapped_findutils_rust

    if cached_report:
        mapped_flex_rust = build / "src/.rustbox-flex" / libraries[flex_library_index].name
        flex_symbols = cached_report["flex_namespaced_symbols"]
    else:
        mapped_flex_rust, flex_symbols = namespace_flex_library(
            libraries[flex_library_index], build
        )
    libraries[flex_library_index] = mapped_flex_rust

    if cached_report:
        mapped_bison_rust = build / "src/.rustbox-bison" / libraries[bison_library_index].name
        mapped_bison_residue = [
            build / "src/.rustbox-bison" / path.name for path in bison_residue_objects
        ]
        bison_symbols = cached_report["bison_namespaced_symbols"]
    else:
        mapped_bison_rust, mapped_bison_residue, bison_symbols = namespace_bison_inputs(
            libraries[bison_library_index], bison_residue_objects, build
        )
    libraries[bison_library_index] = mapped_bison_rust

    if cached_report:
        mapped_curl_rust = build / "src/.rustbox-curl" / libraries[curl_library_index].name
        mapped_curl_residue = [
            build / "src/.rustbox-curl" / path.name for path in curl_residue_objects
        ]
        curl_symbols = cached_report["curl_namespaced_symbols"]
    else:
        mapped_curl_rust, mapped_curl_residue, curl_symbols = namespace_curl_inputs(
            libraries[curl_library_index], curl_residue_objects, build
        )
    libraries[curl_library_index] = mapped_curl_rust

    if cached_report:
        mapped_inetutils = {
            name: build / "src/.rustbox-inetutils" / name / inetutils_libraries[name].name
            for name in INETUTILS_PROGRAMS
        }
        mapped_inetutils_boundary = (
            build / "src/.rustbox-inetutils/telnet" / inetutils_telnet_boundary.name
        )
        inetutils_symbols = cached_report["inetutils_namespaced_symbols"]
    else:
        mapped_inetutils, mapped_inetutils_boundary, inetutils_symbols = (
            namespace_inetutils_programs(
                inetutils_libraries, inetutils_telnet_boundary, build
            )
        )
    for name, index in inetutils_library_indices.items():
        libraries[index] = mapped_inetutils[name]

    if cached_report:
        mapped_iproute2 = {
            name: build / "src/.rustbox-iproute2" / name / iproute2_libraries[name].name
            for name in IPROUTE2_PROGRAMS
        }
        iproute2_symbols = cached_report["iproute2_namespaced_symbols"]
    else:
        mapped_iproute2, iproute2_symbols = namespace_iproute2_programs(
            iproute2_libraries, build
        )
    for name, index in iproute2_library_indices.items():
        libraries[index] = mapped_iproute2[name]

    if cached_report:
        mapped_e2fsprogs = {
            name: build / "src/.rustbox-e2fsprogs" / name / e2fsprogs_libraries[name].name
            for name in E2FSPROGS_PROGRAMS
        }
        e2fsprogs_symbols = cached_report["e2fsprogs_namespaced_symbols"]
        e2fsprogs_runtime_members = cached_report[
            "e2fsprogs_coalesced_runtime_members"
        ]
    else:
        coalesced_e2fsprogs = {}
        e2fsprogs_runtime_members = {}

        def coalesce_e2fsprogs(
            name: str,
        ) -> tuple[str, Path, list[str]]:
            coalesced, runtime_members, _ = coalesce_identical_archive_members(
                procps_rust_library,
                e2fsprogs_libraries[name],
                build / "src/.rustbox-e2fsprogs-runtime" / name,
                f"E2fsprogs {name}/Procps pinned Rust runtime",
            )
            return name, coalesced, runtime_members

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            coalesced_results = list(
                executor.map(coalesce_e2fsprogs, E2FSPROGS_PROGRAMS)
            )
        for name, coalesced, runtime_members in coalesced_results:
            coalesced_e2fsprogs[name] = coalesced
            e2fsprogs_runtime_members[name] = runtime_members
        mapped_e2fsprogs, e2fsprogs_symbols = namespace_e2fsprogs_programs(
            coalesced_e2fsprogs, build
        )
    for name, index in e2fsprogs_library_indices.items():
        libraries[index] = mapped_e2fsprogs[name]
    e2fsprogs_runtime_member_counts = {
        name: len(members)
        for name, members in e2fsprogs_runtime_members.items()
    }
    if e2fsprogs_runtime_member_counts != E2FSPROGS_RUNTIME_MEMBER_COUNTS:
        raise RuntimeError("E2fsprogs/Procps pinned runtime overlap changed")

    if cached_report:
        mapped_kmod_rust = build / "src/.rustbox-kmod" / libraries[kmod_library_index].name
        kmod_symbols = cached_report["kmod_namespaced_symbols"]
    else:
        mapped_kmod_rust, kmod_symbols = namespace_kmod_library(
            libraries[kmod_library_index], build
        )
    libraries[kmod_library_index] = mapped_kmod_rust

    if cached_report:
        mapped_procps_rust = (
            build / "src/.rustbox-procps" / libraries[procps_library_index].name
        )
        procps_symbols = cached_report["procps_namespaced_symbols"]
    else:
        mapped_procps_rust, procps_symbols = namespace_procps_library(
            libraries[procps_library_index], build
        )
    libraries[procps_library_index] = mapped_procps_rust

    if cached_report:
        mapped_shadow_rust = (
            build / "src/.rustbox-shadow" / libraries[shadow_library_index].name
        )
        shadow_symbols = cached_report["shadow_namespaced_symbols"]
        shadow_runtime_members = cached_report["shadow_coalesced_runtime_members"]
    else:
        (
            coalesced_shadow_rust,
            shadow_runtime_members,
            _,
        ) = coalesce_identical_archive_members(
            procps_rust_library,
            shadow_rust_library,
            build / "src/.rustbox-shadow-runtime",
            "Shadow/Procps pinned Rust runtime",
        )
        mapped_shadow_rust, shadow_symbols = namespace_shadow_library(
            coalesced_shadow_rust, build
        )
    libraries[shadow_library_index] = mapped_shadow_rust
    if len(shadow_runtime_members) != 211:
        raise RuntimeError(
            f"Shadow/Procps pinned runtime overlap changed: {len(shadow_runtime_members)}"
        )

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
    if coreutils_runtime_provider.name in namespaced_symbols:
        raise RuntimeError("Coreutils Rust runtime provider unexpectedly needs isolation")
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

    cached_paths = [
        *libraries, *mapped_tar_residue, *mapped_findutils_residue, *mapped_bison_residue,
        *mapped_curl_residue,
        mapped_inetutils_boundary,
        mapped_m4_support, mapped_gzip_support, *util_inputs,
    ]
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
    gawkbug_object = build / "src/.rustbox-gawkbug.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-c", str(repository / "bridges/gawkbug.c"), "-o", str(gawkbug_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(gawkbug_object) != ["rustbox_gawkbug_main"]:
        raise RuntimeError("GNU Gawk bug-report frontend exports the wrong symbols")
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
    xz_aliases_object = build / "src/.rustbox-xz-aliases.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/xz_aliases.c"),
         "-o", str(xz_aliases_object)],
        cwd=build,
        check=True,
    )
    if set(defined_symbols(xz_aliases_object)) != {
        "rustbox_xzdiff_main", "rustbox_xzgrep_main",
        "rustbox_xzless_main", "rustbox_xzmore_main",
    }:
        raise RuntimeError("XZ alias bridge exports the wrong symbols")
    zstd_aliases_object = build / "src/.rustbox-zstd-aliases.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c", str(repository / "bridges/zstd_aliases.c"),
         "-o", str(zstd_aliases_object)],
        cwd=build,
        check=True,
    )
    if set(defined_symbols(zstd_aliases_object)) != {
        "rustbox_zstdgrep_main", "rustbox_zstdless_main",
    }:
        raise RuntimeError("zstd alias bridge exports the wrong symbols")
    findutils_updatedb_object = build / "src/.rustbox-findutils-updatedb.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-c",
         str(repository / "bridges/findutils_updatedb.c"),
         "-o", str(findutils_updatedb_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(findutils_updatedb_object) != ["rustbox_updatedb_main"]:
        raise RuntimeError("GNU Findutils updatedb bridge exports the wrong symbols")
    flex_frontends_object = build / "src/.rustbox-flex-frontends.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-DRUSTBOX_MULTICALL", "-c", str(repository / "bridges/flex_main.c"),
         "-o", str(flex_frontends_object)],
        cwd=build,
        check=True,
    )
    if set(defined_symbols(flex_frontends_object)) != {
        "rustbox_flexpp_main", "rustbox_lex_main",
    }:
        raise RuntimeError("Flex compatibility bridge exports the wrong symbols")
    bison_embedded = repository / "work/analysis/bison-3.8.2/embedded"
    bison_resource_source = bison_embedded / "bison-resources.c"
    bison_resource_manifest = bison_embedded / "manifest.json"
    subprocess.run(
        [
            "python3", str(repository / "scripts/generate_bison_resources.py"),
            "--datadir", str(repository / "work/analysis/bison-3.8.2/normalized/clang-root/usr/share/bison"),
            "--oracle-evidence", str(repository / "evidence/bison-3.8.2-oracle.json"),
            "--output", str(bison_resource_source),
            "--manifest", str(bison_resource_manifest),
        ],
        check=True,
    )
    bison_resource_object = build / "src/.rustbox-bison-resources.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-c", str(bison_resource_source), "-o", str(bison_resource_object)],
        cwd=build, check=True,
    )
    if set(defined_symbols(bison_resource_object)) != {
        "rustbox_bison_resources_create",
        "rustbox_bison_resources_create_persistent",
        "rustbox_bison_resources_remove",
    }:
        raise RuntimeError("Bison embedded resource unit exports the wrong symbols")
    bison_frontends_object = build / "src/.rustbox-bison-frontends.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-D_GNU_SOURCE", "-DRUSTBOX_EMBEDDED", "-DRUSTBOX_MULTICALL", "-c",
         str(repository / "bridges/bison_main.c"), "-o", str(bison_frontends_object)],
        cwd=build, check=True,
    )
    if set(defined_symbols(bison_frontends_object)) != {
        "rustbox_bison_main", "rustbox_yacc_main",
    }:
        raise RuntimeError("Bison embedded frontend bridge exports the wrong symbols")
    curl_config_object = build / "src/.rustbox-curl-config.o"
    subprocess.run(
        ["clang-18", "-O2", "-g", "-DRUSTBOX_MULTICALL", "-c",
         str(repository / "bridges/curl_config.c"), "-o", str(curl_config_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(curl_config_object) != ["rustbox_curl_config_main"]:
        raise RuntimeError("curl-config frontend bridge exports the wrong symbols")
    ncurses_config_object = build / "src/.rustbox-ncursesw6-config.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-DRUSTBOX_MULTICALL", "-c",
         str(repository / "bridges/ncursesw6_config.c"),
         "-o", str(ncurses_config_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(ncurses_config_object) != ["rustbox_ncursesw6_config_main"]:
        raise RuntimeError("ncursesw6-config frontend bridge exports the wrong symbols")
    iproute2_routel_object = build / "src/.rustbox-iproute2-routel.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-D_GNU_SOURCE", "-DRUSTBOX_MULTICALL", "-c",
         str(repository / "bridges/iproute2_routel.c"),
         "-o", str(iproute2_routel_object)],
        cwd=build,
        check=True,
    )
    if defined_symbols(iproute2_routel_object) != ["rustbox_iproute2_routel_main"]:
        raise RuntimeError("IPRoute2 routel frontend bridge exports the wrong symbols")
    e2fsprogs_templates_source = build / "src/.rustbox-e2fsprogs-templates.c"
    subprocess.run(
        ["python3", str(repository / "scripts/generate_e2fsprogs_script_templates.py"),
         "--source", str(repository / "work/upstream/e2fsprogs-1.47.4"),
         "--output", str(e2fsprogs_templates_source)],
        check=True,
    )
    e2fsprogs_frontends_object = build / "src/.rustbox-e2fsprogs-frontends.o"
    e2fsprogs_templates_object = build / "src/.rustbox-e2fsprogs-templates.o"
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-D_GNU_SOURCE", "-DRUSTBOX_MULTICALL", "-c",
         str(repository / "bridges/e2fsprogs_script_frontends.c"),
         "-o", str(e2fsprogs_frontends_object)],
        cwd=build,
        check=True,
    )
    subprocess.run(
        ["clang-18", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-g",
         "-c", str(e2fsprogs_templates_source),
         "-o", str(e2fsprogs_templates_object)],
        cwd=build,
        check=True,
    )
    if set(defined_symbols(e2fsprogs_frontends_object)) != {
        f"rustbox_e2fsprogs_{name}_main" for name in E2FSPROGS_FRONTENDS
    }:
        raise RuntimeError("E2fsprogs script frontend bridge exports the wrong symbols")
    if set(defined_symbols(e2fsprogs_templates_object)) != {
        "rustbox_e2fs_et_h_awk", "rustbox_e2fs_et_h_awk_len",
        "rustbox_e2fs_et_c_awk", "rustbox_e2fs_et_c_awk_len",
        "rustbox_e2fs_ct_c_sed", "rustbox_e2fs_ct_c_sed_len",
        "rustbox_e2fs_ct_c_awk", "rustbox_e2fs_ct_c_awk_len",
    }:
        raise RuntimeError("E2fsprogs embedded template object exports the wrong symbols")
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
    coreutils_acl_imports = sorted(
        (undefined_symbols(canonical_coreutils) & set(acl_symbols))
        - set(defined_symbols(canonical_coreutils))
    )
    if not coreutils_acl_imports:
        raise RuntimeError("canonical Coreutils exposes no translated ACL imports")
    coreutils_acl_map = build / "lib/.rustbox-coreutils-acl.map"
    coreutils_acl_map.write_text(
        "".join(
            f"{symbol} rustbox_acl_private_{symbol}\n"
            for symbol in coreutils_acl_imports
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ["objcopy", "--redefine-syms", str(coreutils_acl_map), str(namespaced_coreutils)],
        check=True,
    )
    rebound_coreutils_undefined = undefined_symbols(namespaced_coreutils)
    if set(coreutils_acl_imports) & rebound_coreutils_undefined:
        raise RuntimeError("Coreutils retained unbound system libacl imports")
    if any(
        f"rustbox_acl_private_{symbol}" not in rebound_coreutils_undefined
        for symbol in coreutils_acl_imports
    ):
        raise RuntimeError("Coreutils lost a translated libacl import")

    dependencies = make_assignment(makefile, "single_binary_deps").split()
    for archive in removed:
        if dependencies.count(archive) != 1:
            raise RuntimeError(f"expected one canonical applet archive: {archive}")
    rewritten: list[str] = []
    inserted = False
    for dependency in dependencies:
        if dependency in removed:
            if not inserted:
                # The public bridge introduces the first reference to the
                # private engine entrypoint, so it must precede Bison's static
                # archive for the linker to extract that member.
                rewritten.append(str(bison_frontends_object))
                rewritten.extend(str(path) for path in libraries)
                # Gzip's byte-identical stable runtime members are coalesced
                # into Coreutils batch 01.  Repeat only the provider archive
                # after Gzip so normal extraction can satisfy late imports.
                rewritten.append(str(coreutils_runtime_provider))
                # Shadow's byte-identical nightly runtime members are
                # coalesced into Procps.  Repeat that provider after Shadow so
                # normal archive extraction can satisfy late runtime imports.
                rewritten.append(str(mapped_procps_rust))
                rewritten.extend(str(path) for path in mapped_tar_residue)
                rewritten.extend(str(path) for path in mapped_findutils_residue)
                rewritten.extend(str(path) for path in mapped_bison_residue)
                rewritten.extend(str(path) for path in mapped_curl_residue)
                rewritten.append(str(mapped_inetutils_boundary))
                rewritten.extend(str(path) for path in typed_bridge_objects)
                rewritten.append(str(sed_abi_object))
                rewritten.append(str(diffutils_error_object))
                rewritten.append(str(grep_abi_object))
                rewritten.append(str(grep_error_object))
                rewritten.append(str(gawkbug_object))
                rewritten.append(str(gzip_aliases_object))
                rewritten.append(str(xz_aliases_object))
                rewritten.append(str(zstd_aliases_object))
                rewritten.append(str(findutils_updatedb_object))
                rewritten.append(str(flex_frontends_object))
                rewritten.append(str(bison_resource_object))
                rewritten.append(str(curl_config_object))
                rewritten.append(str(ncurses_config_object))
                rewritten.append(str(iproute2_routel_object))
                rewritten.append(str(e2fsprogs_frontends_object))
                rewritten.append(str(e2fsprogs_templates_object))
                rewritten.extend(str(path) for path in util_inputs)
                rewritten.append(str(mapped_m4_support))
                rewritten.append(str(mapped_gzip_support))
                inserted = True
            if dependency in bridge_archives:
                rewritten.append(str(bridge_archives[dependency]))
        elif dependency == "-lacl":
            continue
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
        "-lbz2 -llz -llzma -lseccomp -lz -lzstd -lattr -lpcre2-8 "
        "-lreadline -lncurses -lncursesw -lcrypt -lcrypto -lmpfr -lgmp "
        "-ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables "
        "-lblkid -luuid -lfuse3 -larchive",
        "src_coreutils_LDADD=$(single_binary_deps) "
        "$(filter-out -lacl,$(LDADD) $(single_binary_libs)) "
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
    dynamic = subprocess.run(
        ["readelf", "-d", str(output)],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout
    dynamic_needed = sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic)))
    if any(name.startswith("libacl.so") for name in dynamic_needed):
        raise RuntimeError("combined Rustbox still depends on system libacl")
    symbols = defined_symbols(output)
    if symbols.count(BITCOUNT_SYMBOL) != 1 or any(s.endswith("_private_ext2fs_bitcount") for s in symbols):
        raise RuntimeError("expected exactly one shared bitmap counter")
    if any(symbols.count(name) != 1 for name in CRC_SYMBOLS.values()):
        raise RuntimeError("expected one provider for each E2fsprogs checksum")
    if any(symbol.endswith(f"_private_{name}") for symbol in symbols for name in CRC_SYMBOLS):
        raise RuntimeError("per-engine E2fsprogs checksum still linked")
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
        "gawk_public_names": 3,
        "bc_applets": 2,
        "attr_applets": 3,
        "acl_applets": 3,
        "lz4_public_names": 4,
        "less_public_names": 2,
        "gzip_public_names": 14,
        "xz_public_names": 23,
        "zstd_public_names": 6,
        "tar_applets": 2,
        "ncurses_public_names": 11,
        "findutils_public_names": 4,
        "flex_public_names": 3,
        "bison_public_names": 2,
        "curl_public_names": 2,
        "inetutils_programs": 26,
        "iproute2_public_names": 21,
        "e2fsprogs_public_names": 32,
        "kmod_programs": 7,
        "procps_programs": 20,
        "shadow_programs": 32,
        "total_dispatch_names": len(
            set(applets)
            | set(util_dispatch)
            | {"m4", "pkgconf", "pkg-config", "bomtool", "pccritic", "spdxtool", "file", "patch", "sed",
               "cmp", "diff", "diff3", "sdiff", "grep", "egrep", "fgrep", "gawk", "awk", "gawkbug", "bc", "dc",
               "attr", "getfattr", "setfattr", "chacl", "getfacl", "setfacl",
               "lz4", "lz4c", "lz4cat", "unlz4", "less", "lessecho",
               "gzip", "gunzip", "zcat", "uncompress",
               "zcmp", "zdiff", "zforce", "zgrep", "zegrep", "zfgrep", "zless",
               "zmore", "znew", "gzexe",
               "xz", "unxz", "xzcat", "lzma", "unlzma", "lzcat", "xzdec",
               "lzmadec", "lzmainfo", "xzdiff", "xzcmp", "xzegrep", "xzfgrep",
               "xzgrep", "xzless", "xzmore", "lzdiff", "lzcmp", "lzgrep",
               "lzegrep", "lzfgrep", "lzmore", "lzless",
               "zstd", "zstdmt", "unzstd", "zstdcat", "zstdgrep", "zstdless",
               "tar", "rmt", "captoinfo", "clear", "infocmp", "infotocap",
               "reset", "tabs", "tic", "toe", "tput", "tset", "ncursesw6-config",
               "find", "xargs", "locate", "updatedb", "flex", "flex++", "lex",
               "bison", "yacc", "curl", "curl-config",
               "kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod",
               *({f"procps-{name}" if name in {"kill", "uptime"} else name
                  for name in PROCPS_PROGRAMS}),
               *({f"shadow-{name}" if name in SHADOW_COLLISIONS else name
                  for name in SHADOW_PROGRAMS}),
               *({name for name in INETUTILS_PROGRAMS if name not in {"hostname", "logger"}}),
               "inetutils-hostname", "inetutils-logger", *IPROUTE2_PUBLIC_NAMES,
               *E2FSPROGS_PUBLIC_NAMES}
        ),
        "excluded": ["chcon", "runcon"],
        "public_name_precedence": {
            "kill": "GNU Coreutils",
            "util-linux-kill": "util-linux",
            "procps-kill": "Procps-ng",
            "uptime": "GNU Coreutils",
            "procps-uptime": "Procps-ng",
            "fsck": "util-linux",
            "e2fsprogs-fsck": "E2fsprogs",
            **{name: "util-linux" for name in sorted(SHADOW_COLLISIONS)},
            **{f"shadow-{name}": "Shadow" for name in sorted(SHADOW_COLLISIONS)},
        },
        "namespaced_canonical_symbols": {
            "lib/libcoreutils.a": {
                "crc32": "rustbox_coreutils_gnulib_crc32",
                "reason": "isolate zlib's incompatible crc32 ABI used by mkfs.cramfs",
            }
        },
        "source_library_sha256": source_library_hashes,
        **route_selections,
        **identical_layers,
        **cargo_changes,
        **({"iproute2_address_protocol_copies": address_copies} if address_copies else {}),
        **({"iproute2_address_protocols": address_record} if address_record else {}),
        **({"e2fsprogs_dirhash_arrays": dirhash_arrays} if dirhash_arrays else {}),
        "bridge_raw_pointer_types": bridge_raw_types,
        "linked_private_inline_proofs": inline_proofs,
        **({"linked_second_inline_proofs": second_inline_proofs} if second_inline_proofs else {}),
        **({"linked_foreign_declaration_proofs": foreign_proofs} if foreign_proofs else {}),
        "e2fsprogs_shared_checksums": {
            "symbols": sorted(CRC_SYMBOLS.values()), "consumers": sorted(checksum_consumers),
            "object_sha256": {o.name: sha256(o) for o in checksum_objects if o.name != "bitcount.o"},
        },
        "e2fsprogs_shared_bitcount": {
            "symbol": BITCOUNT_SYMBOL, "callers": sorted(bitmap_callers),
            "object_sha256": sha256(next(o for o in checksum_objects if o.name == "bitcount.o")),
        },
        "namespaced_symbols": namespaced_symbols,
        "namespaced_support_symbols": namespaced_support,
        "m4_namespaced_support_symbols": m4_support_symbols,
        "file_namespaced_symbols": file_symbols,
        "patch_namespaced_symbols": patch_symbols,
        "sed_namespaced_symbols": sed_symbols,
        "diffutils_namespaced_symbols": diffutils_symbols,
        "grep_namespaced_symbols": grep_symbols,
        "gawk_namespaced_symbols": gawk_symbols,
        "bc_namespaced_symbols": bc_symbols,
        "attr_namespaced_symbols": attr_symbols,
        "acl_namespaced_symbols": acl_symbols,
        "lz4_namespaced_symbols": lz4_symbols,
        "less_namespaced_symbols": less_symbols,
        "gzip_namespaced_symbols": gzip_symbols,
        "gzip_coalesced_runtime_members": gzip_runtime_members,
        "gzip_coalesced_runtime_member_count": len(gzip_runtime_members),
        "gzip_coalesced_runtime_member_bytes": gzip_runtime_member_bytes,
        "xz_namespaced_symbols": xz_symbols,
        "zstd_namespaced_symbols": zstd_symbols,
        "tar_namespaced_symbols": tar_symbols,
        "ncurses_namespaced_symbols": ncurses_symbols,
        "findutils_namespaced_symbols": findutils_symbols,
        "flex_namespaced_symbols": flex_symbols,
        "bison_namespaced_symbols": bison_symbols,
        "curl_namespaced_symbols": curl_symbols,
        "inetutils_namespaced_symbols": inetutils_symbols,
        "iproute2_namespaced_symbols": iproute2_symbols,
        "e2fsprogs_namespaced_symbols": e2fsprogs_symbols,
        "e2fsprogs_coalesced_runtime_members": e2fsprogs_runtime_members,
        "e2fsprogs_coalesced_runtime_member_count": sum(
            e2fsprogs_runtime_member_counts.values()
        ),
        "kmod_namespaced_symbols": kmod_symbols,
        "procps_namespaced_symbols": procps_symbols,
        "shadow_namespaced_symbols": shadow_symbols,
        "shadow_coalesced_runtime_members": shadow_runtime_members,
        "tar_acl_imports": tar_acl_imports,
        "coreutils_acl_imports": coreutils_acl_imports,
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
        "gawkbug_bridge": {
            "object": str(gawkbug_object.relative_to(build)),
            "symbols": ["rustbox_gawkbug_main"],
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
        "xz_alias_bridge": {
            "object": str(xz_aliases_object.relative_to(build)),
            "symbols": ["rustbox_xzdiff_main", "rustbox_xzgrep_main",
                        "rustbox_xzless_main", "rustbox_xzmore_main"],
            "public_names": ["xzdiff", "xzcmp", "xzegrep", "xzfgrep", "xzgrep",
                             "xzless", "xzmore", "lzdiff", "lzcmp", "lzgrep",
                             "lzegrep", "lzfgrep", "lzmore", "lzless"],
        },
        "zstd_alias_bridge": {
            "object": str(zstd_aliases_object.relative_to(build)),
            "symbols": ["rustbox_zstdgrep_main", "rustbox_zstdless_main"],
            "public_names": ["zstdgrep", "zstdless"],
        },
        "sed_abi_bridge": {
            "object": str(sed_abi_object.relative_to(build)),
            "symbols": ["__wctob_alias"],
        },
        "findutils_updatedb_bridge": {
            "object": str(findutils_updatedb_object.relative_to(build)),
            "symbols": ["rustbox_updatedb_main"],
            "public_names": ["updatedb"],
        },
        "flex_frontend_bridge": {
            "object": str(flex_frontends_object.relative_to(build)),
            "symbols": ["rustbox_flexpp_main", "rustbox_lex_main"],
            "public_names": ["flex++", "lex"],
        },
        "bison_frontend_bridge": {
            "object": str(bison_frontends_object.relative_to(build)),
            "symbols": ["rustbox_bison_main", "rustbox_yacc_main"],
            "public_names": ["bison", "yacc"],
            "embedded_resource_manifest_sha256": sha256(bison_resource_manifest),
        },
        "curl_config_frontend_bridge": {
            "object": str(curl_config_object.relative_to(build)),
            "symbols": ["rustbox_curl_config_main"],
            "public_names": ["curl-config"],
        },
        "ncurses_config_frontend_bridge": {
            "object": str(ncurses_config_object.relative_to(build)),
            "symbols": ["rustbox_ncursesw6_config_main"],
            "public_names": ["ncursesw6-config"],
        },
        "iproute2_routel_frontend_bridge": {
            "object": str(iproute2_routel_object.relative_to(build)),
            "symbols": ["rustbox_iproute2_routel_main"],
            "public_names": ["routel"],
        },
        "e2fsprogs_script_frontend_bridge": {
            "object": str(e2fsprogs_frontends_object.relative_to(build)),
            "template_object": str(e2fsprogs_templates_object.relative_to(build)),
            "symbols": [
                f"rustbox_e2fsprogs_{name}_main" for name in E2FSPROGS_FRONTENDS
            ],
            "public_names": list(E2FSPROGS_FRONTENDS),
        },
        "binary": {
            "bytes": output.stat().st_size,
            "sha256": sha256(output),
            "link_map_sha256": sha256(link_map),
            "dynamic_needed": dynamic_needed,
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
        "gawk_public_names": 3,
        "bc_applets": 2,
        "attr_applets": 3,
        "acl_applets": 3,
        "lz4_public_names": 4,
        "less_public_names": 2,
        "gzip_public_names": 14,
        "xz_public_names": 23,
        "zstd_public_names": 6,
        "tar_applets": 2,
        "ncurses_public_names": 11,
        "findutils_public_names": 4,
        "flex_public_names": 3,
        "bison_public_names": 2,
        "curl_public_names": 2,
        "inetutils_programs": 26,
        "iproute2_public_names": 21,
        "e2fsprogs_public_names": 32,
        "kmod_programs": 7,
        "procps_programs": 20,
        "shadow_programs": 32,
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
