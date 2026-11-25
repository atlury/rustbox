#!/usr/bin/env python3
"""Relink checked GNU errno users together and compare the public commands in both dispatch modes."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from functools import partial
import json
from pathlib import Path
import shlex
import subprocess

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import (coalesce_identical_archive_members, namespace_grep_library,
                                    namespace_gzip_libraries, namespace_sed_library)
from preview_checked_parsers_together import compare

VERSIONS = {"grep": "grep-3.12", "sed": "sed-4.10", "gzip": "gzip-1.14"}


def namespace(name, path, residues, release, stage):
    if residues:
        raise ValueError("unexpected loose C residue")
    objects = []
    if name == "gzip":
        pins = release["source_library_sha256"]
        key, = [k for k in pins if k.endswith("/libcoreutils_small_01_reachable.a")]
        provider = ROOT / key
        support = Path("/rustbox-gzip/normalized-clang/lib/libgzip.a")
        if digest(provider) != pins[key] or digest(support) != pins[str(support)]:
            raise ValueError("gzip runtime or gnulib archive differs")
        rust, members, size = coalesce_identical_archive_members(provider, path, stage / "src/.rustbox-gzip-runtime", "gzip")
        if members != release["gzip_coalesced_runtime_members"] or size != release["gzip_coalesced_runtime_member_bytes"]:
            raise ValueError("gzip duplicate runtime members differ")
        mapped, support, syms = namespace_gzip_libraries(rust, support, stage)
        objects.append(support)
    else:
        mapper = {"grep": namespace_grep_library, "sed": namespace_sed_library}[name]
        mapped, syms = mapper(path, stage)
    if syms != release[name + "_namespaced_symbols"]:
        raise ValueError("GNU archive exports differ")
    return mapped, objects


def commands(name, elf, stage):
    version = VERSIONS[name]
    proofs = json.loads((ROOT / ("evidence/" + version + "-oracle.json")).read_bytes())
    source = ROOT / "work/analysis" / version / "oracle"
    cases = {}
    aliases = {}
    for mode in ("applet", "subcommand"):
        folder = stage / mode
        folder.mkdir()
        names = list(proofs["installed_surface"]["public_names"]) + ["less"] if name == "gzip" else [name]
        if name == "grep":
            names = ["grep", "egrep", "fgrep"]
        for n in names:
            path = folder / n
            if mode == "applet":
                path.symlink_to(elf)
            else:
                path.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + n + ' "$@"\n')
                path.chmod(0o755)
        for cc in ("gcc", "clang"):
            if name == "gzip":
                directory = Path("/rustbox-gzip") / ("install-" + cc) / "usr/bin"
                pins = proofs["installed_surface"]["artifacts"][cc]
                if any(digest(directory / n) != row["sha256"] for n, row in pins.items()):
                    raise ValueError("canonical gzip installation differs")
                less = ROOT / "work/analysis/less-710/oracle" / cc / "less"
                if digest(less) != json.loads((ROOT / "evidence/less-710-oracle.json").read_bytes())["binaries"][cc]["less"]["sha256"]:
                    raise ValueError("canonical pager differs")
                if mode == "subcommand":
                    # GNU's installed shell frontends interpolate $0 in their
                    # diagnostics and help. Dot the original file with the same
                    # bare name the multicall dispatcher gives this subcommand.
                    canonical = folder / ("canonical-" + cc)
                    canonical.mkdir()
                    for n in pins:
                        upstream = directory / n
                        entry = canonical / n
                        with upstream.open("rb") as stream:
                            header = stream.readline(64)
                        if header in (b"#!/bin/sh\n", b"#!/bin/bash\n"):
                            shell = header[2:].strip().decode("ascii")
                            body = "exec " + shell + " -c " + shlex.quote(". " + shlex.quote(str(upstream))) + " " + n
                        elif header.startswith(b"\x7fELF"):
                            body = "exec /bin/bash -c " + shlex.quote('exec -a "$0" "$1" "${@:2}"') + " " + n + " " + shlex.quote(str(upstream))
                        else:
                            raise ValueError(f"unsupported canonical gzip frontend {n}")
                        entry.write_text("#!/bin/sh\n" + body + ' "$@"\n')
                        entry.chmod(0o755)
                    directory = canonical
                flags = ["--gcc-directory", directory, "--clang-directory", folder, "--canonical-less", less]
            else:
                binary = source / (name + "-" + cc)
                if digest(binary) != proofs["binaries"][cc]["sha256"]:
                    raise ValueError("unexpected canonical binary")
                if mode == "subcommand":
                    # The original oracle invokes ./grep or ./sed. A Rustbox
                    # subcommand receives the bare name in argv[0], which getopt
                    # prints verbatim. Give canonical C the same argument bytes.
                    directory = folder / ("bin-" + cc)
                    directory.mkdir()
                    (directory / name).symlink_to(binary)
                    binary = folder / ("invoke-" + cc)
                    binary.write_text("#!/bin/sh\nPATH=" + shlex.quote(str(directory)) + ':$PATH\nexport PATH\nexec ' + name + ' "$@"\n')
                    binary.chmod(0o755)
                flags = ["--gcc", binary, "--clang", folder / name]
            report = folder / (cc + ".json")
            subprocess.run(["python3", ROOT / ("tests/" + name + "-oracle-differential.py"), *flags, "--output", report],
                           check=True, stdout=subprocess.DEVNULL)
            row = json.loads(report.read_bytes())
            if name == "gzip":
                if row["cases"] != row["passed"]:
                    raise ValueError("incomplete gzip command suite")
                checked = row["passed"]
            else:
                if not row["gcc_clang_exact"]:
                    raise ValueError("GNU command comparisons differ")
                checked = row["comparisons"]
            if not checked:
                raise ValueError("empty command suite")
            cases[mode + "-" + cc] = checked
            if name == "grep":
                canonical = folder / ("canonical-" + cc)
                canonical.mkdir()
                for n in names:
                    ref = source / (n + "-" + cc)
                    key = "sha256" if n == "grep" else n + "_wrapper_sha256"
                    if digest(ref) != proofs["binaries"][cc][key]:
                        raise ValueError("unexpected canonical grep alias")
                    (canonical / n).symlink_to(ref)
                report = folder / ("aliases-" + cc + ".json")
                subprocess.run(["python3", ROOT / "tests/grep-alias-differential.py", "--canonical-directory", canonical,
                                "--applet-directory", folder, "--output", report], check=True, stdout=subprocess.DEVNULL)
                aliases[mode + "-" + cc] = json.loads(report.read_bytes())["comparisons"]
                if aliases[mode + "-" + cc] != 4:
                    raise ValueError("expected four grep alias comparisons")
    return dict(commands=cases, **({"alias_cases": aliases} if aliases else {}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "output"):
        p.add_argument(arg, type=Path)
    for name in VERSIONS:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    packages = {n: (n + "-errno-archive.json", partial(namespace, n), partial(commands, n)) for n in VERSIONS}
    compare(a.parent, a.log, a.output, {k: getattr(a, k) for k in packages}, packages)
