"""Replace the two canonical route-name tables in a verified IPRoute2 compiler input."""
# SPDX-License-Identifier: GPL-2.0-or-later
from hashlib import sha256

from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER


def replace_route_names(control):
    start = control.index(b"static mut rtnl_rtscope_tab:")
    end = control.index(b"static mut dflt_table_entry:", start)
    if sha256(control[start:end]).hexdigest() != "1c051d4056b8899fca341c856bb3a53838208454445af4d59bdc21664d84564b":
        raise ValueError("scope/realm tables differ from the measured canonical translation")
    replacement = (ROOT / "compat/iproute2/route_names.rs").read_bytes()
    candidate = control[:start] + replacement + b"\n" + control[end:]
    return candidate, {"control_module_sha256": sha256(control).hexdigest(),
                       "candidate_module_sha256": sha256(candidate).hexdigest(),
                       "raw_pointer_types_removed_in_pilot_module": len(POINTER.findall(control)) - len(POINTER.findall(candidate))}


def replace_netlink_protocols(control):
    start = control.index(b"static mut nl_proto_tab:")
    end = control.index(b"pub const PROTODOWN_REASON_NUM_BITS:", start)
    if sha256(control[start:end]).hexdigest() != "660193b989214703dd8672ed189b93350a2a0210214cc94ac5faaeefedab203e":
        raise ValueError("netlink protocol table differs from the measured canonical translation")
    replacement = (ROOT / "compat/iproute2/netlink_protocols.rs").read_bytes()
    candidate = control[:start] + replacement + b"\n" + control[end:]
    return candidate, {"control_module_sha256": sha256(control).hexdigest(),
                       "candidate_module_sha256": sha256(candidate).hexdigest(),
                       "raw_pointer_types_removed_in_pilot_module": len(POINTER.findall(control)) - len(POINTER.findall(candidate))}
