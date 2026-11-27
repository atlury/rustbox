#!/usr/bin/env python3
"""Compare isosize ISO number readers on regular files, including inconsistent endian fields."""
# SPDX-License-Identifier: 0BSD
from argparse import ArgumentParser
from hashlib import sha256
import json
import os
from pathlib import Path
from random import Random
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_isosize_numbers import ARCHIVE
from check_cargo_private_inlines import digest


def check(parent, pilot, folder):
    selected = json.loads(parent.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    archives = {"parent": ROOT / ARCHIVE, "candidate": pilot / Path(ARCHIVE).name}
    if (row["archive"] != ARCHIVE or row["control_sha256"] != selected["source_library_sha256"][ARCHIVE]
            or row["control_binary_sha256"] != selected["binary"]["sha256"]
            or digest(archives["parent"]) != row["control_sha256"] or digest(archives["candidate"]) != row["candidate_sha256"]):
        raise ValueError("untested archive selection")
    base = Path("/rustbox-util-linux")
    gcc, clang = (base / ("canonical-" + name + "-compdb") for name in ("gcc", "clang"))
    binaries = {"gcc": gcc / "isosize", "clang": clang / "isosize"}
    for name, archive in archives.items():
        binary = folder / name
        subprocess.run(["clang-18", "-O2", ROOT / "bridges/util-linux/small-02-dispatch.c", archive,
                        clang / ".libs/libblkid.a", clang / ".libs/libcommon.a", "-leconf", "-ldl", "-lpthread",
                        "-lrt", "-lutil", "-lm", "-o", binary], check=True)
        binaries[name] = binary

    results = compare_profiles(binaries, folder)
    return dict(archive=row, canonical_binaries={k:digest(binaries[k]) for k in ("gcc", "clang")},
                driver_sha256=digest(Path(__file__)), **results)


def compare_profiles(binaries, folder):
    rng = Random(9660)
    numbers = [(0, 0, 0, 0), (1, 1, 2048, 2048), (0xffffffff, 0x80000000, 65535, 32768),
               (0x12345678, 0x78563412, 0x1234, 0x3412)]
    for _ in range(96):
        sectors, block = rng.getrandbits(32), rng.getrandbits(16)
        numbers.extend([(sectors, sectors, block, block), (sectors, sectors ^ 1, block, block ^ 1)])
    names = []
    for i, (little, big, size, other) in enumerate(numbers):
        file = folder / f"{i}.iso"
        data = bytearray(0x8084)
        data[0x8000:0x8008] = b"\1CD001\1\0"
        struct.pack_into("<I", data, 0x8050, little)
        struct.pack_into(">I", data, 0x8054, big)
        struct.pack_into("<H", data, 0x8080, size)
        struct.pack_into(">H", data, 0x8082, other)
        file.write_bytes(data)
        names.append(file.name)
    (folder / "short.iso").write_bytes(data[:0x8083])
    data[0x8000] = 0
    (folder / "unlabelled.iso").write_bytes(data)
    cases = [names, ["-x", *names], ["-d", "512", *names], ["-d", "2048", *names], ["short.iso"],
             ["-x", "unlabelled.iso"], ["1.iso", "short.iso", "missing.iso"], ["missing.iso"]]
    summary = []
    memchecks = 0
    for num, args in enumerate(cases):
        expected = None
        for name, binary in binaries.items():
            modes = [["isosize"]]
            if name == "multicall":
                modes.append(["rustbox", "isosize"])
            elif name in ("parent", "candidate"):
                modes.append(["rustbox-util-linux-small-02", "isosize"])
            for prefix in modes:
                cmd = [*prefix, *args]
                proc = subprocess.run(cmd, executable=binary, capture_output=True, cwd=folder, env=dict(os.environ, LC_ALL="C"), timeout=120)
                actual = proc.returncode, proc.stdout, proc.stderr
                if expected is None:
                    expected = actual
                if expected != actual:
                    raise ValueError((num, name, prefix, "canonical status, stdout or stderr differs"))
            if num == 1:
                alias = folder / ("memcheck-" + name) / "isosize"
                alias.parent.mkdir()
                alias.symlink_to(binary)
                log = alias.parent / "memcheck.log"
                proc = subprocess.run(["valgrind","--error-exitcode=99","--log-file="+str(log),alias,*args],
                                      capture_output=True,cwd=folder,env=dict(os.environ,LC_ALL="C"),timeout=240)
                if (proc.returncode, proc.stdout, proc.stderr) != expected or "ERROR SUMMARY: 0 errors" not in log.read_text():
                    raise ValueError(("Memcheck", name))
                memchecks += 1
        status, stdout, stderr = expected
        if num == 1 and (not status == 0 or len(stdout.splitlines()) != len(names)
                          or stderr.count(b"723error:") != 98 or stderr.count(b"733error:") != 98):
            raise ValueError("endian mismatch diagnostics were not exercised")
        summary.append(dict(status=status, stdout_sha256=sha256(stdout).hexdigest(), stderr_sha256=sha256(stderr).hexdigest()))
    return dict(image_count=len(names), profiles=summary, memcheck_runs=memchecks)


if __name__ == "__main__":
    p=ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("pilot", type=Path)
    a=p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(check(a.parent.resolve(), a.pilot.resolve(), Path(tmp)), indent=2, sort_keys=True))
