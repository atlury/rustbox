// SPDX-License-Identifier: GPL-2.0-or-later
static ROUTING_PROTOCOLS: RouteNames = RouteNames {
    defaults: &[
        (0, c"unspec"), (1, c"redirect"), (2, c"kernel"), (3, c"boot"),
        (4, c"static"), (8, c"gated"), (9, c"ra"), (10, c"mrt"),
        (11, c"zebra"), (12, c"bird"), (13, c"dnrouted"), (14, c"xorp"),
        (15, c"ntk"), (16, c"dhcp"), (18, c"keepalived"), (42, c"babel"),
        (186, c"bgp"), (187, c"isis"), (188, c"ospf"), (189, c"rip"), (192, c"eigrp"),
    ],
    local: c"/etc/iproute2/rt_protos",
    vendor: c"/usr/share/iproute2/rt_protos",
    directory: Some(c"rt_protos.d"),
    loaded: OnceLock::new(),
    cache: Mutex::new((None, 0)),
};

#[no_mangle]
pub unsafe extern "C" fn rtnl_rtprot_n2a(id: i32, buf: *mut c_char, len: i32) -> *const c_char {
    // Canonical rt_protos renders negative IDs as unsigned decimal.
    if id < 0 {
        snprintf(buf, len as size_t, c"%u".as_ptr(), id as u32);
        return buf;
    }
    ROUTING_PROTOCOLS.forward(id, buf, len)
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_rtprot_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    ROUTING_PROTOCOLS.write_id(id, arg)
}
