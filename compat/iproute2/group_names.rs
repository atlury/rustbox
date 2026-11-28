// SPDX-License-Identifier: GPL-2.0-or-later
struct GroupNames {
    buckets: [Vec<(i32, std::ffi::CString)>; 256],
}

#[forbid(unsafe_code)]
impl GroupNames {
    fn insert(&mut self, id: i32, name: &CStr) -> Result<(), std::collections::TryReserveError> {
        let bucket = &mut self.buckets[(id & 255) as usize];
        let mut bytes = Vec::new();
        bucket.try_reserve(1)?;
        bytes.try_reserve_exact(name.to_bytes_with_nul().len())?;
        bytes.extend_from_slice(name.to_bytes_with_nul());
        let owned = std::ffi::CString::from_vec_with_nul(bytes).expect("copied a complete C string");
        bucket.push((id, owned));
        Ok(())
    }

    fn name(&self, id: i32) -> Option<&CStr> {
        self.buckets[(id & 255) as usize].iter().rev()
            .find(|(key, _)| *key == id)
            .map(|(_, name)| name.as_c_str())
            .or_else(|| (id == 0).then_some(c"default"))
    }

    fn id(&self, query: &CStr) -> Option<i32> {
        for (index, bucket) in self.buckets.iter().enumerate() {
            if let Some((id, _)) = bucket.iter().rev().find(|(_, name)| name.as_c_str() == query) {
                return Some(*id);
            }
            // The built-in entry was originally the tail of hash bucket zero.
            if index == 0 && query == c"default" {
                return Some(0);
            }
        }
        None
    }
}

fn group_names() -> &'static GroupNames {
    static GROUPS: OnceLock<GroupNames> = OnceLock::new();
    GROUPS.get_or_init(|| {
        let mut names = GroupNames { buckets: std::array::from_fn(|_| Vec::new()) };
        for path in [c"/etc/iproute2/group", c"/usr/share/iproute2/group"] {
            // fread_id_name is the upstream parser. It terminates its 512-byte output.
            let fp = unsafe { fopen(path.as_ptr(), c"r".as_ptr()) };
            if fp.is_null() {
                if unsafe { *__errno_location() } == ENOENT { continue; }
                break;
            }
            let mut bytes = [0u8; 512];
            let mut id = 0;
            loop {
                let status = unsafe { fread_id_name(fp, &mut id, bytes.as_mut_ptr().cast()) };
                if status == 0 { break; }
                let name = CStr::from_bytes_until_nul(&bytes).expect("terminated IPRoute2 group name");
                if status < 0 {
                    unsafe { fprintf(stderr, c"Database %s is corrupted at %s\n".as_ptr(), path.as_ptr(), name.as_ptr()); }
                    break;
                }
                if id >= 0 && names.insert(id, name).is_err() {
                    unsafe { fprintf(stderr, c"malloc error: for entry\n".as_ptr()); }
                    break;
                }
            }
            unsafe { fclose(fp); }
            break;
        }
        names
    })
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_group_a2n(id: *mut i32, arg: *const c_char) -> i32 {
    if let Some(value) = group_names().id(CStr::from_ptr(arg)) {
        *id = value;
        return 0;
    }
    let mut end = core::ptr::null_mut();
    // The canonical interface narrows long to int before checking its sign.
    let value = strtol(arg, &mut end, 0) as i32;
    if end.is_null() || end.cast_const() == arg || *end != 0 || value < 0 { return -1; }
    *id = value;
    0
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_group_n2a(id: i32, buf: *mut c_char, len: i32) -> *const c_char {
    let groups = group_names();
    if numeric == 0 {
        if let Some(name) = groups.name(id) { return name.as_ptr(); }
    }
    snprintf(buf, len as size_t, c"%d".as_ptr(), id);
    buf
}
