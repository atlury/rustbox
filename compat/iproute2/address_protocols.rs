// SPDX-License-Identifier: GPL-2.0-or-later
// Included in the IPRoute2 rt_names translation in place of its address-protocol table.
fn address_protocol_names() -> &'static [Option<&'static core::ffi::CStr>; 256] {
    use core::ffi::CStr;
    use std::sync::OnceLock;

    static NAMES: OnceLock<[Option<&'static CStr>; 256]> = OnceLock::new();
    NAMES.get_or_init(|| {
        let mut slots = [core::ptr::null_mut(); 256];
        for (slot, name) in
            slots
                .iter_mut()
                .zip([c"unspec", c"kernel_lo", c"kernel_ra", c"kernel_ll"])
        {
            *slot = name.as_ptr().cast_mut();
        }
        // The canonical flat-table reader takes an inclusive upper ID. It
        // replaces entries with strdup results and never writes into a name.
        let last = i32::from(u8::MAX);
        unsafe {
            let local = rtnl_tab_initialize(
                c"/etc/iproute2/rt_addrprotos".as_ptr(),
                slots.as_mut_ptr(),
                last,
            );
            if local == -ENOENT {
                rtnl_tab_initialize(
                    c"/usr/share/iproute2/rt_addrprotos".as_ptr(),
                    slots.as_mut_ptr(),
                    last,
                );
            }
            rtnl_tab_initialize_dir(c"rt_addrprotos.d".as_ptr(), slots.as_mut_ptr(), last);
        }
        // Both the literals and the final strdup allocations live for the process
        // lifetime. Only immutable names escape, after the last loader has returned.
        slots.map(|name| {
            if name.is_null() {
                None
            } else {
                Some(unsafe { CStr::from_ptr(name) })
            }
        })
    })
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_addrprot_n2a(
    id: u8,
    buf: *mut core::ffi::c_char,
    len: i32,
) -> *const core::ffi::c_char {
    if numeric == 0 {
        if let Some(name) = address_protocol_names()[usize::from(id)] {
            return name.as_ptr();
        }
    }
    snprintf(buf, len as size_t, c"%#x".as_ptr(), u32::from(id));
    buf
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_addrprot_a2n(id: *mut u8, arg: *const core::ffi::c_char) -> i32 {
    let names = address_protocol_names();
    let query = core::ffi::CStr::from_ptr(arg);
    if let Some(index) = names.iter().position(|entry| *entry == Some(query)) {
        *id = index as u8;
        return 0;
    }
    let mut end = core::ptr::null_mut();
    let value = strtoul(arg, &mut end, 0);
    if end.is_null() || end.cast_const() == arg || *end != 0 || value > u8::MAX.into() {
        return -1;
    }
    *id = value as u8;
    0
}
