// SPDX-License-Identifier: GPL-3.0-or-later

use std::ffi::{OsStr, OsString};

#[cfg(unix)]
use std::os::unix::ffi::OsStrExt;

pub type AppletMain = fn(&[OsString]) -> i32;

pub struct Applet {
    pub name: &'static str,
    pub main: AppletMain,
}

// Applets enter this sorted table only after their public differential gate
// passes. Shared code remains in this one crate and one final executable.
pub static APPLETS: &[Applet] = &[];

#[cfg(unix)]
pub fn invocation_name(path: &OsStr) -> &[u8] {
    path.as_bytes()
        .rsplit(|byte| *byte == b'/')
        .next()
        .unwrap_or_default()
}

pub fn find_applet(name: &[u8]) -> Option<&'static Applet> {
    APPLETS
        .binary_search_by(|applet| applet.name.as_bytes().cmp(name))
        .ok()
        .map(|index| &APPLETS[index])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invocation_uses_final_raw_path_component() {
        assert_eq!(invocation_name(OsStr::new("/usr/bin/rustbox")), b"rustbox");
        assert_eq!(invocation_name(OsStr::new("true")), b"true");
        assert_eq!(invocation_name(OsStr::new("/")), b"");
    }

    #[test]
    fn initial_registry_is_sorted_and_empty() {
        assert!(APPLETS.is_empty());
        assert!(find_applet(b"true").is_none());
    }
}
