#!/usr/bin/env python3
"""Stage GNU Findutils with defined arithmetic and multicall entrypoints."""

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
        raise RuntimeError(f"Findutils {label} precondition failed in {path}")
    path.write_text(text.replace(old, new))


def export_entrypoint(path: Path, name: str) -> None:
    replace_once(
        path,
        "int\nmain (int argc, char **argv)\n{",
        f"int\nrustbox_{name}_main (int argc, char **argv)\n{{",
        f"{name} multicall entrypoint",
    )
    with path.open("a") as output:
        output.write(
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\nmain (int argc, char **argv)\n"
            "{\n"
            f"  return rustbox_{name}_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        )


def normalize_long_double_uintmax(path: Path) -> None:
    """Spell one same-range cast in a form C2Rust can represent on LP64."""
    replace_once(
        path,
        "#include <locale.h>\n",
        "#include <limits.h>\n#include <locale.h>\n",
        "human-number limits include",
    )
    replace_once(
        path,
        "      uintmax_t u = value;\n",
        "#if UINTMAX_MAX == ULONG_MAX\n"
        "      unsigned long u = value;\n"
        "#else\n"
        "      uintmax_t u = value;\n"
        "#endif\n",
        "human-number same-range cast",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/findutils-4.10.0"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["findutils"]
    state = json.loads((repository / "work/upstream/.state/findutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Findutils source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical Findutils signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        locate_relative = "locate/locate.c"
        path = staged / locate_relative
        before = path.read_text()
        old = """  register short x;

  x = (signed char) fgetc (fp) << 8;
  x |= (fgetc (fp) & 0xff);
  return x;
"""
        new = """  int high = fgetc (fp) & 0xff;
  int low = fgetc (fp) & 0xff;
  int value = high * 256 + low;

  return value >= 0x8000 ? value - 0x10000 : value;
"""
        if before.count(old) != 1:
            raise RuntimeError("Findutils signed-prefix precondition failed")
        path.write_text(before.replace(old, new))
        entrypoints = {
            "find/ftsfind.c": "find",
            "xargs/xargs.c": "xargs",
            "locate/locate.c": "locate",
            "locate/frcode.c": "frcode",
        }
        for relative, name in entrypoints.items():
            export_entrypoint(staged / relative, name)
        human_relative = "gl/lib/human.c"
        normalize_long_double_uintmax(staged / human_relative)

        canonical_files = {
            item.relative_to(canonical).as_posix()
            for item in canonical.rglob("*") if item.is_file()
        }
        normalized_files = {
            item.relative_to(staged).as_posix()
            for item in staged.rglob("*") if item.is_file()
        }
        if canonical_files != normalized_files:
            raise RuntimeError("normalization changed the Findutils file set")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = sorted([*entrypoints, human_relative])
        if changed != expected_changed:
            raise RuntimeError(f"unexpected normalized Findutils sources: {changed}")
        operations = {
            "find/ftsfind.c": "export rustbox_find_main and retain a conditional standalone wrapper",
            "xargs/xargs.c": "export rustbox_xargs_main and retain a conditional standalone wrapper",
            "locate/frcode.c": "export rustbox_frcode_main and retain a conditional standalone wrapper",
            human_relative: (
                "on targets where uintmax_t and unsigned long have the same range, make the "
                "existing long-double conversion's unsigned-long type explicit"
            ),
        }
        manifest = {
            "schema": 1,
            "release": "4.10.0",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoints": 4,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [
                {
                    "source": name,
                    "canonical_sha256": sha256(canonical / name),
                    "normalized_sha256": sha256(staged / name),
                    "operation": operations.get(
                        name,
                        "decode the signed 16-bit big-endian prefix with defined arithmetic and "
                        "export rustbox_locate_main with a conditional standalone wrapper",
                    ),
                    **({
                        "semantic_basis": (
                            "high and low are bytes; high*256+low constructs the unsigned 16-bit "
                            "value, and subtracting 65536 above 0x7fff yields the same signed value "
                            "without left-shifting a negative operand or relying on "
                            "unsigned-to-short conversion"
                        ),
                    } if name == locate_relative else ({
                        "semantic_basis": (
                            "UINTMAX_MAX == ULONG_MAX proves the selected conversion has the "
                            "same range and C conversion semantics; other targets retain the "
                            "canonical cast"
                        ),
                    } if name == human_relative else {})),
                }
                for name in changed
            ],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": changed, "entrypoints": 4,
                      "undefined_behavior": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
