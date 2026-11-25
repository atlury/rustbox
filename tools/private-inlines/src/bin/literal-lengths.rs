// SPDX-License-Identifier: 0BSD
use proc_macro2::{TokenStream, TokenTree};
use std::collections::BTreeMap;
use std::error::Error;
use std::fs;
use std::io;
use std::path::{Component, PathBuf};
use syn::visit::{self, Visit};
use syn::{Expr, ExprCall, ExprPath, ForeignItem, Item, Lit};

fn mentions(tokens: TokenStream) -> usize {
    tokens
        .into_iter()
        .map(|token| match token {
            TokenTree::Ident(id) => usize::from(id == "strlen" || id == "r#strlen"),
            TokenTree::Group(group) => mentions(group.stream()),
            _ => 0,
        })
        .sum()
}

fn compact(s: &str) -> String {
    s.split_whitespace().collect()
}

struct Calls<'a> {
    source: &'a str,
    references: usize,
    ambiguous: bool,
    edits: Vec<(usize, usize, String)>,
}

impl Calls<'_> {
    fn length(&self, call: &ExprCall) -> Option<(usize, usize, String)> {
        let Expr::Path(path) = &*call.func else {
            return None;
        };
        if !path.path.is_ident("strlen") || !call.attrs.is_empty() || call.args.len() != 1 {
            return None;
        }
        let Expr::Cast(outer) = call.args.first()? else {
            return None;
        };
        let Expr::Cast(inner) = &*outer.expr else {
            return None;
        };
        let Expr::Lit(expr) = &*inner.expr else {
            return None;
        };
        let Lit::ByteStr(literal) = &expr.lit else {
            return None;
        };
        let bytes = literal.value();
        let (&end_byte, contents) = bytes.split_last()?;
        if end_byte != 0 || contents.contains(&0) {
            return None;
        }
        let start = path.path.get_ident()?.span().byte_range().start;
        let end = call.paren_token.span.close().byte_range().end;
        let span = literal.span().byte_range();
        let spelling = self.source.get(span.clone())?;
        if !spelling.starts_with("b\"")
            || spelling.contains(['\r', '\n'])
            || compact(self.source.get(start..span.start)?) != "strlen("
            || !matches!(
                compact(self.source.get(span.end..end)?).as_str(),
                "as*constu8as*const::core::ffi::c_char,)"
                    | "as*constu8as*const::core::ffi::c_char)"
            )
        {
            return None;
        }
        let original = self.source.get(start..end)?;
        let lines: String = original
            .chars()
            .filter(|c| matches!(c, '\r' | '\n'))
            .collect();
        Some((start, end, format!("({}usize{lines})", contents.len())))
    }
}

impl<'ast> Visit<'ast> for Calls<'_> {
    fn visit_use_glob(&mut self, _: &'ast syn::UseGlob) {
        self.ambiguous = true;
    }
    fn visit_item_macro(&mut self, _: &'ast syn::ItemMacro) {
        self.ambiguous = true;
    }
    fn visit_stmt_macro(&mut self, stmt: &'ast syn::StmtMacro) {
        // A statement macro could introduce a binding with a generated name.
        self.ambiguous = true;
        visit::visit_stmt_macro(self, stmt);
    }
    fn visit_expr_call(&mut self, call: &'ast ExprCall) {
        if let Some(edit) = self.length(call) {
            self.edits.push(edit);
        }
        visit::visit_expr_call(self, call);
    }
    fn visit_expr_path(&mut self, path: &'ast ExprPath) {
        if path.qself.is_none() && path.path.is_ident("strlen") {
            self.references += 1;
        }
        visit::visit_expr_path(self, path);
    }
}

fn scan(source: &str) -> Result<Vec<(usize, usize, String)>, Box<dyn Error>> {
    let syntax = syn::parse_file(source)?;
    let mut declarations = 0;
    let mut size_types = 0;
    for item in &syntax.items {
        match item {
            Item::Mod(_) => return Ok(Vec::new()),
            Item::Type(alias) if alias.ident == "size_t" && alias.attrs.is_empty() => {
                if matches!(alias.ty.as_ref(), syn::Type::Path(p) if p.qself.is_none() && p.path.is_ident("usize"))
                {
                    size_types += 1;
                }
            }
            Item::ForeignMod(block)
                if block.attrs.is_empty()
                    && block
                        .abi
                        .name
                        .as_ref()
                        .is_some_and(|name| name.value() == "C") =>
            {
                for foreign in &block.items {
                    if let ForeignItem::Fn(f) = foreign {
                        if f.sig.ident == "strlen" && f.attrs.is_empty() {
                            let signature = &source[f.sig.fn_token.span.byte_range().start
                                ..f.semi_token.span.byte_range().end];
                            if compact(signature)
                                == "fnstrlen(__s:*const::core::ffi::c_char)->size_t;"
                            {
                                declarations += 1;
                            }
                        }
                    }
                }
            }
            _ => {}
        }
    }
    if declarations != 1 || size_types != 1 {
        return Ok(Vec::new());
    }
    let mut calls = Calls {
        source,
        references: 0,
        ambiguous: false,
        edits: Vec::new(),
    };
    calls.visit_file(&syntax);
    // A local binding, import, macro mention or additional declaration makes
    // name resolution ambiguous. Skip the module in its entirety.
    if calls.ambiguous || mentions(source.parse()?) != 1 + calls.references {
        calls.edits.clear();
    }
    Ok(calls.edits)
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = PathBuf::from(std::env::args_os().nth(1).ok_or("expected source root")?);
    let files: Vec<PathBuf> = serde_json::from_reader(io::stdin().lock())?;
    let mut result = BTreeMap::new();
    for file in files {
        if !file.components().all(|c| matches!(c, Component::Normal(_)))
            || file.extension().and_then(|ext| ext.to_str()) != Some("rs")
        {
            return Err("expected compiler-selected Rust module".into());
        }
        let source = fs::read_to_string(root.join(&file))?;
        if source.contains("fn strlen(") {
            let edits = scan(&source)?;
            if !edits.is_empty() {
                result.insert(file, edits);
            }
        }
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}
