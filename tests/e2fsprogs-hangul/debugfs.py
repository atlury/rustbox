"""Exercise actual case-insensitive directory hashing and compare both public command streams."""
import os
import re
import subprocess
import sys
import unicodedata

count = 0
for algorithm in (1, 2, 4, 5):
    for name in ("가", "각", "힣", "A각\u0301가", "각힣" * 4):
        hashes = []
        for spelling in (name, unicodedata.normalize("NFD", name)):
            command = os.fsencode(f"dx_hash -h {algorithm} -e utf8-12.1 -c {spelling}")
            pair = [subprocess.run([tool, "-R", command], capture_output=True) for tool in sys.argv[1:]]
            a, b = pair
            if (a.returncode, a.stdout, a.stderr) != (b.returncode, b.stdout, b.stderr) or a.returncode:
                raise ValueError((command, a.stdout, b.stdout, a.stderr, b.stderr))
            match = re.fullmatch(rb"Hash of .+ is (0x[0-9a-f]+ \(minor 0x[0-9a-f]+\))\n", a.stdout)
            if match is None:
                raise ValueError((command, a.stdout, a.stderr))
            hashes.append(match[1])
            count += 1
        if hashes[0] != hashes[1]:
            raise ValueError(f"composed and decomposed spellings hashed differently for {name}")
print(f"{count} canonical debugfs Hangul commands matched")
