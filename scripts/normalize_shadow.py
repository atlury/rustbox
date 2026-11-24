#!/usr/bin/env python3
"""Create deterministic multicall-entrypoint normalization for Shadow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SIGNATURES = {
    "chage": ("int main (int argc, char **argv)",),
    "chfn": ("int main (int argc, char **argv)",),
    "chgpasswd": ("int main (int argc, char **argv)",),
    "chpasswd": ("int main (int argc, char **argv)",),
    "chsh": ("int main (int argc, char **argv)",),
    "faillog": ("int main (int argc, char **argv)",),
    "getsubids": ("int main(int argc, char *argv[])",),
    "gpasswd": ("int main (int argc, char **argv)",),
    "groupadd": ("int main (int argc, char **argv)",),
    "groupdel": ("int main (int argc, char **argv)",),
    "groupmod": ("int main (int argc, char **argv)",),
    "grpck": ("int main (int argc, char **argv)",),
    "grpconv": (
        "int main (int argc, char **argv)",
        "int\nmain(MAYBE_UNUSED int _1, char **argv)",
    ),
    "grpunconv": (
        "int main (int argc, char **argv)",
        "int\nmain(MAYBE_UNUSED int _1, char **argv)",
    ),
    "lastlog": ("int main (int argc, char **argv)",),
    "login": ("int main (int argc, char **argv)",),
    "newgidmap": ("int main(int argc, char **argv)",),
    "newgrp": ("int main (int argc, char **argv)",),
    "newuidmap": ("int main(int argc, char **argv)",),
    "newusers": ("int main (int argc, char **argv)",),
    "nologin": ("int main (void)",),
    "passwd": ("int\nmain(int argc, char **argv)",),
    "pwck": ("int main (int argc, char **argv)",),
    "pwconv": ("int main (int argc, char **argv)",),
    "pwunconv": ("int main (int argc, char **argv)",),
    "su": ("int main (int argc, char **argv)",),
    "useradd": ("int main (int argc, char **argv)",),
    "userdel": ("int main (int argc, char **argv)",),
    "usermod": ("int main (int argc, char **argv)",),
    "vipw": ("int main (int argc, char **argv)",),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/shadow-4.20.4"
    state = json.loads((root / "work/upstream/.state/shadow.json").read_text())
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["shadow"]
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("canonical Shadow source is not signature-verified")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(canonical, output, symlinks=True)

    transformations = []
    for program, signatures in SIGNATURES.items():
        source = output / f"src/{program}.c"
        text = source.read_text()
        exported = f"rustbox_shadow_{program}_main"
        before = sha256(source)
        definitions = 0
        for signature in signatures:
            if text.count(signature) != 1:
                raise RuntimeError(f"Shadow entrypoint signature changed: {program}: {signature!r}")
            if program == "nologin":
                replacement = f"int {exported} (int argc, char **argv)"
            else:
                replacement = signature.replace("main", exported, 1)
            text = text.replace(signature, replacement, 1)
            definitions += 1
        if exported in source.read_text():
            raise RuntimeError(f"Shadow exported entrypoint already exists: {program}")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            f"\treturn {exported}(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        source.write_text(text + wrapper)
        transformations.append({
            "path": f"src/{program}.c",
            "entrypoint": exported,
            "conditional_definitions": definitions,
            "before_sha256": before,
            "after_sha256": sha256(source),
            "kind": "export entrypoint and retain standalone wrapper",
        })

    manifest = {
        "schema": 1,
        "release": "4.20.4",
        "canonical_sha256": release["sha256"],
        "entrypoint_engines": len(SIGNATURES),
        "public_programs": 32,
        "aliases": {"sg": "newgrp", "vigr": "vipw"},
        "transformations": transformations,
    }
    manifest_path = output / "rustbox-normalization.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "entrypoints": len(SIGNATURES),
        "programs": 32,
        "transformations": len(transformations),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
