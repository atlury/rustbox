// SPDX-License-Identifier: GPL-2.0-or-later
// Shared implementation of the rt_scopes and rt_realms flat name tables.
use core::ffi::{c_char, c_ulong, CStr};
use std::sync::{Mutex, OnceLock};

struct RouteNames {
    defaults: &'static [(u8, &'static CStr)],
    local: &'static CStr,
    vendor: &'static CStr,
    loaded: OnceLock<[Option<&'static CStr>; 256]>,
    cache: Mutex<(Option<&'static CStr>, c_ulong)>,
}

impl RouteNames {
    const fn new(
        defaults: &'static [(u8, &'static CStr)],
        local: &'static CStr,
        vendor: &'static CStr,
    ) -> Self {
        Self {
            defaults,
            local,
            vendor,
            loaded: OnceLock::new(),
            cache: Mutex::new((None, 0)),
        }
    }

    fn names(&self) -> &[Option<&'static CStr>; 256] {
        self.loaded.get_or_init(|| {
            let mut slots = [core::ptr::null_mut(); 256];
            for &(id, name) in self.defaults {
                slots[usize::from(id)] = name.as_ptr().cast_mut();
            }
            // The reader takes an inclusive upper ID. It stores process-lifetime
            // strdup results and never mutates the strings.
            unsafe {
                let last = i32::from(u8::MAX);
                if rtnl_tab_initialize(self.local.as_ptr(), slots.as_mut_ptr(), last) == -ENOENT {
                    rtnl_tab_initialize(self.vendor.as_ptr(), slots.as_mut_ptr(), last);
                }
            }
            slots.map(|slot| {
                if slot.is_null() {
                    None
                } else {
                    Some(unsafe { CStr::from_ptr(slot) })
                }
            })
        })
    }

    unsafe fn forward(&self, id: i32, buf: *mut c_char, len: i32) -> *const c_char {
        if numeric == 0 {
            if let Ok(index) = u8::try_from(id) {
                if self.loaded.get().is_none() {
                    if let Some(&(_, name)) = self.defaults.iter().find(|&&(key, _)| key == index) {
                        return name.as_ptr();
                    }
                }
                if let Some(name) = self.names()[usize::from(index)] {
                    return name.as_ptr();
                }
            }
        }
        snprintf(buf, len as size_t, c"%d".as_ptr(), id);
        buf
    }

    fn reverse(&self, query: &CStr) -> Option<u32> {
        let entries = self.names();
        let mut cache = self.cache.lock().unwrap_or_else(|error| error.into_inner());
        // Upstream retains the last matching name across numeric conversions,
        // including failed conversions, and replaces its cached numeric result.
        if cache.0 == Some(query) {
            return Some(cache.1 as u32);
        }
        if let Some(index) = entries.iter().position(|name| *name == Some(query)) {
            *cache = (entries[index], index as c_ulong);
            return Some(index as u32);
        }
        let mut end = core::ptr::null_mut();
        let value = unsafe { strtoul(query.as_ptr(), &mut end, 0) };
        cache.1 = value;
        if end.is_null()
            || end.cast_const() == query.as_ptr()
            || unsafe { *end } != 0
            || value > 255
        {
            return None;
        }
        Some(value as u32)
    }

    unsafe fn write_id(&self, id: *mut u32, arg: *const c_char) -> i32 {
        if let Some(value) = self.reverse(CStr::from_ptr(arg)) {
            *id = value;
            0
        } else {
            -1
        }
    }
}

static ROUTE_SCOPES: RouteNames = RouteNames::new(
    &[
        (0, c"global"),
        (200, c"site"),
        (253, c"link"),
        (254, c"host"),
        (255, c"nowhere"),
    ],
    c"/etc/iproute2/rt_scopes",
    c"/usr/share/iproute2/rt_scopes",
);
static ROUTE_REALMS: RouteNames = RouteNames::new(
    &[(0, c"unknown")],
    c"/etc/iproute2/rt_realms",
    c"/usr/share/iproute2/rt_realms",
);

#[no_mangle]
pub unsafe extern "C" fn rtnl_rtscope_n2a(id: i32, buf: *mut c_char, len: i32) -> *const c_char {
    ROUTE_SCOPES.forward(id, buf, len)
}
#[no_mangle]
pub unsafe extern "C" fn rtnl_rtscope_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    ROUTE_SCOPES.write_id(id, arg)
}
#[no_mangle]
pub unsafe extern "C" fn rtnl_rtrealm_n2a(id: i32, buf: *mut c_char, len: i32) -> *const c_char {
    ROUTE_REALMS.forward(id, buf, len)
}
#[no_mangle]
pub unsafe extern "C" fn rtnl_rtrealm_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    ROUTE_REALMS.write_id(id, arg)
}
