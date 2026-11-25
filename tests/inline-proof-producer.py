#!/usr/bin/env python3
"""Recompute the E2fsprogs inline parent keys consumed by the pinned declaration receipts."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = json.loads((ROOT / "batches/e2fsprogs-foreign-declarations.json").read_bytes())
tool = (ROOT / "work/analysis/private-inlines-linux/release/rustbox-inline-audit").read_bytes()
driver = (ROOT / "scripts/prune_private_inlines.py").read_bytes()
if not rows:
    raise ValueError("no pinned E2fsprogs parents")
for key, record in rows.items():
    archive = ROOT / key
    archive_hash = sha256(archive.read_bytes()).hexdigest()
    manifest = json.loads(archive.with_suffix(".sources.json").read_bytes())
    foreign = archive.with_name(record["file"]).read_bytes()
    if sha256(foreign).hexdigest() != record["sha256"] or archive_hash != manifest["archive_sha256"]:
        raise ValueError(f"unexpected archive or foreign declarations: {key}")
    parent = json.loads(foreign)["parent"]
    fingerprint = sha256((manifest["build_key"] + archive_hash).encode() + tool + driver).hexdigest()
    proof = archive.with_suffix(f".inlines-{fingerprint}.json")
    if proof.name != parent["file"] or sha256(proof.read_bytes()).hexdigest() != parent["sha256"]:
        raise ValueError(f"compiled inline checker selected a different parent: {key}")
print(f"Verified the Linux checker against all {len(rows)} E2fsprogs declaration parents.")
