// SPDX-License-Identifier: curl
fn manual_lines() -> impl Iterator<Item = &'static core::ffi::CStr> {
    CURL_MANUAL.split_inclusive(|&byte| byte == 0).map(|line| {
        core::ffi::CStr::from_bytes_with_nul(line).expect("invalid built-in manual record")
    })
}

#[no_mangle]
pub unsafe extern "C" fn hugehelp() {
    for line in manual_lines() {
        puts(line.as_ptr());
    }
}

#[no_mangle]
pub unsafe extern "C" fn showhelp(
    trigger: *const ::core::ffi::c_char,
    arg: *const ::core::ffi::c_char,
    endarg: *const ::core::ffi::c_char,
) {
    let mut ctx = scan_ctx {
        trigger: core::ptr::null(), tlen: 0,
        arg: core::ptr::null(), flen: 0,
        endarg: core::ptr::null(), elen: 0,
        olen: 0, rbuf: [0; 40], obuf: [0; 160], show: 0,
    };
    inithelpscan(&mut ctx, trigger, arg, endarg);
    for line in manual_lines() {
        let bytes = line.to_bytes();
        if !helpscan(bytes.as_ptr(), bytes.len(), &mut ctx)
            || !helpscan(b"\n".as_ptr(), 1, &mut ctx)
        {
            break;
        }
    }
}
