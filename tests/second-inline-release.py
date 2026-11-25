#!/usr/bin/env python3
"""Cold and warm release preparation must select the same archive and parent receipt."""
# SPDX-License-Identifier: 0BSD
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_second_inline_layers as release


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    work = root / "work/analysis"
    work.mkdir(parents=True)
    config = root / "batches"
    config.mkdir()
    args = config / "archives.args"
    cargo = Path("work/analysis/example-1/translations/c2rust/example/target/release/libexample.a")
    grouped = Path("work/analysis/iproute2-1/program-translations/cargo-target/ip/release/libip_audit.a")
    args.write_text(f"--example-rust-library=/work/{cargo}\n")
    parent = {"file": "parent.json", "sha256": "parent-checksum"}
    parents = {str(path): parent for path in (cargo, grouped)}
    records, data = {}, {}
    for package, path in (("example", cargo), ("iproute2", grouped)):
        file = root / path
        file.parent.mkdir(parents=True)
        file.write_bytes(b"same release archive")
        sha = release.digest(file)
        (work / f"{package}-cargo-inline-proofs.json").write_text(json.dumps({str(path): parent}))
        data[path] = json.dumps({"archive": str(path), "parent": parent, "archive_sha256": sha,
                                 "private_functions_removed": 1, "raw_pointer_type_tokens_removed": 3,
                                 "second_layer": {"archive_sha256": sha, "ranges": {"lib.rs": [[1, 2]]}}}).encode()
        key = hashlib.sha256(data[path]).hexdigest()
        records[str(path)] = {"file": file.with_suffix(f".layer2-{key}.json").name, "sha256": key}
    (config / "multicall-second-inline-proofs.json").write_text(json.dumps(records))

    def produce(link, archive, *, publish, expected_receipt):
        assert publish and expected_receipt == records[str(archive)]
        assert link["linked_private_inline_proofs"][str(archive)] == parent
        (root / archive).with_name(expected_receipt["file"]).write_bytes(data[archive])

    with patch.object(release, "ROOT", root), patch.object(release, "check_layer", side_effect=produce) as compiler:
        release.prepare(records, args)
        assert compiler.call_count == 2
        compiler.reset_mock()
        release.prepare(records, args)
        compiler.assert_not_called()
        hashes = {n: release.digest(root / n) for n in records}
        assert release.linked_layers(root, parents, hashes) == records
        for stale in (dict(parents, **{str(cargo): {"file": "different"}}),
                      {str(cargo): parent}):
            try:
                release.linked_layers(root, stale, hashes)
            except ValueError:
                pass
            else:
                raise AssertionError("accepted a stale parent")
        manifest = config / "multicall-second-inline-proofs.json"
        manifest.write_text("{}")
        link = root / "before.json"
        link.write_text(json.dumps({"source_library_sha256": {n: release.digest(root / n) for n in records},
                                    "linked_private_inline_proofs": parents}))
        batches = root / "results.json"
        ready = {n: {"status": "verified", "helpers": 1, "pointers": 3, "receipt": r}
                 for n, r in records.items()}
        for entry in (dict(ready[str(grouped)], status="pending"), dict(ready[str(grouped)], pointers=4)):
            batches.write_text(json.dumps({"link_sha256": release.digest(link),
                                          "archives": dict(ready, **{str(grouped): entry})}))
            try:
                release.enroll(root, link, [batches])
            except ValueError:
                pass
            else:
                raise AssertionError("enrolled an incomplete or inconsistent batch")
            assert manifest.read_text() == "{}"
        batches.write_text(json.dumps({"link_sha256": release.digest(link), "archives": ready}))
        release.enroll(root, link, [batches])
        assert release.manifest(root) == records
        (root / grouped).write_bytes(b"changed archive")
        try:
            release.prepare(records, args)
        except ValueError:
            pass
        else:
            raise AssertionError("reused a receipt for a different archive")
print("Single-crate and grouped release preparation, cache reuse, stale archives and changed parents passed.")
