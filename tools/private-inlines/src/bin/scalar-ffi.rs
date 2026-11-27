// SPDX-License-Identifier: 0BSD
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io;
use std::path::{Component, Path};
use syn::{FnArg, ForeignItem, Item, PathArguments, ReturnType, Type, Visibility};

// Only direct primitive types and file-local aliases to those primitives qualify.
// Keep platform C typedefs spelled with their original absolute core path.
fn scalar(ty: &Type, aliases: &BTreeMap<String, String>) -> Option<String> {
    let Type::Path(p) = ty else { return None };
    if p.qself.is_some()
        || p.path
            .segments
            .iter()
            .any(|s| !matches!(s.arguments, PathArguments::None))
    {
        return None;
    }
    if let Some(id) = p.path.get_ident() {
        let name = id.to_string();
        return match name.as_str() {
            "u8" | "u16" | "u32" | "u64" | "usize" | "i8" | "i16" | "i32" | "i64" | "isize"
            | "f32" | "f64" => Some(name),
            _ => aliases.get(&name).cloned(),
        };
    }
    let parts: Vec<_> = p
        .path
        .segments
        .iter()
        .map(|x| x.ident.to_string())
        .collect();
    if p.path.leading_colon.is_none() || parts.len() != 3 || parts[..2] != ["core", "ffi"] {
        return None;
    }
    match parts[2].as_str() {
        "c_char" | "c_schar" | "c_uchar" | "c_short" | "c_ushort" | "c_int" | "c_uint"
        | "c_long" | "c_ulong" | "c_longlong" | "c_ulonglong" | "c_float" | "c_double"
        | "c_void" => Some(format!("::core::ffi::{}", parts[2])),
        _ => None,
    }
}

fn ffi_type(ty: &Type, aliases: &BTreeMap<String, String>) -> Option<String> {
    if let Type::Ptr(ptr) = ty {
        let inner = ffi_type(&ptr.elem, aliases)?;
        let kind = if ptr.mutability.is_some() {
            "mut"
        } else {
            "const"
        };
        return Some(format!("*{kind} {inner}"));
    }
    scalar(ty, aliases)
}

type Entry = (String, usize, usize, usize);

fn scan(source: &str) -> Result<Vec<Entry>, syn::Error> {
    let file = syn::parse_file(source)?;
    if file.items.iter().any(|i| matches!(i, Item::Mod(_))) {
        return Ok(Vec::new());
    }
    let mut aliases = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for item in &file.items {
        if let Item::Type(alias) = item {
            let name = alias.ident.to_string();
            if !seen.insert(name.clone()) {
                aliases.remove(&name);
            } else if alias.attrs.is_empty() && alias.generics.params.is_empty() {
                if let Some(resolved) = scalar(&alias.ty, &BTreeMap::new()) {
                    aliases.insert(name, resolved);
                }
            }
        }
    }
    let mut out = Vec::new();
    for item in file.items {
        let Item::ForeignMod(block) = item else {
            continue;
        };
        if !block.attrs.is_empty()
            || block.abi.name.as_ref().map(|x| x.value()).as_deref() != Some("C")
        {
            continue;
        }
        let after_block = block.brace_token.span.close().byte_range().end;
        for decl in block.items {
            let ForeignItem::Fn(f) = decl else { continue };
            let s = f.sig;
            if !f.attrs.is_empty()
                || !matches!(f.vis, Visibility::Inherited)
                || s.variadic.is_some()
                || s.unsafety.is_some()
                || s.abi.is_some()
                || !s.generics.params.is_empty()
            {
                continue;
            }
            let params: Option<Vec<_>> = s
                .inputs
                .iter()
                .enumerate()
                .map(|(i, arg)| {
                    let FnArg::Typed(param) = arg else {
                        return None;
                    };
                    if !param.attrs.is_empty() {
                        return None;
                    }
                    Some(format!("a{i}: {}", ffi_type(&param.ty, &aliases)?))
                })
                .collect();
            let Some(params) = params else { continue };
            let result = match s.output {
                ReturnType::Default => String::new(),
                ReturnType::Type(_, ty) => {
                    let Some(ret) = ffi_type(&ty, &aliases) else {
                        continue;
                    };
                    format!(" -> {ret}")
                }
            };
            let signature = format!("fn {}({}){result};", s.ident, params.join(", "));
            if signature.contains('*') {
                out.push((
                    signature,
                    s.fn_token.span.byte_range().start,
                    f.semi_token.span.byte_range().end,
                    after_block,
                ));
            }
        }
    }
    Ok(out)
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args_os()
        .nth(1)
        .ok_or("expected compiler source directory")?;
    let inputs: BTreeSet<String> = serde_json::from_reader(io::stdin().lock())?;
    let mut result = BTreeMap::new();
    for module in inputs {
        let path = Path::new(&module);
        if path.extension().is_none_or(|s| s != "rs")
            || !path.components().all(|c| matches!(c, Component::Normal(_)))
        {
            return Err("unexpected module path".into());
        }
        let items = scan(&fs::read_to_string(Path::new(&root).join(path))?)?;
        if !items.is_empty() {
            result.insert(module, items);
        }
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn resolves_scalar_aliases_and_excludes_local_layouts_and_symbol_overrides() {
        let src = r#"pub type size_t = usize;
extern "C" {
 fn foo(p: *const u8, n: size_t) -> *mut ::core::ffi::c_void;
 #[link_name = "other"] fn different(p: *mut u8);
 fn local(p: *mut Local);
 fn var(p: *const u8, ...);
}
#[link(name="other")] extern "C" { fn linked(p: *mut u8); }
"#;
        let rows = scan(src).unwrap();
        assert_eq!(rows.len(), 1);
        let (signature, lo, hi, end) = &rows[0];
        assert_eq!(
            signature,
            "fn foo(a0: *const u8, a1: usize) -> *mut ::core::ffi::c_void;"
        );
        assert!(src[*lo..*hi].starts_with("fn foo("));
        assert_eq!(&src[*end - 1..*end], "}");
    }
}
