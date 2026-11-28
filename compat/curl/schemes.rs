// SPDX-License-Identifier: curl
#[no_mangle]
pub unsafe extern "C" fn Curl_getn_scheme(
    scheme: *const ::core::ffi::c_char,
    len: size_t,
) -> *const Curl_scheme {
    if !(2..=7).contains(&len) {
        return core::ptr::null();
    }
    // urlapi and setopt pass measured token lengths. Curl_get_scheme uses strlen.
    let bytes = unsafe { core::slice::from_raw_parts(scheme.cast::<u8>(), len as usize) };
    let mut buffer = [0u8; 7];
    let name = &mut buffer[..bytes.len()];
    name.copy_from_slice(bytes);
    name.make_ascii_lowercase();
    match &*name {
        b"dict" => &raw const Curl_scheme_dict,
        b"file" => &raw const Curl_scheme_file,
        b"ftp" => &raw const Curl_scheme_ftp,
        b"ftps" => &raw const Curl_scheme_ftps,
        b"gopher" => &raw const Curl_scheme_gopher,
        b"gophers" => &raw const Curl_scheme_gophers,
        b"http" => &raw const Curl_scheme_http,
        b"https" => &raw const Curl_scheme_https,
        b"imap" => &raw const Curl_scheme_imap,
        b"imaps" => &raw const Curl_scheme_imaps,
        b"ldap" => &raw const Curl_scheme_ldap,
        b"ldaps" => &raw const Curl_scheme_ldaps,
        b"mqtt" => &raw const Curl_scheme_mqtt,
        b"mqtts" => &raw const Curl_scheme_mqtts,
        b"pop3" => &raw const Curl_scheme_pop3,
        b"pop3s" => &raw const Curl_scheme_pop3s,
        b"rtsp" => &raw const Curl_scheme_rtsp,
        b"scp" => &raw const Curl_scheme_scp,
        b"sftp" => &raw const Curl_scheme_sftp,
        b"smtp" => &raw const Curl_scheme_smtp,
        b"smtps" => &raw const Curl_scheme_smtps,
        b"socks" => &raw const Curl_scheme_socks,
        b"socks4" => &raw const Curl_scheme_socks4,
        b"socks4a" => &raw const Curl_scheme_socks4a,
        b"socks5" => &raw const Curl_scheme_socks5,
        b"socks5h" => &raw const Curl_scheme_socks5h,
        b"telnet" => &raw const Curl_scheme_telnet,
        b"tftp" => &raw const Curl_scheme_tftp,
        b"ws" => &raw const Curl_scheme_ws,
        b"wss" => &raw const Curl_scheme_wss,
        _ => core::ptr::null(),
    }
}
