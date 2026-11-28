#!/usr/bin/env python3
"""Compare curl's actual descriptor choices for byte strings and explicit lengths."""
# SPDX-License-Identifier: curl
import argparse
import ctypes
import json
from pathlib import Path
import random
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_curl_scheme_lookup import CANONICAL, HELPER, canonical_lookup
from check_cargo_private_inlines import digest


def compile_oracles(directory, cc):
    src = CANONICAL.parent
    lookup = canonical_lookup()
    names = sorted(re.findall(rb"return &Curl_scheme_([a-z0-9]+);", lookup))
    table = (src / "strcase.c").read_bytes()
    inline = (src / "strcase.h").read_bytes()
    compare = (src / "strequal.c").read_bytes()
    tables = b"\n".join(re.findall(rb"const unsigned char Curl_\w+map\[256\] = \{.*?\n\};", table, re.S))
    folds = b"\n".join(re.findall(rb"static CURL_INLINE char Curl_raw_to\w+\(.*?\n\}", inline, re.S))
    c = (b'#include <stddef.h>\n#define CURL_INLINE inline\nstruct Curl_scheme { int id; };\n'
         + tables + b"\n" + folds + b"\n" + compare[compare.index(b"static int casecompare("):]
         + b"\n".join(b"static const struct Curl_scheme Curl_scheme_%s = { %d };" % (n,i) for i,n in enumerate(names,1))
         + b"\n" + lookup + b"\nint selected(const char *s, size_t n) { const struct Curl_scheme *v = Curl_getn_scheme(s,n); return v ? v->id : 0; }")
    rust = (b"#![allow(non_camel_case_types,non_upper_case_globals)]\n"
            b"type size_t = usize; pub struct Curl_scheme(i32);\n"
            + b"\n".join(b"static mut Curl_scheme_%s: Curl_scheme = Curl_scheme(%d);" % (n,i) for i,n in enumerate(names,1))
            + b"\n" + HELPER.read_bytes()
            + b'\n#[no_mangle] unsafe extern "C" fn selected(s: *const core::ffi::c_char,n:usize)->i32 { Curl_getn_scheme(s,n).as_ref().map_or(0, |v| v.0) }')
    (directory / "oracle.c").write_bytes(c)
    (directory / "lookup.rs").write_bytes(rust)
    subprocess.run([cc,"-std=c11","-O2","-fPIC","-shared","oracle.c","-o","canonical.so"],cwd=directory,check=True)
    subprocess.run(["rustc","--edition=2021","--crate-type","cdylib","-O","lookup.rs","-o","candidate.so"],cwd=directory,check=True)
    def selected(path):
        func = ctypes.CDLL(str(directory / path)).selected
        func.argtypes, func.restype = (ctypes.c_char_p, ctypes.c_size_t), ctypes.c_int
        return func
    return names, selected("canonical.so"), selected("candidate.so")


def compare(cc):
    with TemporaryDirectory() as tmp:
        names, original, candidate = compile_oracles(Path(tmp), cc)
        total = 0
        def check(buf, length, expected=None):
            nonlocal total
            a, b = original(buf,length), candidate(buf,length)
            if a != b or (expected is not None and a != expected):
                raise ValueError(f"descriptor mismatch for {buf!r}, length {length}: {a}, {b}, expected {expected}")
            total += 1
        for length in (0,1,8,255,ctypes.c_size_t(-1).value):
            check(None,length,0)
        for index, name in enumerate(names,1):
            for mask in range(1<<len(name)):
                mixed = bytes(c-32 if 97<=c<=122 and mask & (1<<i) else c for i,c in enumerate(name))
                check(mixed+b":ignored",len(name),index)
            for base in (name,name.upper()):
                for i in range(len(name)):
                    for value in range(256):
                        check(base[:i]+bytes([value])+base[i+1:],len(base))
            for length in range(len(name)+1):
                check(name,length)
        random_bytes = random.Random(20261128)
        for _ in range(16384):
            data = random_bytes.randbytes(random_bytes.randrange(10))
            check(data,len(data))
    return dict(cases=total, passed=total, schemes=len(names), helper_sha256=digest(HELPER),
                protocol_sha256=digest(CANONICAL),
                case_sources_sha256={name:digest(CANONICAL.parent/name) for name in ("strcase.c","strcase.h","strequal.c")},
                cc=subprocess.check_output([cc,"--version"],text=True).splitlines()[0])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc",default="cc")
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    result = compare(args.cc)
    report = json.dumps(result,sort_keys=True,indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    print(report,end="")
