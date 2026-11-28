// SPDX-License-Identifier: GPL-2.0-or-later
struct RouteTableNames {
    buckets: [Vec<(u32, std::ffi::CString)>; 256],
}

#[forbid(unsafe_code)]
impl RouteTableNames {
    fn builtin(id: u32) -> Option<&'static CStr> {
        match id {
            253 => Some(c"default"),
            254 => Some(c"main"),
            255 => Some(c"local"),
            _ => None,
        }
    }

    fn insert(&mut self, id: u32, name: &CStr) -> Result<(), std::collections::TryReserveError> {
        let bucket = &mut self.buckets[(id & 255) as usize];
        let mut bytes = Vec::new();
        bucket.try_reserve(1)?;
        bytes.try_reserve_exact(name.to_bytes_with_nul().len())?;
        bytes.extend_from_slice(name.to_bytes_with_nul());
        let owned = std::ffi::CString::from_vec_with_nul(bytes).expect("copied a complete name");
        bucket.push((id, owned));
        Ok(())
    }

    fn name(&self, id: u32) -> Option<&CStr> {
        self.buckets[(id & 255) as usize].iter().rev()
            .find(|(key, _)| *key == id)
            .map(|(_, name)| name.as_c_str())
            .or_else(|| Self::builtin(id))
    }

    fn id(&self, query: &CStr) -> Option<u32> {
        for (index, bucket) in self.buckets.iter().enumerate() {
            if let Some((id, _)) = bucket.iter().rev().find(|(_, name)| name.as_c_str() == query) {
                return Some(*id);
            }
            if Self::builtin(index as u32) == Some(query) {
                return Some(index as u32);
            }
        }
        None
    }
}

impl RouteTableNames {
    // Return true only when the canonical loader would try the vendor file.
    fn read_file(&mut self, path: &CStr) -> bool {
        unsafe {
            let file = fopen(path.as_ptr(), c"r".as_ptr());
            if file.is_null() {
                return *__errno_location() == ENOENT;
            }
            let mut bytes = [0u8; 512];
            let mut id = 0;
            loop {
                let status = fread_id_name(file, &mut id, bytes.as_mut_ptr().cast());
                if status == 0 { break; }
                let name = CStr::from_bytes_until_nul(&bytes).expect("terminated IPRoute2 name");
                if status < 0 {
                    fprintf(stderr, c"Database %s is corrupted at %s\n".as_ptr(), path.as_ptr(), name.as_ptr());
                    break;
                }
                if id >= 0 && self.insert(id as u32, name).is_err() {
                    fprintf(stderr, c"malloc error: for entry\n".as_ptr());
                    break;
                }
            }
            fclose(file);
        }
        false
    }

    fn read_directory(&mut self, base: &CStr, overlay: Option<&CStr>) {
        // Retain libc directory order, lstat shadowing (including dangling
        // symlinks) and the errno visible after the original enumeration.
        unsafe {
            let dir = opendir(base.as_ptr());
            if dir.is_null() { return; }
            loop {
                let entry = readdir(dir);
                if entry.is_null() { break; }
                let name = CStr::from_ptr((*entry).d_name.as_ptr());
                let bytes = name.to_bytes();
                if bytes.starts_with(b".") || bytes.len() <= 5 || !bytes.ends_with(b".conf") {
                    continue;
                }
                let mut path = [0i8; 4096];
                if let Some(local) = overlay {
                    snprintf(path.as_mut_ptr(), path.len() as size_t, c"%s/%s".as_ptr(), local.as_ptr(), name.as_ptr());
                    let mut info = std::mem::MaybeUninit::uninit();
                    if lstat(path.as_ptr(), info.as_mut_ptr()) == 0 { continue; }
                }
                snprintf(path.as_mut_ptr(), path.len() as size_t, c"%s/%s".as_ptr(), base.as_ptr(), name.as_ptr());
                self.read_file(CStr::from_ptr(path.as_ptr()));
            }
            closedir(dir);
        }
    }
}

fn route_table_names() -> &'static RouteTableNames {
    static TABLE: OnceLock<RouteTableNames> = OnceLock::new();
    TABLE.get_or_init(|| {
        let mut table = RouteTableNames { buckets: std::array::from_fn(|_| Vec::new()) };
        if table.read_file(c"/etc/iproute2/rt_tables") {
            table.read_file(c"/usr/share/iproute2/rt_tables");
        }
        let local = c"/etc/iproute2/rt_tables.d";
        table.read_directory(c"/usr/share/iproute2/rt_tables.d", Some(local));
        table.read_directory(local, None);
        table
    })
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_rttable_n2a(id: u32, buf: *mut c_char, len: i32) -> *const c_char {
    let names = route_table_names();
    if numeric == 0 {
        if let Some(name) = names.name(id) { return name.as_ptr(); }
    }
    snprintf(buf, len as size_t, c"%u".as_ptr(), id);
    buf
}

#[no_mangle]
pub unsafe extern "C" fn rtnl_rttable_a2n(id: *mut u32, arg: *const c_char) -> i32 {
    if let Some(value) = route_table_names().id(CStr::from_ptr(arg)) {
        *id = value;
        return 0;
    }
    let mut end = core::ptr::null_mut();
    let value = strtoul(arg, &mut end, 0);
    if end.is_null() || end.cast_const() == arg || *end != 0 || value > u32::MAX.into() {
        return -1;
    }
    *id = value as u32;
    0
}
