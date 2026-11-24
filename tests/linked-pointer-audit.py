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
        for field, valid in (("e2fsprogs_inline_proofs", True),
                             ("linked_private_inline_proofs", True),
                             ("linked_private_inline_proofs", False)):
            if not valid:
                proof["sources"]["lib.rs"] = sha(b"stale")
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
                    assert result["byte_identical_inline_cleanups"]["demo"]["raw_pointer_type_tokens_removed"] == 1
            assert source.read_bytes() == original
print("Repeated and rejected audit replays both preserved the original Cargo source.")
