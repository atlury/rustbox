#!/usr/bin/env python3
"""Accept equivalent C strings only in parsed casts and preserve unrelated Rust tokens."""
# SPDX-License-Identifier: 0BSD
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_c_string_literal_pilot import rewrite

subprocess.run(["cargo", "build", "--locked", "--offline", "--release", "--manifest-path",
                ROOT / "tools/private-inlines/Cargo.toml", "--bin", "c-string-literals", "--target-dir",
                ROOT / "work/analysis/syntax-tools-native"], check=True)
tool = ROOT / "work/analysis/syntax-tools-native/release/c-string-literals"
with TemporaryDirectory() as temp:
    folder = Path(temp)
    original = (Path(__file__).parent / "input.rs").read_bytes()
    (folder / "input.rs").write_bytes(original)
    replaced, delta = rewrite(folder, ["input.rs"], tool)
    converted = replaced["input.rs"]
    assert delta["c_string_literals"] == 2 and delta["raw_pointer_types_removed"] == 4
    for line in original.splitlines():
        if any(x in line for x in (b"let inside", b"let missing", b"let other", b"let token", b"let comment")):
            assert line in converted
    (folder / "converted.rs").write_bytes(converted)
    outputs = []
    for name in ("input", "converted"):
        subprocess.run(["rustc", "--edition=2021", folder / (name + ".rs"), "-o", folder / name], check=True)
        outputs.append(subprocess.check_output([folder / name]))
    assert outputs[0] == outputs[1]
print("Rust compiled both variants and returned the same bytes, including escaped non-UTF-8 data.")
