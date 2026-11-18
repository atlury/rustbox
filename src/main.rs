// SPDX-License-Identifier: GPL-3.0-or-later

use std::ffi::{OsStr, OsString};
use std::process::ExitCode;

#[cfg(unix)]
use std::os::unix::ffi::OsStrExt;

fn print_usage() {
    eprintln!("usage: rustbox APPLET [ARGUMENT]...");
    eprintln!("       APPLET [ARGUMENT]...  (through a rustbox symlink)");
}

fn status(code: i32) -> ExitCode {
    ExitCode::from(u8::try_from(code).unwrap_or(255))
}

fn main() -> ExitCode {
    let mut arguments = std::env::args_os();
    let invoked = arguments
        .next()
        .unwrap_or_else(|| OsString::from("rustbox"));
    let invoked_name = rustbox::invocation_name(&invoked);
    let mut remaining: Vec<OsString> = arguments.collect();

    if invoked_name == b"rustbox" {
        if remaining
            .first()
            .is_some_and(|argument| argument == OsStr::new("--list"))
        {
            for applet in rustbox::APPLETS {
                println!("{}", applet.name);
            }
            return ExitCode::SUCCESS;
        }
        if remaining.is_empty() {
            print_usage();
            return status(125);
        }
        let selected = remaining.remove(0);
        return dispatch(selected.as_os_str().as_bytes(), &remaining);
    }

    dispatch(invoked_name, &remaining)
}

fn dispatch(name: &[u8], arguments: &[OsString]) -> ExitCode {
    let Some(applet) = rustbox::find_applet(name) else {
        eprintln!(
            "rustbox: unknown applet '{}'",
            String::from_utf8_lossy(name)
        );
        return status(127);
    };
    status((applet.main)(arguments))
}
