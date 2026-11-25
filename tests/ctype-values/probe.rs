// SPDX-License-Identifier: 0BSD
#[path = "../../compat/linux/ctype.rs"]
mod linux;
use linux::rustbox_ctype as c;

#[unsafe(no_mangle)]
pub extern "C" fn rust_classify(class: usize, byte: u8) -> i32 {
    let classes = [c::upper, c::lower, c::alpha, c::digit, c::xdigit, c::space,
                   c::print, c::graph, c::blank, c::cntrl, c::punct, c::alnum];
    classes[class](byte)
}
