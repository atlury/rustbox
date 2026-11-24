#!/usr/bin/env python3
"""Create deterministic multicall-entrypoint normalization for IPRoute2."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ENTRYPOINTS = {
    "arpd": ("misc/arpd.c", "int main(int argc, char **argv)"),
    "bridge": ("bridge/bridge.c", "int\nmain(int argc, char **argv)"),
    "dcb": ("dcb/dcb.c", "int main(int argc, char **argv)"),
    "devlink": ("devlink/devlink.c", "int main(int argc, char **argv)"),
    "dpll": ("dpll/dpll.c", "int main(int argc, char **argv)"),
    "genl": ("genl/genl.c", "int main(int argc, char **argv)"),
    "ifstat": ("misc/ifstat.c", "int main(int argc, char *argv[])"),
    "ip": ("ip/ip.c", "int main(int argc, char **argv)"),
    "lnstat": ("misc/lnstat.c", "int main(int argc, char **argv)"),
    "netshaper": ("netshaper/netshaper.c", "int main(int argc, char **argv)"),
    "nstat": ("misc/nstat.c", "int main(int argc, char *argv[])"),
    "rdma": ("rdma/rdma.c", "int main(int argc, char **argv)"),
    "rtacct": ("misc/rtacct.c", "int main(int argc, char *argv[])"),
    "rtmon": ("ip/rtmon.c", "int\nmain(int argc, char **argv)"),
    "ss": ("misc/ss.c", "int main(int argc, char *argv[])"),
    "tc": ("tc/tc.c", "int main(int argc, char **argv)"),
    "tipc": ("tipc/tipc.c", "int main(int argc, char *argv[])"),
    "vdpa": ("vdpa/vdpa.c", "int main(int argc, char **argv)"),
}

# C2Rust 0.22.1 cannot import Clang's AST for GNU's omitted-middle
# conditional operator.  Spell this single-evaluation expression out in
# standard C without changing its observable behavior.
C2RUST_NORMALIZATIONS = {
    "lib/utils.c": (
        '\t\tp = getenv("PROC_ROOT") ? : "/proc";\n',
        '\t\tconst char *proc_root = getenv("PROC_ROOT");\n'
        '\t\tp = proc_root ? proc_root : "/proc";\n',
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/iproute2-7.3.0"
    state = json.loads((root / "work/upstream/.state/iproute2.json").read_text())
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["iproute2"]
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("canonical IPRoute2 source is not signature-verified")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(canonical, output, symlinks=True)

    transformations = []
    for program, (relative, signature) in ENTRYPOINTS.items():
        source = output / relative
        text = source.read_text()
        exported = f"rustbox_iproute2_{program}_main"
        if text.count(signature) != 1 or exported in text:
            raise RuntimeError(f"IPRoute2 entrypoint signature changed: {program}")
        before = sha256(source)
        replacement = signature.replace("main", exported, 1)
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            f"\treturn {exported}(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        source.write_text(text.replace(signature, replacement, 1) + wrapper)
        transformations.append({
            "path": relative,
            "entrypoint": exported,
            "before_sha256": before,
            "after_sha256": sha256(source),
            "kind": "export entrypoint and retain standalone wrapper",
        })

    for relative, (original, replacement) in C2RUST_NORMALIZATIONS.items():
        source = output / relative
        text = source.read_text()
        if text.count(original) != 1 or replacement in text:
            raise RuntimeError(f"IPRoute2 C2Rust normalization anchor changed: {relative}")
        before = sha256(source)
        source.write_text(text.replace(original, replacement, 1))
        transformations.append({
            "path": relative,
            "before_sha256": before,
            "after_sha256": sha256(source),
            "kind": "expand GNU omitted-middle conditional with single evaluation",
        })

    manifest = {
        "schema": 1,
        "release": "7.3.0",
        "source_sha256": release["sha256"],
        "source_signature_verified": True,
        "engines": len(ENTRYPOINTS),
        "public_names": 21,
        "transformations": transformations,
    }
    (output / ".rustbox-normalization.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"engines": len(ENTRYPOINTS), "changes": len(transformations)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
