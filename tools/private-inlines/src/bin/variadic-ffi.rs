// SPDX-License-Identifier: 0BSD
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::{fs, io};
use std::path::{Component, Path};
use syn::{ForeignItem, Item};

// Existing compiler receipts pin this scanner's exact source. Reuse its type,
// attribute, visibility and ABI checks, and retain its original byte offsets.
#[allow(dead_code)]
mod scalar {
    include!("scalar-ffi.rs");

    pub(super) fn scan_fixed(source: &str) -> Result<Vec<Entry>, syn::Error> {
        scan(source)
    }
}

type Entry = (String, usize, usize, usize);

fn scan(source: &str) -> Result<Vec<Entry>, Box<dyn Error>> {
    if !source.contains("...") {
        return Ok(Vec::new());
    }
    let file = syn::parse_file(source)?;
    let mut masked = source.as_bytes().to_vec();
    let mut starts = BTreeSet::new();
    for item in file.items {
        let Item::ForeignMod(block) = item else { continue };
        for member in block.items {
            let ForeignItem::Fn(f) = member else { continue };
            let Some(var) = &f.sig.variadic else { continue };
            if f.sig.inputs.is_empty() || !var.attrs.is_empty() || var.pat.is_some() || var.comma.is_some() {
                continue;
            }
            let dots = &var.dots.spans;
            let range = dots[0].byte_range().start..dots[2].byte_range().end;
            if masked.get(range.clone()) != Some(b"...") {
                return Err("invalid C variadic token range".into());
            }
            // Blanking just the ellipsis leaves the fixed parameters and their trailing comma.
            masked[range].fill(b' ');
            starts.insert(f.sig.fn_token.span.byte_range().start);
        }
    }
    if starts.is_empty() {
        return Ok(Vec::new());
    }
    let mut result = Vec::new();
    for (mut signature, start, end, after) in scalar::scan_fixed(std::str::from_utf8(&masked)?)? {
        if starts.contains(&start) {
            let close = signature.find(')').ok_or("invalid fixed ABI signature")?;
            signature.insert_str(close, ", ...");
            result.push((signature, start, end, after));
        }
    }
    Ok(result)
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args_os().nth(1).ok_or("expected compiler source directory")?;
    let modules: BTreeSet<String> = serde_json::from_reader(io::stdin().lock())?;
    let mut result = BTreeMap::new();
    for module in modules {
        let path = Path::new(&module);
        if path.extension().is_none_or(|s| s != "rs")
            || !path.components().all(|c| matches!(c, Component::Normal(_))) {
            return Err("unexpected module path".into());
        }
        let rows = scan(&fs::read_to_string(Path::new(&root).join(path))?)?;
        if !rows.is_empty() { result.insert(module, rows); }
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_variadic_abi_and_source_range() {
        let source = r#"type Size = usize;
extern "C" {
 fn print(n: Size, format: *const ::core::ffi::c_char, ...) -> i32;
 fn fixed(format: *const ::core::ffi::c_char);
 fn local(handle: *mut Local, ...);
 #[link_name="other"] fn renamed(format: *const u8, ...);
}
"#;
        let rows = scan(source).unwrap();
        assert_eq!(rows.len(), 1);
        let (signature, start, end, after) = &rows[0];
        assert_eq!(signature, "fn print(a0: usize, a1: *const ::core::ffi::c_char, ...) -> i32;");
        assert_eq!(&source[*start..*end], "fn print(n: Size, format: *const ::core::ffi::c_char, ...) -> i32;");
        assert_eq!(&source[*after-1..*after], "}");
    }

    #[test]
    fn excludes_inapplicable_or_non_c_declarations() {
        let s = r#"extern "system" { fn abi(s: *const u8, ...); }
#[link(name="special")] extern "C" { fn linked(s: *mut u8, ...); }
extern "C" { pub fn visible(s: *mut u8, ...); fn any(...); }
"#;
        assert!(scan(s).unwrap().is_empty());
    }
}
