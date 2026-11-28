"""Exercise debugfs xattr hashing on a private image with external attribute blocks."""
# SPDX-License-Identifier: LGPL-2.0-only
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import subprocess


def compare(stage, programs):
    env = dict(os.environ, LC_ALL="C", TZ="UTC", E2FSPROGS_FAKE_TIME="1700000000", E2FSCK_TIME="1700000000")
    canonical = Path("/oracle/stage-gcc/sbin")
    image = stage / "original.img"
    with image.open("xb") as f:
        f.truncate(8 * 1024 * 1024)
    subprocess.run([canonical/"mke2fs", "-qF", "-t", "ext2", "-b", "1024", "-I", "128", "-U",
                    "0870f485-b34a-4726-8a76-5fd731130fac", image], env=env, capture_output=True, check=True)
    # A fixed filesystem UUID does not fix mke2fs's per-image directory hash seed.
    # Every implementation starts with a byte-for-byte copy of the same image.
    names = [b"user.a", b"user.\x80name", b"user.\xff"]
    writes = [(names[0], 1), (names[1], 6), (names[2], 271), (names[1], 33)]
    reference = None
    for label, program in programs.items():
        work = stage / ("image-" + label)
        work.mkdir()
        shutil.copyfile(image, work/"fs.img")
        transcript = []
        def invoke(command):
            result = subprocess.run([program, "-w", "-R", command, "fs.img"], cwd=work, env=env,
                                    capture_output=True, check=True, timeout=120)
            transcript.append((result.stdout, result.stderr))
            return result.stdout
        for name, size in writes:
            data = bytes((i * 197 + size) & 255 for i in range(size))
            (work/"value").write_bytes(data)
            invoke(b"ea_set -f value / " + name)
            invoke(b"ea_get -f recovered / " + name)
            if (work/"recovered").read_bytes() != data:
                raise ValueError(f"{label} did not preserve extended attribute bytes")
            (work/"recovered").unlink()
        if not re.search(rb"File ACL: [1-9][0-9]*", invoke(b"stat /")):
            raise ValueError("expected the attributes in an external block")
        original_names = invoke(b"ea_list /")
        if b"user.a (1)" not in original_names or sorted(re.findall(rb" \((\d+)\)", original_names)) != [b"1", b"271", b"33"]:
            raise ValueError("missing extended attribute")
        invoke(b"ea_rm / " + names[0])
        remaining = invoke(b"ea_list /")
        if names[0] in remaining or sorted(re.findall(rb" \((\d+)\)", remaining)) != [b"271", b"33"]:
            raise ValueError("attribute removal changed the wrong names")
        checked = subprocess.run([canonical/"e2fsck", "-fn", "fs.img"], cwd=work, env=env,
                                 capture_output=True, check=True, timeout=120)
        transcript.append((checked.stdout, checked.stderr))
        result = (transcript, sha256((work/"fs.img").read_bytes()).digest())
        if reference is not None and result != reference:
            raise ValueError(f"{label} differed on command output or the resulting filesystem")
        reference = result
    return dict(compared=sorted(programs), attribute_writes=len(writes), raw_names=len(names),
                external_block=True, command_comparisons_per_program=len(reference[0]), identical_images=True)
