#!/usr/bin/env python3
"""Strict release receipts must bind every input and use the original source layout policy."""
# SPDX-License-Identifier: 0BSD

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_cargo_private_inlines as verifier
import prune_private_inlines


class RebuildRequired(Exception):
    pass


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    relative = Path("work/analysis/inetutils-2.8/program-translations/cargo-target/release/libdemo_audit.a")
    source, _ = verifier.layout(relative)
    crate, archive = root / source, root / relative
    archive.parent.mkdir(parents=True)
    crate.mkdir(parents=True)
    archive.write_bytes(b"test archive")
    archive.with_suffix(".d").write_text(f"demo: /work/{source}/lib.rs\n")
    inputs = ("Cargo.lock", "Cargo.toml", "lib.rs", "rust-toolchain.toml")
    for name in inputs:
        (crate / name).write_bytes(name.encode())
    (root / "scripts").mkdir()
    for name in ("prune_private_inlines.py", "inline_source_layout.py", "syntax"):
        (root / "scripts" / name).write_bytes(name.encode())
    tool = root / "scripts/syntax"
    expected = verifier.digest(archive)

    with patch.object(verifier, "ROOT", root), patch.object(prune_private_inlines, "TOOL", tool), \
         patch.object(verifier.subprocess, "run", side_effect=RebuildRequired):
        for producer in verifier.STRICT_VERIFIERS:
            h = hashlib.sha256()
            for sha in (producer, verifier.digest(root / "scripts/prune_private_inlines.py"),
                        verifier.digest(tool), expected):
                h.update(bytes.fromhex(sha))
            for name in sorted(inputs):
                h.update(str(source / name).encode() + b"\0" + bytes.fromhex(verifier.digest(crate / name)))
            key = h.hexdigest()
            proof = archive.with_suffix(f".inlines-{key}.json")
            record = {"key": key, "archive_sha256": expected, "ranges": {}, "sources": {}}
            proof.write_text(json.dumps(record))
            assert verifier.check_linux_cargo(relative, True)["sha256"] == verifier.digest(proof)
            proof.write_text(json.dumps(dict(record, source_layout="byte_offsets")))
            try:
                verifier.check_linux_cargo(relative, True)
            except ValueError:
                pass
            else:
                raise AssertionError("strict producer accepted a layout it never verified")
            proof.write_text(json.dumps(record))
            (crate / "lib.rs").write_bytes(b"changed")
            try:
                verifier.check_linux_cargo(relative, True)
            except RebuildRequired:
                pass
            else:
                raise AssertionError("strict receipt was reused after source changed")
            (crate / "lib.rs").write_bytes(b"lib.rs")
            proof.unlink()
        # The later producer binds the padding helper as well as the syntax tool.
        key_inputs = bytes.fromhex(verifier.OFFSET_VERIFIER)
        helper = root / "scripts/inline_source_layout.py"
        for path in (helper, root / "scripts/prune_private_inlines.py", tool, archive):
            key_inputs += bytes.fromhex(verifier.digest(path))
        for name in sorted(inputs):
            key_inputs += str(source / name).encode() + b"\0" + bytes.fromhex(verifier.digest(crate / name))
        key = hashlib.sha256(key_inputs).hexdigest()
        proof = archive.with_suffix(f".inlines-{key}.json")
        record = {"key": key, "archive_sha256": expected, "ranges": {}, "sources": {},
                  "source_layout": "byte_offsets"}
        proof.write_text(json.dumps(record))
        assert verifier.check_linux_cargo(relative, True)["sha256"] == verifier.digest(proof)
        proof.write_text(json.dumps(dict(record, source_layout="unknown")))
        try:
            verifier.check_linux_cargo(relative, True)
        except ValueError:
            pass
        else:
            raise AssertionError("unknown layout accepted")
        proof.write_text(json.dumps(record))
        helper.write_bytes(b"changed")
        try:
            verifier.check_linux_cargo(relative, True)
        except RebuildRequired:
            pass
        else:
            raise AssertionError("old offset receipt accepted after the padding implementation changed")
print("Previous release receipts bind their inputs and accept only verified layouts.")
