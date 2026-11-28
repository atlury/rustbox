// SPDX-License-Identifier: 0BSD
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io;
use std::path::{Component, Path};
use syn::spanned::Spanned;
use syn::{Expr, Item, ItemType, Lit, Type};

fn resolve(
    ty: &Type,
    owner: &str,
    aliases: &BTreeMap<String, Option<&ItemType>>,
    seen: &mut BTreeSet<String>,
) -> Option<String> {
    match ty {
        Type::Ptr(p) => {
            let target = resolve(&p.elem, owner, aliases, seen)?;
            let kind = if p.mutability.is_some() {
                "mut"
            } else {
                "const"
            };
            Some(format!("*{kind} {target}"))
        }
        Type::Array(a) => {
            let Expr::Lit(length) = &a.len else {
                return None;
            };
            let Lit::Int(n) = &length.lit else {
                return None;
            };
            Some(format!(
                "[{};{}]",
                resolve(&a.elem, owner, aliases, seen)?,
                n.base10_digits()
            ))
        }
        Type::Path(p) if p.qself.is_none() => {
            let path = &p.path;
            if let Some(id) = path.get_ident() {
                let id = id.to_string();
                if let Some(alias) = aliases.get(&id) {
                    let alias = (*alias)?;
                    if !seen.insert(id) {
                        return None;
                    }
                    return resolve(&alias.ty, owner, aliases, seen);
                }
                return match id.as_str() {
                    "u8" | "u16" | "u32" | "u64" | "u128" | "usize" | "i8" | "i16" | "i32"
                    | "i64" | "i128" | "isize" | "f32" | "f64" => Some(id),
                    _ if id == owner => Some(format!("self:{owner}")),
                    _ => None,
                };
            }
            let names: Vec<_> = path
                .segments
                .iter()
                .map(|seg| seg.ident.to_string())
                .collect();
            if path.leading_colon.is_none()
                || names.len() != 3
                || names[..2] != ["core", "ffi"]
                || path.segments.iter().any(|seg| !seg.arguments.is_empty())
            {
                return None;
            }
            match names[2].as_str() {
                "c_char" | "c_schar" | "c_uchar" | "c_short" | "c_ushort" | "c_int" | "c_uint"
                | "c_long" | "c_ulong" | "c_longlong" | "c_ulonglong" | "c_float" | "c_double"
                | "c_void" => Some(format!("::core::ffi::{}", names[2])),
                _ => None,
            }
        }
        _ => None,
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let crate_dir = std::env::args_os()
        .nth(1)
        .ok_or("missing crate directory")?;
    let modules: BTreeMap<String, BTreeSet<String>> = serde_json::from_reader(io::stdin().lock())?;
    let mut result = BTreeMap::new();
    for (module, names) in modules {
        let path = Path::new(&module);
        if path.extension().is_none_or(|e| e != "rs")
            || !path.components().all(|c| matches!(c, Component::Normal(_)))
        {
            return Err("unexpected Rust module path".into());
        }
        let source = fs::read_to_string(Path::new(&crate_dir).join(path))?;
        let file = syn::parse_file(&source)?;
        let mut aliases = BTreeMap::new();
        for item in &file.items {
            if let Item::Type(alias) = item {
                let name = alias.ident.to_string();
                let eligible = alias.attrs.is_empty() && alias.generics.params.is_empty();
                if aliases
                    .insert(name.clone(), eligible.then_some(alias))
                    .is_some()
                {
                    aliases.insert(name, None);
                }
            }
        }
        let mut found = BTreeMap::new();
        for item in &file.items {
            let Item::Struct(s) = item else { continue };
            let name = s.ident.to_string();
            if !names.contains(&name) {
                continue;
            }
            if s.attrs.len() != 2
                || !s.generics.params.is_empty()
                || !matches!(s.vis, syn::Visibility::Public(_))
            {
                return Err(format!(
                    "unexpected struct attributes or visibility on {module}::{name}"
                )
                .into());
            }
            let mut fields = Vec::new();
            for field in &s.fields {
                if !field.attrs.is_empty() || !matches!(field.vis, syn::Visibility::Public(_)) {
                    return Err(format!("unexpected field on {module}::{name}").into());
                }
                let ty = resolve(&field.ty, &name, &aliases, &mut BTreeSet::new())
                    .ok_or_else(|| format!("unresolved field type on {module}::{name}"))?;
                fields.push((
                    field
                        .ident
                        .as_ref()
                        .ok_or("expected named field")?
                        .to_string(),
                    ty,
                ));
            }
            let span = s.span().byte_range();
            if found.insert(name, (span.start, span.end, fields)).is_some() {
                return Err("ambiguous top-level struct".into());
            }
        }
        if !names.iter().eq(found.keys()) {
            return Err("a selected top-level struct is missing".into());
        }
        result.insert(module, found);
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}
