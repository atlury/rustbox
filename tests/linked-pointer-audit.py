#!/usr/bin/env python3
"""Private-inline audits replay into scratch even when reading original Cargo inputs."""
# SPDX-License-Identifier: 0BSD

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_linked_pointers as inventory


def sha(data):
    return hashlib.sha256(data).hexdigest()


with tempfile.TemporaryDirectory() as workspace:
    root = Path(workspace)
    package = Path("work/analysis/example/program-translations")
    crate = package / "demo/demo-final"
    archive = package / "cargo-target/demo/release/libdemo_audit.a"
    (root / crate).mkdir(parents=True)
    (root / crate / "Cargo.toml").write_text('[package]\nname = "demo"\n')
    source = root / crate / "lib.rs"
    original = b"#[inline]\nfn unused(_: *mut u8) {}\npub fn keep() {}\n"
    source.write_bytes(original)
    end = original.index(b"\npub")
    final = b"\n" + original[end:]
    built = root / archive
    built.parent.mkdir(parents=True)
    built.write_bytes(b"fixture")
    built.with_suffix(".d").write_text(f"archive: /work/{crate}/lib.rs\n")
    proof_file = built.with_suffix(".proof.json")
    proof = {"archive_sha256": sha(built.read_bytes()), "ranges": {"lib.rs": [[0, end]]},
             "sources": {"lib.rs": sha(final)}}
    with patch.object(inventory, "ROOT", root):
        for field, layout, valid in (("e2fsprogs_inline_proofs", "lines", True),
                                     ("linked_private_inline_proofs", "lines", True),
                                     ("linked_private_inline_proofs", "byte_offsets", True),
                                     ("linked_private_inline_proofs", "byte_offsets", False)):
            expected = final
            if layout == "byte_offsets":
                proof["source_layout"] = layout
                expected = bytes(c if c in b" \t\r\n" else 32 for c in original[:end]) + original[end:]
            proof["sources"]["lib.rs"] = sha(expected if valid else b"stale")
            proof_file.write_text(json.dumps(proof))
            link = {"binary": {"sha256": "fixture"}, "source_library_sha256": {str(archive): proof["archive_sha256"]},
                    field: {str(archive): {"file": proof_file.name,
                                          "sha256": sha(proof_file.read_bytes())}}}
            with tempfile.TemporaryDirectory() as scratch:
                try:
                    result = inventory.audit(link, Path(scratch))
                except ValueError as error:
                    if valid or "restaged source differs" not in str(error):
                        raise
                else:
                    assert valid
                    assert result["all"]["raw_pointer_type_tokens"] == 0
                    cleanup = result["byte_identical_inline_cleanups"]["demo"]
                    assert cleanup["raw_pointer_type_tokens_removed"] == 1
                    assert cleanup["source_bytes_removed"] == len(original) - len(expected)
                    assert cleanup.get("source_layout", "lines") == layout
            assert source.read_bytes() == original
print("Repeated and rejected audit replays both preserved the original Cargo source.")

with tempfile.TemporaryDirectory() as workspace:
    root = Path(workspace)
    package = Path("work/analysis/e2fsprogs-test/program-translations")
    archive = package / "rustbox-e2fsprogs-shared/bitcount.o"
    obj = root / archive
    obj.parent.mkdir(parents=True)
    obj.write_bytes(b"test object")
    source = Path("compat/e2fsprogs/bitcount.rs")
    (root / source).parent.mkdir(parents=True)
    (root / source).write_text("pub fn count(_: *const u8) {}\n")
    checksum = sha(obj.read_bytes())
    manifest = {"archive_sha256": checksum, "sources": {str(source): sha((root / source).read_bytes())}}
    obj.with_suffix(".sources.json").write_text(json.dumps(manifest))
    link = {"binary": {"sha256": "fixture"}, "source_library_sha256": {str(archive): checksum}}
    with patch.object(inventory, "ROOT", root), tempfile.TemporaryDirectory() as scratch:
        measured = inventory.audit(link, Path(scratch))["all"]
        assert measured["standalone_objects"] == measured["files"] == measured["raw_pointer_type_tokens"] == 1
        (root / source).write_text("pub fn count(_: &[u8]) {}\n")
        try:
            inventory.audit(link, Path(scratch))
        except ValueError as error:
            if "restaged source differs" not in str(error):
                raise
        else:
            raise AssertionError("bitmap provider source changed without invalidating the release audit")
print("The shared bitmap provider is counted once and its source digest is checked.")
