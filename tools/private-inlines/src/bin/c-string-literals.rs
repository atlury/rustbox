// SPDX-License-Identifier: 0BSD
use std::collections::BTreeMap;
use std::error::Error;
use std::fs;
use std::io;
use std::path::{Component, Path, PathBuf};
use syn::visit::{self, Visit};
use syn::{Expr, ExprCast, Lit, PathArguments, Type};

fn const_pointee<'a>(ty: &'a Type, absolute: bool, names: &[&str]) -> Option<&'a syn::Ident> {
    let Type::Ptr(ptr) = ty else { return None };
    let Type::Path(path) = &*ptr.elem else {
        return None;
    };
    if ptr.mutability.is_some()
        || ptr.const_token.is_none()
        || path.qself.is_some()
        || path.path.leading_colon.is_some() != absolute
        || !path
            .path
            .segments
            .iter()
            .all(|s| matches!(s.arguments, PathArguments::None))
        || !path
            .path
            .segments
            .iter()
            .map(|s| s.ident.to_string())
            .eq(names.iter().copied())
    {
        return None;
    }
    Some(&path.path.segments.last()?.ident)
}

struct Literals<'s> {
    source: &'s str,
    edits: Vec<(usize, usize, String)>,
}

impl Literals<'_> {
    fn replacement(&self, cast: &ExprCast) -> Option<(usize, usize, String)> {
        let last = const_pointee(&cast.ty, true, &["core", "ffi", "c_char"])?;
        let Expr::Cast(inner) = &*cast.expr else {
            return None;
        };
        const_pointee(&inner.ty, false, &["u8"])?;
        let Expr::Lit(expr) = &*inner.expr else {
            return None;
        };
        let Lit::ByteStr(literal) = &expr.lit else {
            return None;
        };
        if !cast.attrs.is_empty() || !inner.attrs.is_empty() || !expr.attrs.is_empty() {
            return None;
        }
        let range = literal.span().byte_range();
        let text = self.source.get(range.clone())?;
        if text.contains(['\n', '\r']) {
            return None;
        }
        let contents = text.strip_prefix("b\"")?.strip_suffix("\\0\"")?;
        let c_literal = format!("c\"{contents}\"");
        // syn decodes both literal forms, including escapes. Reject inner NULs
        // or any spelling that does not reconstruct exactly the same bytes.
        let parsed = syn::parse_str::<syn::LitCStr>(&c_literal).ok()?;
        if parsed.value().as_bytes_with_nul() != literal.value() {
            return None;
        }
        let end = last.span().byte_range().end;
        let casts = self.source.get(range.end..end)?;
        if casts.split_whitespace().collect::<String>() != "as*constu8as*const::core::ffi::c_char" {
            return None;
        }
        let mut replacement = format!(
            "{c_literal}{}.as_ptr()",
            "\n".repeat(casts.matches('\n').count())
        );
        // Keep CRLF line breaks on generated input that uses them.
        if casts.contains("\r\n") {
            if casts.replace("\r\n", "").contains('\n') {
                return None;
            }
            replacement = replacement.replace('\n', "\r\n");
        }
        Some((range.start, end, replacement))
    }
}

impl<'ast> Visit<'ast> for Literals<'_> {
    fn visit_expr_cast(&mut self, cast: &'ast ExprCast) {
        if let Some(edit) = self.replacement(cast) {
            self.edits.push(edit);
        } else {
            visit::visit_expr_cast(self, cast);
        }
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args_os()
        .nth(1)
        .ok_or("expected Cargo source root")?;
    let files: Vec<PathBuf> = serde_json::from_reader(io::stdin().lock())?;
    let mut changes = BTreeMap::new();
    for file in files {
        if !file.components().all(|c| matches!(c, Component::Normal(_)))
            || file.extension().and_then(|s| s.to_str()) != Some("rs")
        {
            return Err("expected crate-relative Rust module".into());
        }
        let source = fs::read_to_string(Path::new(&root).join(&file))?;
        if !source.contains("c_char") || !source.contains("*const u8") {
            continue;
        }
        let syntax = syn::parse_file(&source)?;
        let mut scan = Literals {
            source: &source,
            edits: Vec::new(),
        };
        scan.visit_file(&syntax);
        if !scan.edits.is_empty() {
            if changes.insert(file, scan.edits).is_some() {
                return Err("duplicate compiler input".into());
            }
        }
    }
    serde_json::to_writer(io::stdout().lock(), &changes)?;
    Ok(())
}
