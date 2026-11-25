#!/usr/bin/env python3
"""Reconstruct the ip archive's compiler input and stage an address-protocol pilot."""
# SPDX-License-Identifier: GPL-2.0-or-later
from hashlib import sha256
import json
from pathlib import Path
import sys

from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER

MODULE = Path("src/lib/rt_names.rs")
MODULE_SHA256 = "33bbef39e15386546d9f98bc07ecd371b3ba7e1c455ab1f1d347273ecd85d271"

BRIDGE_MODULE_SHA256 = "490e1818f493ff12382f74052804fbd44715ed91f3fa444996c524cb3268f7bf"
TABLE_SHA256 = "b8fe9bf3139128f9c1d86959ab53b33d2bf599b00ef8124bef95bee9841335b5"


def compiler_inputs(link, archive, destination=None):
    from audit_linked_pointers import measure

    inputs = {"binary": link["binary"]}
    for key in ("source_library_sha256", "linked_private_inline_proofs", "linked_second_inline_proofs",
                "linked_foreign_declaration_proofs"):
        if archive in link.get(key, {}):
            inputs[key] = {archive: link[key][archive]}
    matches = []
    files = {}

    def capture(selected, module, digest, data):
        if str(selected) != archive or module in files:
            raise ValueError("unexpected archive or repeated compiler input")
        files[module] = digest.hex()
        if destination is not None:
            target = destination / module
            if target.read_bytes() != data:
                target.write_bytes(data)
        if module == MODULE:
            if digest.hex() != (BRIDGE_MODULE_SHA256 if Path(archive).name == "libbridge_audit.a" else MODULE_SHA256):
                raise ValueError("unexpected compiler-selected rt_names.rs")
            matches.append(data)

    measure(inputs, inspect_module=capture)
    control, = matches
    return control, files


def replace_table(control):
    parent = sha256(control).hexdigest()
    if parent not in (MODULE_SHA256, BRIDGE_MODULE_SHA256):
        raise ValueError("the address-protocol conversion requires the measured rt_names.rs")
    start = control.index(b"static mut rtnl_addrprot_tab:")
    end = control.index(b"static mut rtnl_rtscope_tab:", start)
    if sha256(control[start:end]).hexdigest() != TABLE_SHA256:
        raise ValueError("address-protocol table and functions differ from the qualified transformation")
    replacement = (ROOT / "compat/iproute2/address_protocols.rs").read_bytes()
    candidate = control[:start] + replacement + b"\n" + control[end:]
    if any(name in candidate for name in (b"rtnl_addrprot_tab", b"rtnl_addrprot_initialize")):
        raise ValueError("the legacy address-protocol table is still referenced")
    return candidate, {"control_module_sha256": parent, "candidate_module_sha256": sha256(candidate).hexdigest(),
                       "raw_pointer_types_removed_in_pilot_module": len(POINTER.findall(control)) - len(POINTER.findall(candidate))}


def stage(link_path, output):
    from iproute2_address_protocol_archive import control_view
    link = control_view(json.loads(link_path.read_bytes()))
    archive, = (key for key in link["source_library_sha256"] if key.endswith("/libip_audit.a"))
    control, _ = compiler_inputs(link, archive)
    candidate, report = replace_table(control)
    (output / "control.rs").write_bytes(control)
    (output / "candidate.rs").write_bytes(candidate)
    print(json.dumps(dict(report, archive_sha256=link["source_library_sha256"][archive])))


if __name__ == "__main__":
    stage(Path(sys.argv[1]), Path(sys.argv[2]))
