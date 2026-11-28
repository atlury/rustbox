#!/usr/bin/env python3
"""Exercise the transformed C-variadic ABI with integer, floating-point and byte-string arguments."""
# SPDX-License-Identifier: 0BSD
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_variadic_ffi import substitute
from check_cargo_private_inlines import digest

def main():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "lib.rs").write_text('pub mod left;\npub mod right;\nfn main() { left::check(); right::check(); }\n')
        for name in ("left", "right"):
            (root / (name + ".rs")).write_text(r'''
extern "C" {
    fn snprintf(dst: *mut ::core::ffi::c_char, len: usize, format: *const ::core::ffi::c_char, ...) -> i32;
}
pub fn check() {
    let mut result = [0_i8; 32];
    let data = [0xff_u8, 0];
    let n = unsafe { snprintf(result.as_mut_ptr(), result.len(), c"%u:%.1f:%s".as_ptr(),
                              17_u32, 1.25_f64, data.as_ptr()) };
    assert_eq!(n, 8);
    let got: Vec<u8> = result[..=n as usize].iter().map(|c| *c as u8).collect();
    assert_eq!(got, b"17:1.2:\xff\0");
}
''')
        def run():
            subprocess.run(["rustc", "--edition=2021", "lib.rs", "-o", "test"], cwd=root, check=True)
            subprocess.run([root / "test"], cwd=root, check=True)
        run()
        inputs = {p.name:digest(p) for p in root.glob("*.rs")}
        changed, facts = substitute(root, inputs)
        assert facts["raw_pointer_types_removed"] == 2 and facts["variadic_ffi"]["snprintf"]["copies"] == 2
        for name, data in changed.items():
            (root / name).write_bytes(data)
        run()
    print("Both callers retained the C variadic ABI and produced identical formatted bytes.")

if __name__ == "__main__":
    main()
