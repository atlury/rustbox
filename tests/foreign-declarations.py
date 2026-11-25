#!/usr/bin/env python3
"""Exercise the declaration selector's syntax, visibility and diagnostic boundaries."""
# SPDX-License-Identifier: 0BSD
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def check(selector, directory):
    source = b'''extern "C" {
    fn dead(arg: *const u8);
    static mut UNUSED: *mut u8;
    pub fn exported();
    #[link_name = "other"]
    fn renamed();
    fn called();
    fn stale();
    fn expanded();
}
extern "Rust" { fn native(); }
unsafe fn body() { called(); }
'''
    (directory / "lib.rs").write_bytes(source)
    nested = b'mod child;\nextern "C" { fn nested(); }\n'
    (directory / "parent.rs").write_bytes(nested)
    records = []
    for name in ("dead", "UNUSED", "exported", "renamed", "called", "stale", "expanded", "native", "body", "nested"):
        parent = name == "nested"
        start = (nested if parent else source).index(name.encode()) + int(name == "stale")
        kind = "static" if name == "UNUSED" else "function"
        records.append({"code": {"code": "dead_code"}, "message": f"{kind} `{name}` is never used",
                        "spans": [{"file_name": "parent.rs" if parent else "lib.rs", "is_primary": True,
                                   "expansion": {} if name == "expanded" else None, "byte_start": start}]})
    data = "".join(json.dumps(item) + "\n" for item in records).encode()
    result = json.loads(subprocess.check_output([selector], cwd=directory, input=data))
    if set(result) != {"lib.rs"} or [source[a:b] for a, b in result["lib.rs"]] != [
            b"fn dead(arg: *const u8);", b"static mut UNUSED: *mut u8;"]:
        raise ValueError(f"unexpected declaration selection: {result}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        check(Path(sys.argv[1]).resolve(), Path(tmp))
