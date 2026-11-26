// SPDX-License-Identifier: 0BSD
use serde_json::json;
use std::{collections::BTreeMap, error::Error, fs, io, path::PathBuf};
use syn::visit::{self, Visit};
use syn::*;

struct Counts<'a> {
    source: &'a str,
    context: &'static str,
    groups: BTreeMap<&'static str, [usize; 2]>,
    spaced: usize,
}

impl Counts<'_> {
    fn in_context(&mut self, context: &'static str, f: impl FnOnce(&mut Self)) {
        let previous = std::mem::replace(&mut self.context, context);
        f(self);
        self.context = previous;
    }
}

impl<'ast> Visit<'ast> for Counts<'_> {
    fn visit_type_ptr(&mut self, ty: &'ast TypePtr) {
        let spelling = if ty.mutability.is_some() {
            "*mut"
        } else {
            "*const"
        };
        let offset = ty.star_token.span.byte_range().start;
        if !self.source[offset..].starts_with(spelling) {
            self.spaced += 1;
        }
        self.groups.entry(self.context).or_default()[usize::from(ty.mutability.is_some())] += 1;
        visit::visit_type_ptr(self, ty);
    }

    fn visit_foreign_item(&mut self, item: &'ast ForeignItem) {
        self.in_context("foreign_declaration", |v| {
            visit::visit_foreign_item(v, item)
        });
    }

    fn visit_signature(&mut self, sig: &'ast Signature) {
        let group = if self.context == "foreign_declaration" {
            self.context
        } else {
            "defined_signature"
        };
        self.in_context(group, |v| visit::visit_signature(v, sig));
    }

    fn visit_field(&mut self, field: &'ast Field) {
        self.in_context("field", |v| visit::visit_field(v, field));
    }

    fn visit_item_type(&mut self, item: &'ast ItemType) {
        self.in_context("type_alias", |v| visit::visit_item_type(v, item));
    }

    fn visit_item_static(&mut self, item: &'ast ItemStatic) {
        self.in_context("static_or_const_type", |v| v.visit_type(&item.ty));
        self.visit_expr(&item.expr);
    }

    fn visit_item_const(&mut self, item: &'ast ItemConst) {
        self.in_context("static_or_const_type", |v| v.visit_type(&item.ty));
        self.visit_generics(&item.generics);
        self.visit_expr(&item.expr);
    }

    fn visit_pat_type(&mut self, node: &'ast PatType) {
        self.visit_pat(&node.pat);
        let context = if self.context == "other" {
            "pattern_annotation"
        } else {
            self.context
        };
        self.in_context(context, |v| v.visit_type(&node.ty));
    }

    fn visit_expr_cast(&mut self, cast: &'ast ExprCast) {
        self.visit_expr(&cast.expr);
        self.in_context("cast_destination", |v| v.visit_type(&cast.ty));
    }

    fn visit_angle_bracketed_generic_arguments(
        &mut self,
        args: &'ast AngleBracketedGenericArguments,
    ) {
        let context = if self.context == "other" {
            "generic_argument"
        } else {
            self.context
        };
        self.in_context(context, |v| {
            visit::visit_angle_bracketed_generic_arguments(v, args)
        });
    }
}

fn scan(source: &str) -> std::result::Result<serde_json::Value, syn::Error> {
    let file = syn::parse_file(source)?;
    let mut counts = Counts {
        source,
        context: "other",
        groups: BTreeMap::new(),
        spaced: 0,
    };
    counts.visit_file(&file);
    Ok(json!({"groups": counts.groups, "spaced": counts.spaced}))
}

fn main() -> std::result::Result<(), Box<dyn Error>> {
    let root = PathBuf::from(
        std::env::args_os()
            .nth(1)
            .ok_or("expected source directory")?,
    );
    let ids: Vec<String> = serde_json::from_reader(io::stdin().lock())?;
    let mut results = BTreeMap::new();
    for id in ids {
        if id.len() != 64 || !id.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("expected SHA-256 source keys".into());
        }
        let source = fs::read_to_string(root.join(&id))?;
        results.insert(id.clone(), scan(&source).map_err(|e| format!("{id}: {e}"))?);
    }
    serde_json::to_writer(io::stdout().lock(), &results)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn separates_types_from_macro_payloads_comments_and_literals() {
        let source = r#"
            // *const in a comment
            type Alias = *const *mut u8;
            struct S { field: * const u8 }
            extern "C" { fn f(p: *mut u8) -> *const u8; }
            static P: Option<*const u8> = None;
            fn g(p: *mut u8) {
                let q: *const u8 = p as *const u8;
                other::<*mut u8>(q);
                unknown!(*mut u8);
                let _ = "*const in a string";
            }
        "#;
        assert_eq!(
            scan(source).unwrap(),
            json!({"spaced":1, "groups":{
                "type_alias":[1,1], "field":[1,0], "foreign_declaration":[1,1], "static_or_const_type":[1,0],
                "defined_signature":[0,1], "pattern_annotation":[1,0], "cast_destination":[1,0], "generic_argument":[0,1]
            }})
        );
    }
}
