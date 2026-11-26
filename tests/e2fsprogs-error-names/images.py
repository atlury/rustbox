#!/usr/bin/env python3
"""Exercise first and last ext superblock error names through the three E2fsprogs readers."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
ORACLE = Path("/rustbox-e2fsprogs")
PACKAGE = ROOT / "work/analysis/e2fsprogs-1.47.4"
OPTIONS = {"debugfs": ["-R", "stats"], "dumpe2fs": ["-h"], "tune2fs": ["-l"]}
FIELDS = ("first_error_time", "last_error_time", "first_error_errcode", "last_error_errcode")


def checks(elf, batch, directory):
    canonical = {cc: ORACLE / ("stage-" + cc) / "sbin" for cc in ("gcc", "clang-18")}
    layout = directory / "layout"
    includes = ["-I" + str(ORACLE / "oracle-gcc/lib"), "-I" + str(ROOT / "work/upstream/e2fsprogs-1.47.4/lib")]
    code = "#include <stddef.h>\n#include <stdio.h>\n#include <ext2fs/ext2_fs.h>\nint main(void) {\n"
    for field in FIELDS:
        code += f'printf("%zu %zu\\n", offsetof(struct ext2_super_block,s_{field}), sizeof(((struct ext2_super_block *)0)->s_{field}));\n'
    subprocess.run(["gcc", *includes, "-x", "c", "-", "-o", layout], input=(code + "return 0;}\n").encode(), check=True)
    positions = [tuple(map(int, line.split())) for line in subprocess.check_output([layout]).splitlines()]
    if [size for _, size in positions] != [4, 4, 1, 1]:
        raise ValueError("canonical ext error field layout differs")
    image = directory / "sample.img"
    with image.open("xb") as f:
        f.truncate(8 * 1024 * 1024)
    env = dict(os.environ, LC_ALL="C", TZ="UTC", E2FSPROGS_FAKE_TIME="1700000000", PAGER="cat")
    subprocess.run([canonical["gcc"] / "mke2fs", "-qF", "-t", "ext2", "-O", "none", "-b", "1024",
                    "-U", "11111111-2222-3333-4444-555555555555", image], env=env, check=True)

    programs = {engine: {cc: ([engine], folder / engine) for cc, folder in canonical.items()} for engine in OPTIONS}
    input_hashes = {}
    for engine, targets in programs.items():
        alias = directory / engine
        alias.symlink_to(elf)
        targets["symlink"] = ([engine], alias)
        targets["subcommand"] = ([elf, engine], elf)
        if batch:
            folder = batch / engine
            row = json.loads((folder / "pilot.json").read_bytes())
            archive = folder / Path(row["archive"]).name
            if sha256(archive.read_bytes()).hexdigest() != row["candidate_sha256"]:
                raise ValueError("unexpected engine archive")
            shared = PACKAGE / "program-translations/rustbox-e2fsprogs-shared"
            program = directory / (engine + "-candidate")
            subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", f"-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_{engine}_main",
                            ROOT / "bridges/e2fsprogs_program_main.c", archive, *(shared / n for n in ("crc16.o", "crc32.o", "bitcount.o")),
                            "-lblkid", "-luuid", "-lfuse3", "-ldl", "-lpthread", "-lm", "-o", program], check=True)
            targets["archive"] = ([engine], program)
            input_hashes[engine] = row["candidate_sha256"]
    cases = [(0, 0, "", ""), (2, 4, "EIO", "EFSBADCRC"), (17, 18, "EFAULT", "UNKNOWN_ERRCODE_18"),
             (255, 1, "UNKNOWN_ERRCODE_255", "UNKNOWN")]
    for first, last, first_text, last_text in cases:
        with image.open("r+b") as f:
            for (offset, size), value in zip(positions, (1700000000, 1700000001, first, last)):
                f.seek(1024 + offset)
                f.write(value.to_bytes(size, "little"))
        for engine, targets in programs.items():
            observed = {}
            for name, (prefix, binary) in targets.items():
                result = subprocess.run([*prefix, *OPTIONS[engine], image], executable=binary, env=env,
                                        capture_output=True, timeout=30)
                observed[name] = result.returncode, result.stdout, result.stderr
            status, stdout, _ = observed["gcc"]
            if status or len(set(observed.values())) != 1:
                raise ValueError((engine, first, last, {n:(v[0],sha256(v[1]).hexdigest(),v[2]) for n,v in observed.items()}))
            for label, text in (("First", first_text), ("Last", last_text)):
                lines = [line.split(b":", 1)[1].strip() for line in stdout.splitlines() if line.startswith((label + " error err:").encode())]
                if lines != ([text.encode()] if text else []):
                    raise ValueError((engine, first, last, label, lines))
    return dict(elf_sha256=sha256(elf.read_bytes()).hexdigest(), archives=input_hashes, cases_per_command=len(cases),
                commands=list(OPTIONS), error_codes=[[f,l] for f,l,_,_ in cases], dispatch_comparisons=4*len(cases)*len(OPTIONS),
                archive_comparisons=2*len(cases)*len(OPTIONS) if batch else 0)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("batch", type=Path, nargs="?")
    a=p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(checks(a.elf.resolve(), a.batch, Path(tmp)), indent=2, sort_keys=True))
