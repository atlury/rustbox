#!/usr/bin/env python3
"""Compare the checked compression discriminator with both canonical file 5.48 compilers."""
# SPDX-License-Identifier: BSD-2-Clause
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_file_compression_headers import NATIVE, TABLE_START, TABLE_END, region
from check_cargo_private_inlines import digest


def predicates(canonical, translated, scratch, compilers):
    source = canonical.read_bytes()
    funcs = []
    for name in (b"zlibcmp", b"lzmacmp"):
        start = source.index(b"static int\n" + name + b"(const unsigned char *buf)")
        funcs.append(source[start:source.index(b"\n}", start)+2])
    # Take exact C string spellings and signed required lengths from the canonical table.
    table = re.findall(rb'\{ \{ \.(?:magic|func) = ("(?:\\.|[^"\\])*"|lzmacmp|zlibcmp) \},\s*(-?\d+),', source)
    if len(table) != 15:
        raise ValueError("canonical file compression table differs")
    entries = [b"{" + (b"NULL," + magic if length.startswith(b"-") else b"(const unsigned char *)" + magic + b",NULL") + b","+length+b"}" for magic,length in table]
    header = region(translated.read_bytes(), TABLE_START, TABLE_END)
    selected = re.findall(rb"^            header: (CompressionHeader::[^\n]+),$", header, re.M)
    if len(selected) != len(entries):
        raise ValueError("tested Rust rows differ from the translated archive")
    rust = scratch/"probe.rs"
    rust.write_bytes(NATIVE.read_bytes() + b"\nconst HEADERS: [CompressionHeader; 15] = [" + b",".join(selected) + b"];\n" + b"""
#[no_mangle]
pub unsafe extern "C" fn check_rust(i: usize, p: *const u8, n: usize) -> i32 {
    let h = HEADERS[i];
    if n < h.length() { return 0; }
    h.matches(::core::slice::from_raw_parts(p, h.length())) as i32
}
""")
    subprocess.run(["rustc","--edition","2021","--crate-type","staticlib","-C","opt-level=2",rust,"-o",scratch/"libprobe.a"],check=True)
    c = scratch/"probe.c"
    c.write_bytes(b"""#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int file_bigendian(void) { uint16_t a=1; return *(const unsigned char *)&a == 0; }
""" + b"\n".join(funcs) + b"""
struct method { const unsigned char *magic; int (*test)(const unsigned char *); int len; };
static const struct method methods[] = {""" + b",".join(entries) + b"""};
extern int check_rust(size_t, const unsigned char *, size_t);
static unsigned long total;
static void test(size_t index, const unsigned char *p, size_t n) {
    const struct method *m = &methods[index];
    int c = n >= (size_t)abs(m->len) && (m->test ? m->test(p) : memcmp(p,m->magic,m->len)==0);
    if (c != check_rust(index,p,n)) exit(2);
    ++total;
}
int main(void) {
    unsigned char b[16] = {0};
    for (unsigned v=0;v<65536;++v) {
        b[0]=v>>8; b[1]=v;
        for (size_t i=0;i<15;++i) test(i,b,2);
    }
    memset(b,0,sizeof(b)); b[0]=0x5d;
    for (int pos=0;pos<13;++pos) {
        unsigned char old=b[pos];
        for (unsigned v=0;v<256;++v) { b[pos]=v; test(13,b,13); }
        b[pos]=old;
    }
    for (size_t i=0;i<15;++i) {
        if (methods[i].magic) memcpy(b,methods[i].magic,methods[i].len);
        for (size_t n=0;n<=sizeof(b);++n) {
            test(i,b,n);
            for (size_t j=0;j<n;++j) { b[j]^=1; test(i,b,n); b[j]^=1; }
        }
        test(i,NULL,0);
    }
    printf("%lu\\n",total);
    return 0;
}
""")
    results = {}
    for cc in compilers:
        subprocess.run([cc,"-O2",c,scratch/"libprobe.a","-lm","-lpthread","-ldl","-o",scratch/"probe"],check=True)
        results[cc] = int(subprocess.check_output([scratch/"probe"]))
    return results


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("canonical", type=Path)
    p.add_argument("translated", type=Path)
    p.add_argument("--cc", action="append", required=True)
    args=p.parse_args()
    with TemporaryDirectory() as tmp:
        counts=predicates(args.canonical,args.translated,Path(tmp),args.cc)
    print(json.dumps(dict(canonical_source_sha256=digest(args.canonical),translated_source_sha256=digest(args.translated),
                          helper_sha256=digest(NATIVE),comparisons=counts),sort_keys=True))
