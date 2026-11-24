#!/usr/bin/env python3
"""Apply asserted ABI-preserving repairs to modernized IPRoute2 Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(path: Path, old: str, new: str, reason: str) -> dict[str, str]:
    text = path.read_text()
    if text.count(old) != 1 or new in text:
        raise RuntimeError(f"IPRoute2 repair anchor changed: {path}: {reason}")
    before = digest(path)
    path.write_text(text.replace(old, new, 1))
    return {
        "path": str(path),
        "reason": reason,
        "before_sha256": before,
        "after_sha256": digest(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output or output.is_symlink():
        raise RuntimeError("IPRoute2 finalizer requires distinct real directories")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output, ignore=shutil.ignore_patterns("target", "Cargo.lock"))

    changes = []
    changes.append(replace_once(
        output / "lib.rs",
        "#![allow(dead_code)]\n",
        "#![allow(dead_code)]\n#![allow(deref_nullptr)]\n",
        "permit C offsetof/container_of raw-address expressions without dereference",
    ))
    changes.append(replace_once(
        output / "src/ip/iplink_xdp.rs",
        """        return if details as ::core::ffi::c_int != 0 {
            0 as ::core::ffi::c_int
        } else {
            xdp_dump_json(&raw mut tb as *mut *mut rtattr)
        }
""",
        """        if details as ::core::ffi::c_int == 0 {
            xdp_dump_json(&raw mut tb as *mut *mut rtattr);
        }
        return;
""",
        "preserve C void conditional return",
    ))
    bpf = output / "src/lib/bpf_libbpf.rs"
    changes.append(replace_once(
        bpf,
        "                kernel_log_buf: 0,\n",
        "                kernel_log_buf: ::core::ptr::null_mut::<::core::ffi::c_char>(),\n",
        "represent zero-initialized libbpf pointer as a null pointer",
    ))
    changes.append(replace_once(
        bpf,
        "            init.set_c2rust_unnamed(::core::ptr::null::<::core::ffi::c_char>());\n",
        "            init.set_c2rust_unnamed(0 as __u32);\n",
        "represent libbpf anonymous 32-bit padding as zero",
    ))

    escape = output / "src/lib/escape.rs"
    escape_text = escape.read_text()
    pattern = re.compile(
        r"static mut ESC_tab: \[::core::ffi::c_uchar; 257\] = unsafe \{.*?\n\};\n"
        r"(?=unsafe extern \"C\" fn esc_all)",
        re.DOTALL,
    )
    match = pattern.search(escape_text)
    if match is None:
        raise RuntimeError("IPRoute2 ESC_tab repair anchor changed")
    literal = (
        "@..............................."
        "||||||||||||||||||||||||||||||||"
        "||||||||||||||||||||||||||||||||"
        "|||||||||||||||||||||||||||||||."
        "????????????????????????????????"
        "????????????????????????????????"
        "????????????????????????????????"
        "????????????????????????????????\\0"
    )
    replacement = (
        "static mut ESC_tab: [::core::ffi::c_uchar; 257] = unsafe {\n"
        "    ::core::mem::transmute::<[u8; 257], [::core::ffi::c_uchar; 257]>(\n"
        f'        *b"{literal}",\n'
        "    )\n"
        "};\n"
    )
    before = digest(escape)
    escape.write_text(pattern.sub(lambda _match: replacement, escape_text, count=1))
    changes.append({
        "path": str(escape),
        "reason": "preserve C string initializer as one 257-byte array",
        "before_sha256": before,
        "after_sha256": digest(escape),
    })

    changes.append(replace_once(
        output / "src/lib/utils.rs",
        "::f128::f128::new(t) == ::core::f64::INFINITY",
        "::f128::f128::new(t) == ::f128::f128::new(::core::f64::INFINITY)",
        "promote both operands for the C double/long-double infinity comparison",
    ))
    for relative in ("src/tc/q_fq.rs", "src/tc/q_netem.rs"):
        path = output / relative
        changes.append(replace_once(
            path,
            "_min1 as ::core::ffi::c_ulong\n",
            "_min1 as usize\n",
            "spell x86_64 c_ulong byte count as Rust slice length",
        ))
        changes.append(replace_once(
            path,
            "_min2 as ::core::ffi::c_ulong\n",
            "_min2 as usize\n",
            "spell x86_64 c_ulong byte count as Rust slice length",
        ))

    for change in changes:
        change["path"] = str(Path(change["path"]).relative_to(output))
    manifest = {
        "schema": 1,
        "repairs": len(changes),
        "files": len({change["path"] for change in changes}),
        "changes": changes,
    }
    (output / "rustbox-iproute2-finalization.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"repairs": len(changes), "files": manifest["files"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
