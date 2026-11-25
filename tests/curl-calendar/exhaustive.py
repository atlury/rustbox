#!/usr/bin/env python3
"""Compare all three-byte words to curl's canonical signed- and unsigned-char C implementations."""
# SPDX-License-Identifier: curl
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
source_file = ROOT / "work/upstream/curl-8.23.0/lib/parsedate.c"
source = source_file.read_bytes()
start = source.index(b"UNITTEST int checkmonth(const char *check, size_t len)\n{")
canonical = source[start:source.index(b"\n}", start) + 2]
lower, = [line for line in source.splitlines() if line.startswith(b"#define LOWERCASE(")]
assert lower == b"#define LOWERCASE(x) ((x) | 0x20)"
assert sha256(canonical).hexdigest() == "0484f2b6023f335207bc050462c6f9b44ed05b818ee26f74e912dda7db7f5d58"
helper = (ROOT / "compat/curl/month.rs").read_bytes()
with TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "canonical.c").write_bytes(b"#include <stdint.h>\n#include <stddef.h>\n#define UNITTEST\n" +
                                       lower + b"\n" + canonical + b"\n")
    (work / "candidate.rs").write_bytes(helper + b'''
#[no_mangle]
extern "C" fn rustbox_test_month(a: u8, b: u8, c: u8) -> i32 {
    checkmonth([a, b, c])
}
''')
    subprocess.run(["rustc", "--edition=2021", "-O", "--crate-type=staticlib", "candidate.rs", "-o", "month.a"],
                   cwd=work, check=True)
    results = {}
    for cc in ("gcc", "clang-18"):
        for char in ("signed", "unsigned"):
            subprocess.run([cc, "-O2", f"-f{char}-char", "canonical.c", ROOT / "tests/curl-calendar/months.c",
                            "month.a", "-o", "test"], cwd=work, check=True)
            actual = subprocess.check_output([work / "test"])
            if actual != b"16777216 words, 96 accepted spellings\n":
                raise ValueError(actual)
            results[cc + "-" + char] = 1 << 24
    print(json.dumps(dict(cases_per_build=results, accepted_spellings=96, canonical_function_sha256=sha256(canonical).hexdigest(),
                          canonical_file_sha256=sha256(source).hexdigest(), safe_helper_sha256=sha256(helper).hexdigest()),
                     sort_keys=True, indent=2))
