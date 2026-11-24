#!/usr/bin/env python3
"""Replay the x86-64 Linux link map with GNU ld packed relative relocations."""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path, help="configured Coreutils build directory")
    parser.add_argument("destination", type=Path, help="new directory for the stripped candidate")
    args = parser.parse_args()
    build = args.build.resolve()
    production = build / "src/rustbox"
    loads = [line[5:] for line in production.with_suffix(".map").read_text().splitlines()
             if line.startswith("LOAD ")]
    first = loads.index(str(build / "src/.rustbox-dispatch.o"))
    last = next(i for i in range(first, len(loads)) if loads[i].endswith("/libgcc.a"))
    # clang supplies startup objects and libgcc. The system .so linker scripts
    # already expand the versioned .so inputs listed in the GNU map.
    inputs = ["lib/.rustbox-libcoreutils.a" if p == "lib/libcoreutils.a" else p
              for p in loads[first:last] if ".so." not in p]

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        baseline = root / "baseline"
        subprocess.run(["strip", "-s", "-o", baseline, production], check=True)
        for name, flags in (("control", []), ("packed", ["-Wl,-z,pack-relative-relocs"])):
            output = root / name / "rustbox"
            output.parent.mkdir()
            subprocess.run(["clang-18", "-Wl,--gc-sections,--as-needed", *flags,
                            "-o", output, *inputs], cwd=build, check=True)
            subprocess.run(["strip", "-s", output], check=True)
            fingerprint = digest(output)
            if name == "control" and fingerprint != digest(baseline):
                raise RuntimeError("control link differs from the stripped baseline")
            subprocess.run([output, "true"], check=True)
            print(name, output.stat().st_size, fingerprint, flush=True)
        args.destination.mkdir(parents=True, exist_ok=False)
        shutil.copy2(output, args.destination / "rustbox")


if __name__ == "__main__":
    main()
