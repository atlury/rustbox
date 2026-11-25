// SPDX-License-Identifier: GPL-2.0-or-later
static NETLINK_PROTOCOLS: RouteNames = RouteNames::new(
    &[
        (0, c"rtnl"), (1, c"unused"), (2, c"usersock"), (3, c"fw"),
        (4, c"tcpdiag"), (5, c"nflog"), (6, c"xfrm"), (7, c"selinux"),
        (8, c"iscsi"), (9, c"audit"), (10, c"fiblookup"), (11, c"connector"),
        (12, c"nft"), (13, c"ip6fw"), (14, c"dec-rt"), (15, c"uevent"),
        (16, c"genl"), (18, c"scsi-trans"), (19, c"ecryptfs"), (20, c"rdma"),
        (21, c"crypto"),
    ],
    c"/etc/iproute2/nl_protos",
    c"/usr/share/iproute2/nl_protos",
);

#[no_mangle]
pub unsafe extern "C" fn nl_proto_n2a(id: i32, buf: *mut c_char, len: i32) -> *const c_char {
    if numeric == 0 {
        if let Ok(index) = u8::try_from(id) {
            // Even built-in netlink protocol names can be overridden on the first call.
            if let Some(name) = NETLINK_PROTOCOLS.names()[usize::from(index)] {
                return name.as_ptr();
            }
        }
    }
    snprintf(buf, len as size_t, c"%d".as_ptr(), id);
    buf
}

#[no_mangle]
pub unsafe extern "C" fn nl_proto_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    NETLINK_PROTOCOLS.write_id(id, arg)
}
