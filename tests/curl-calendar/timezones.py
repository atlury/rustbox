#!/usr/bin/env python3
"""Compare every reachable one- to four-letter curl timezone with its original C routine."""
# SPDX-License-Identifier: curl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_curl_timezone import CANONICAL, HELPER, MODULE, substitute
from check_cargo_private_inlines import digest

source = CANONICAL.read_bytes()
tables = source[source.index(b"struct tzinfo {"):source.index(b"#define LOWERCASE(")]
start = source.index(b"static int tzcompare(")
end = source.index(b"static void skip(", start)
driver = Path(__file__).with_name("timezones.c")
crate = ROOT / "work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable"
replacements, info = substitute(crate, {MODULE: digest(crate / MODULE)})
candidate = replacements[MODULE]
a = candidate.index(b"static tzone:")
b = candidate.index(b'unsafe extern "C" fn checkday(', a)
h = HELPER.read_bytes()
if candidate.count(h) != 1:
    raise ValueError("expected checked time-zone functions in generated parser")
with TemporaryDirectory() as temp:
    dest = Path(temp)
    (dest / "canonical.c").write_bytes(b"#include <stdint.h>\n#include <stdlib.h>\n#define UNITTEST\n"
        b"#define CURL_ARRAYSIZE(a) (sizeof(a)/sizeof((a)[0]))\n" + tables + source[start:end])
    (dest / "timezone.rs").write_bytes(b"""#![allow(non_camel_case_types,non_upper_case_globals,unused_parens)]
type int16_t = i16;
type uint32_t = u32;
const DST: i32 = -60;
struct tzinfo { tz: u32, offset: i16 }
""" + candidate[a:b] + h + b"""
#[no_mangle]
pub extern "C" fn rustbox_test_timezone(a: u8, b: u8, c: u8, d: u8, len: usize) -> i32 {
    checktz(&[a, b, c, d][..len])
}
""")
    subprocess.run(["rustc", "--edition=2021", "-O", "--crate-type=staticlib", "timezone.rs", "-o", "timezone.a"],
                   cwd=dest, check=True)
    total = sum(52 ** n for n in range(1, 5))
    results = {}
    for cc in ("gcc", "clang-18"):
        for signedness in ("signed", "unsigned"):
            subprocess.run([cc, "-O2", "-f" + signedness + "-char", "canonical.c", driver, "timezone.a", "-o", "compare"],
                           cwd=dest, check=True)
            out = subprocess.check_output([dest / "compare"])
            if out != f"{total} tokens, 69 valid zones\n".encode():
                raise ValueError(out)
            results[f"{cc}-{signedness}"] = total
    print(json.dumps(dict(cases_per_build=results, accepted_spellings=69, canonical_sha256=info["canonical_sha256"],
                          helper_sha256=digest(HELPER), table_source_sha256=info["tables_sha256"],
                          driver_sha256=digest(driver)), sort_keys=True, indent=2))
