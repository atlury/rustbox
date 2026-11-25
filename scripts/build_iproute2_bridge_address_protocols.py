#!/usr/bin/env python3
"""Rebuild the custom IPRoute2 bridge engine using its own compiler command and original source receipts."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import compile_staged, source_list_digest
from check_next_inline_layer import apply_receipt
from e2fsprogs_foreign_declarations import read_proof, staged_compiler_inputs
from stage_iproute2_address_protocols import MODULE, replace_table

BRIDGE = Path("work/analysis/iproute2-7.3.0/program-translations/rustbox-bridge/libbridge_audit.a")


def compile_bridge(link, output):
    key = str(BRIDGE)
    archive = output / BRIDGE.name
    with tempfile.TemporaryDirectory() as tmp:
        crate, inputs, rustc = staged_compiler_inputs(link, BRIDGE, Path(tmp))
        receipt = link["linked_foreign_declaration_proofs"][key]
        apply_receipt(crate, read_proof(link, BRIDGE, receipt)["declarations"], inputs)
        sources = {n: digest(crate / n) for n in inputs}
        parent = compile_staged(crate, inputs, rustc, archive)
        if parent != link["source_library_sha256"][key]:
            raise ValueError("bridge control failed to reproduce the actual linked archive")
        module = crate / MODULE
        after, changes = replace_table(module.read_bytes())
        module.write_bytes(after)
        candidate = compile_staged(crate, inputs, rustc, archive)
        if candidate == parent:
            raise ValueError("bridge live conversion did not change the archive")
        record = dict(changes, archive=key, candidate_sha256=candidate, control_sha256=parent,
                      control_binary_sha256=link["binary"]["sha256"], compiler_selected_sources=len(inputs),
                      parent_sources_sha256=source_list_digest(sources),
                      candidate_sources_sha256=source_list_digest({n: digest(crate / n) for n in inputs}))
        (output / "pilot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record


def build_bridge_trial(output, link):
    output = output.resolve()
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        scratch = Path(tmp)
        (scratch / "control.json").write_text(json.dumps(link))
        result = scratch / "result"
        result.mkdir()
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{scratch}:/trial", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", "/work/scripts/build_iproute2_bridge_address_protocols.py",
                        "/trial/control.json", "/trial/result"], check=True)
        result.rename(output)


if __name__ == "__main__":
    compile_bridge(json.loads(Path(sys.argv[1]).read_bytes()), Path(sys.argv[2]))
