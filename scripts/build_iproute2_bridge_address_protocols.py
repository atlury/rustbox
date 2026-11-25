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


def compile_bridge(link, output, route_names=False, netlink_protocols=False):
    key = str(BRIDGE)
    archive = output / BRIDGE.name
    if netlink_protocols:
        from iproute2_route_name_archives import candidate_path as route_path, verified_records
        route_parent = verified_records(link, link["iproute2_route_names"])[key]
        if digest(ROOT / route_path(route_parent)) != route_parent["candidate_sha256"]:
            raise ValueError("bridge netlink parent differs from linked archive")
    if route_names or netlink_protocols:
        from iproute2_address_protocol_archive import candidate_path, control_view, selected_records
        parent_record = selected_records(link)[key]
        linked_parent = ROOT / candidate_path(parent_record)
        if digest(linked_parent) != parent_record["candidate_sha256"]:
            raise ValueError("bridge route-name parent differs from linked archive")
        link = control_view(link)
    with tempfile.TemporaryDirectory() as tmp:
        crate, inputs, rustc = staged_compiler_inputs(link, BRIDGE, Path(tmp))
        receipt = link["linked_foreign_declaration_proofs"][key]
        apply_receipt(crate, read_proof(link, BRIDGE, receipt)["declarations"], inputs)
        parent = compile_staged(crate, inputs, rustc, archive)
        if parent != link["source_library_sha256"][key]:
            raise ValueError("bridge control failed to reproduce the actual linked archive")
        module = crate / MODULE
        transform = replace_table
        if route_names or netlink_protocols:
            from iproute2_route_names import replace_route_names
            baseline, _ = replace_table(module.read_bytes())
            module.write_bytes(baseline)
            parent = compile_staged(crate, inputs, rustc, archive)
            if parent != parent_record["candidate_sha256"]:
                raise ValueError("bridge did not reproduce the linked address-protocol archive")
            transform = replace_route_names
        if netlink_protocols:
            from iproute2_route_names import replace_netlink_protocols
            baseline, _ = replace_route_names(module.read_bytes())
            module.write_bytes(baseline)
            parent = compile_staged(crate, inputs, rustc, archive)
            if parent != route_parent["candidate_sha256"]:
                raise ValueError("bridge did not reproduce the linked scope/realm archive")
            transform = replace_netlink_protocols
        sources = {n: digest(crate / n) for n in inputs}
        after, changes = transform(module.read_bytes())
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


def build_bridge_trial(output, link, route_names=False, netlink_protocols=False):
    output = output.resolve()
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        scratch = Path(tmp)
        (scratch / "control.json").write_text(json.dumps(link))
        result = scratch / "result"
        result.mkdir()
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{scratch}:/trial", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", "/work/scripts/build_iproute2_bridge_address_protocols.py",
                        "/trial/control.json", "/trial/result", *(["--route-names"] if route_names else []),
                        *(["--netlink-protocols"] if netlink_protocols else [])], check=True)
        result.rename(output)


if __name__ == "__main__":
    compile_bridge(json.loads(Path(sys.argv[1]).read_bytes()), Path(sys.argv[2]), sys.argv[3:] == ["--route-names"],
                   sys.argv[3:] == ["--netlink-protocols"])
