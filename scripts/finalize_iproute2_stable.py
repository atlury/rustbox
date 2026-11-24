#!/usr/bin/env python3
"""Apply asserted ABI-preserving repairs to modernized IPRoute2 Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


PROGRAMS = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
PROGRAM_REPAIR_FILES = {
    program: {"lib.rs", "src/lib/utils.rs"} for program in PROGRAMS
}
PROGRAM_REPAIR_FILES["ip"] |= {
    "src/ip/iplink_xdp.rs",
    "src/lib/bpf_libbpf.rs",
}
PROGRAM_REPAIR_FILES["ss"].add("src/lib/escape.rs")
PROGRAM_REPAIR_FILES["tc"] |= {
    "src/lib/bpf_libbpf.rs",
    "src/tc/q_fq.rs",
    "src/tc/q_netem.rs",
}
ALL_REPAIR_FILES = set().union(*PROGRAM_REPAIR_FILES.values())


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
    parser.add_argument("--program", choices=PROGRAMS)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output or output.is_symlink():
        raise RuntimeError("IPRoute2 finalizer requires distinct real directories")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output, ignore=shutil.ignore_patterns("target", "Cargo.lock"))

    expected_files = (
        PROGRAM_REPAIR_FILES[args.program] if args.program else ALL_REPAIR_FILES
    )
    present_files = {
        relative for relative in ALL_REPAIR_FILES if (output / relative).is_file()
    }
    if present_files != expected_files:
        raise RuntimeError(
            "IPRoute2 repair file inventory changed: "
            f"program={args.program or 'monolithic'} "
            f"expected={sorted(expected_files)} present={sorted(present_files)}"
        )

    changes = []
    changes.append(replace_once(
        output / "lib.rs",
        "#![allow(dead_code)]\n",
        "#![allow(dead_code)]\n#![allow(deref_nullptr)]\n",
        "permit C offsetof/container_of raw-address expressions without dereference",
    ))
    if "src/ip/iplink_xdp.rs" in expected_files:
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
    if "src/lib/bpf_libbpf.rs" in expected_files:
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

    if "src/lib/escape.rs" in expected_files:
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
    for relative in sorted(expected_files & {"src/tc/q_fq.rs", "src/tc/q_netem.rs"}):
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
        "program": args.program,
        "expected_repair_files": sorted(expected_files),
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
