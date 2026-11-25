#!/usr/bin/env python3
"""Compare every ordered dictionary entry and length using compiled upstream C and safe Rust."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_linked_pointers import measure
from build_lz4_dictionary_pilot import CANONICAL, MODULE, transform
from cargo_source_parent import cargo_origin

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("link", type=Path)
args = p.parse_args()
link = json.loads(args.link.read_bytes())
key, = [k for k in link["source_library_sha256"] if k.endswith("/liblz4_1_11_1_normalized_audit.a")]
with TemporaryDirectory() as folder:
    work = Path(folder)
    (work / "reference.c").write_text("""
#include <stdio.h>
#include "lorem.c"
int main(void) {
    for (size_t i = 0; i < kNbWords; ++i) {
        size_t len = strlen(kWords[i]);
        if (fputc((int)len, stdout) == EOF || fwrite(kWords[i], 1, len, stdout) != len) return 1;
    }
    return 0;
}
""")
    subprocess.run(["cc", "-O2", "-I" + str(CANONICAL.parent), work / "reference.c", "-o", work / "reference"], check=True)
    expected = subprocess.check_output([work / "reference"])
    def test(archive, module, checksum, data):
        if str(module) != MODULE:
            return
        candidate, stats = transform(data)
        start = candidate.index(b"#[forbid(unsafe_code)]\nmod dictionary {")
        end = candidate.index(b"static mut kNbWords:", start)
        main = b"""
fn main() {
    use std::io::Write;
    let mut out = std::io::stdout().lock();
    for i in 0..dictionary::COUNT {
        let word = dictionary::word(i);
        assert_eq!(word.len() as u32, dictionary::LENGTHS[i]);
        out.write_all(&[word.len() as u8]).unwrap();
        out.write_all(word).unwrap();
    }
}
"""
        (work / "words.rs").write_bytes(candidate[start:end] + main)
        subprocess.run(["rustc", "--edition=2021", "-Funsafe_code", work / "words.rs", "-o", work / "words"], check=True)
        if subprocess.check_output([work / "words"]) != expected or stats["words"] != 255:
            raise ValueError("LZ4 dictionary or lengths differ from canonical C")
        try:
            transform(data.replace(b"lorem", b"LORem", 1))
        except ValueError:
            return
        raise ValueError("accepted an unrecognized parent source")
    measure(link, inspect_module=test, archive_pair=(cargo_origin(link, key), Path(key)))
    if not (work / "words").is_file():
        raise ValueError("the selected archive omitted the dictionary module")
    print(f"All 255 entries and lengths matched the compiled canonical dictionary ({len(expected)} output bytes).")
