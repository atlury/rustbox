#!/usr/bin/env python3
"""Stage XZ Utils with deterministic, translation-friendly entrypoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f"XZ {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def append_wrapper(path: Path, entry: str) -> None:
    path.write_text(path.read_text() + (
        "\n#ifndef RUSTBOX_MULTICALL\n"
        "int main(int argc, char **argv)\n"
        "{\n"
        f"\treturn {entry}(argc, argv);\n"
        "}\n"
        "#endif\n"
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/xz-5.8.4"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["xz"]
    state = json.loads((repository / "work/upstream/.state/xz.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"XZ source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical XZ signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        xz_main = staged / "src/xz/main.c"
        replace_once(xz_main, "int\nmain(int argc, char **argv)\n{",
                     "int\nrustbox_xz_main(int argc, char **argv)\n{",
                     "xz entrypoint")
        append_wrapper(xz_main, "rustbox_xz_main")

        lzmainfo = staged / "src/lzmainfo/lzmainfo.c"
        replace_once(lzmainfo, "extern int\nmain(int argc, char **argv)\n{",
                     "extern int\nrustbox_lzmainfo_main(int argc, char **argv)\n{",
                     "lzmainfo entrypoint")
        append_wrapper(lzmainfo, "rustbox_lzmainfo_main")

        xzdec = staged / "src/xzdec/xzdec.c"
        replace_once(
            xzdec,
            "int\nmain(int argc, char **argv)\n{",
            "#ifdef LZMADEC\n"
            "# define RUSTBOX_XZDEC_ENTRY rustbox_lzmadec_main\n"
            "#else\n"
            "# define RUSTBOX_XZDEC_ENTRY rustbox_xzdec_main\n"
            "#endif\n\n"
            "int\nRUSTBOX_XZDEC_ENTRY(int argc, char **argv)\n{",
            "xzdec personalities",
        )
        append_wrapper(xzdec, "RUSTBOX_XZDEC_ENTRY")

        canonical_files = {path.relative_to(canonical).as_posix()
                           for path in canonical.rglob("*") if path.is_file()}
        staged_files = {path.relative_to(staged).as_posix()
                        for path in staged.rglob("*") if path.is_file()}
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed XZ source-tree files")
        changed = sorted(name for name in canonical_files
                         if sha256(canonical / name) != sha256(staged / name))
        expected = ["src/lzmainfo/lzmainfo.c", "src/xz/main.c", "src/xzdec/xzdec.c"]
        if changed != expected:
            raise RuntimeError(f"unexpected XZ normalized sources: {changed}")

        operations = {
            "src/xz/main.c": "export rustbox_xz_main and retain a conditional standalone main wrapper",
            "src/xzdec/xzdec.c": "export distinct xzdec and lzmadec personality entrypoints and retain conditional standalone wrappers",
            "src/lzmainfo/lzmainfo.c": "export rustbox_lzmainfo_main and retain a conditional standalone main wrapper",
        }
        manifest = {
            "schema": 1, "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed, "entrypoints": 4,
            "conditional": "RUSTBOX_MULTICALL",
            "compiler_normalization": "--disable-clmul-crc selects upstream portable CRC C instead of optional x86 CLMUL intrinsics",
            "engine": "exact deterministic source rewrite",
            "transformations": [{
                "source": name, "canonical_sha256": sha256(canonical / name),
                "normalized_sha256": sha256(staged / name), "operation": operations[name],
            } for name in changed],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoints": 4}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
