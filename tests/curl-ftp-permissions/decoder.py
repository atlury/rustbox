#!/usr/bin/env python3
"""Compare all byte mutations of all UNIX permission modes with curl's own decoder."""
# SPDX-License-Identifier: curl
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "work/upstream/curl-8.23.0/lib/ftplistparser.c").read_bytes()
assert sha256(source).hexdigest() == "abda2491568be631d71d699410aeeaeadd338705da3429b64b0909953dda7b42"
start = source.index(b"#define FTP_LP_MALFORMATED_PERM ")
end = source.index(b"\n}\n", start) + 3
helper = (ROOT / "compat/curl/ftp_permissions.rs").read_bytes()
driver = Path(__file__).with_suffix(".c")
with TemporaryDirectory() as folder:
    scratch = Path(folder)
    (scratch / "reference.c").write_bytes(source[start:end] + b"""
unsigned int canonical(const char *p) { return ftp_pl_get_permission(p); }
""")
    (scratch / "rust.rs").write_bytes(helper + b"""
#[no_mangle]
pub extern "C" fn candidate(bytes: &[u8; 9]) -> u32 { ftp_pl_get_permission(*bytes) }
""")
    subprocess.run(["rustc", "-O", "--edition=2021", "--crate-type=staticlib", "rust.rs", "-o", "rust.a"], cwd=scratch, check=True)
    results = {}
    for cc in ("gcc", "clang-18"):
        for char in ("signed", "unsigned"):
            subprocess.run([cc, "-O2", "-Wall", "-Wextra", "-Werror", f"-f{char}-char", "reference.c", driver,
                            "rust.a", "-o", "compare"], cwd=scratch, check=True)
            expected = 4096 * 9 * 256
            if subprocess.check_output([scratch / "compare"]) != f"{expected} comparisons and 4096 known modes\n".encode():
                raise ValueError("incomplete FTP mode comparison")
            results[f"{cc}-{char}"] = expected
    print(json.dumps(dict(known_modes=4096, byte_mutations_per_build=results, helper_sha256=sha256(helper).hexdigest(),
                          canonical_source_sha256=sha256(source).hexdigest(), driver_sha256=sha256(driver.read_bytes()).hexdigest()),
                     indent=2, sort_keys=True))
