// SPDX-License-Identifier: GPL-2.0-or-later
const DSFIELD_ZERO: &CStr = c"0";
static DSFIELD_NAMES: RouteNames = RouteNames::new(
    &[(0, DSFIELD_ZERO)],
    c"/etc/iproute2/rt_dsfield",
    c"/usr/share/iproute2/rt_dsfield",
);

#[forbid(unsafe_code)]
fn dsfield_name(id: i32) -> Option<&'static CStr> {
    let index = u8::try_from(id).ok()?;
    if index == 0 && DSFIELD_NAMES.loaded.get().is_none() {
        return Some(DSFIELD_ZERO);
    }
    DSFIELD_NAMES.names()[usize::from(index)]
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_dsfield_get_name(id: i32) -> *const c_char {
    dsfield_name(id).map_or(core::ptr::null(), CStr::as_ptr)
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_dsfield_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    if let Some(value) = DSFIELD_NAMES.reverse(CStr::from_ptr(arg), 16) {
        *id = value;
        0
    } else {
        -1
    }
}
