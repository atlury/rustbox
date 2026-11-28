#!/usr/bin/env python3
"""Check unused type cycles, cross-module roots and fixed-length source replacement."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_unused_c_types import substitute

root = b"""
#![allow(dead_code, unused_imports)]
pub mod left;
pub mod right;
use crate::right::{Imported as Handle};
pub fn uses_handle(_: Handle) {}
pub fn qualified(_: crate::right::Visible) {}
"""
left = b"""
#[repr(C)] pub struct Duplicate { p: *const i32 }
pub fn takes_local(_: Duplicate) {}
#[repr(C)] pub struct Cycle { next: *mut Other }
#[repr(C)] pub struct Other { next: *mut Cycle }
pub type CycleAlias = Cycle;
#[repr(C)] pub struct Kept { ptr: *mut u8 }
macro_rules! retain { ($name:ident) => { pub fn retained(_: $name) {} }; }
retain!(Kept);
pub type Number = i32;
"""
right = b"""
#[repr(C)] pub struct Duplicate { p: *const i32 }
#[repr(C)] pub struct Visible { p: *mut i32 }
#[repr(C)] pub struct Imported { p: *mut i32 }
#[repr(C)] pub struct CallbackArg { p: *mut i32 }
pub type Callback = unsafe extern "C" fn(*mut CallbackArg);
pub extern "C" fn use_callback(_: Callback) {}
#[repr(transparent)] pub struct Wrapper(*mut i32);
"""
with TemporaryDirectory() as tmp:
    crate = Path(tmp)
    files = {"lib.rs": root, "left.rs": left, "right.rs": right}
    for name, data in files.items():
        (crate / name).write_bytes(data)
    compile_command = ["rustc", "--edition=2021", "--crate-type=lib", "--emit=metadata", "lib.rs"]
    subprocess.run(compile_command, cwd=crate, check=True)
    hashes = {name: sha256(data).hexdigest() for name, data in files.items()}
    changes, facts = substitute(crate, hashes)
    assert set(changes) == {"left.rs", "right.rs"}
    assert facts["removed_declarations"] == {"struct": 3, "type": 1}, facts
    assert facts["raw_pointer_types_removed"] == 3
    assert b"pub struct Duplicate" in changes["left.rs"] and b"pub struct Duplicate" not in changes["right.rs"]
    assert b"pub type Number" in changes["left.rs"] and b"pub struct Kept" in changes["left.rs"]
    for name, data in changes.items():
        assert len(data) == len(files[name]) and data.count(b"\n") == files[name].count(b"\n")
        (crate / name).write_bytes(data)
    subprocess.run(compile_command, cwd=crate, check=True)
    remaining, again = substitute(crate, {k: sha256((crate / k).read_bytes()).hexdigest() for k in files})
    assert not remaining and not again["raw_pointer_types_removed"]
print("Both crates compiled. Live layouts, macro uses, C callbacks and unrelated aliases survived the rewrite.")
