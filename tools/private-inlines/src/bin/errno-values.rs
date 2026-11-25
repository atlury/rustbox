// SPDX-License-Identifier: 0BSD
use proc_macro2::{TokenStream, TokenTree};
use std::{
    collections::BTreeMap,
    error::Error,
    fs, io,
    path::{Component, PathBuf},
};
use syn::{
    spanned::Spanned,
    visit::{self, Visit},
    BinOp, Expr, ForeignItem, Item, Pat, UnOp, Visibility,
};

const NAME: &str = "__errno_location";
type Edit = (usize, usize, String);

fn mentions(stream: TokenStream) -> usize {
    stream
        .into_iter()
        .map(|t| match t {
            TokenTree::Ident(i) => usize::from(i == NAME || i == "r#__errno_location"),
            TokenTree::Group(g) => mentions(g.stream()),
            _ => 0,
        })
        .sum()
}

fn cell(expr: &Expr) -> bool {
    let Expr::Unary(u) = expr else { return false };
    let Expr::Call(c) = u.expr.as_ref() else {
        return false;
    };
    matches!(u.op, UnOp::Deref(_))
        && u.attrs.is_empty()
        && c.attrs.is_empty()
        && c.args.is_empty()
        && matches!(&*c.func, Expr::Path(p) if p.attrs.is_empty() && p.qself.is_none() && p.path.is_ident(NAME))
}

#[derive(Default)]
struct Uses {
    edits: Vec<Edit>,
    reads: usize,
    writes: usize,
    ambiguous: bool,
}

impl Uses {
    fn value(&mut self, e: &Expr) {
        if cell(e) {
            let r = e.span().byte_range();
            self.edits
                .push((r.start, r.end, "crate::rustbox_errno::get()".to_owned()));
            self.reads += 1;
        }
    }
}

impl<'a> Visit<'a> for Uses {
    fn visit_local(&mut self, n: &'a syn::Local) {
        // Binding to a plain integer local copies the value. A ref pattern can expose the address.
        let pat = if let Pat::Type(t) = &n.pat {
            &*t.pat
        } else {
            &n.pat
        };
        if matches!(pat, Pat::Ident(i) if i.by_ref.is_none() && i.subpat.is_none()) {
            if let Some(init) = &n.init {
                self.value(&init.expr);
            }
        }
        visit::visit_local(self, n);
    }
    fn visit_expr_binary(&mut self, n: &'a syn::ExprBinary) {
        if matches!(
            n.op,
            BinOp::Eq(_) | BinOp::Ne(_) | BinOp::Lt(_) | BinOp::Le(_) | BinOp::Gt(_) | BinOp::Ge(_)
        ) && matches!(&*n.right, Expr::Lit(_) | Expr::Cast(_))
        {
            self.value(&n.left);
        }
        visit::visit_expr_binary(self, n);
    }
    fn visit_expr_cast(&mut self, n: &'a syn::ExprCast) {
        self.value(&n.expr);
        visit::visit_expr_cast(self, n);
    }
    fn visit_expr_call(&mut self, n: &'a syn::ExprCall) {
        for arg in &n.args {
            self.value(arg);
        }
        visit::visit_expr_call(self, n);
    }
    fn visit_expr_assign(&mut self, n: &'a syn::ExprAssign) {
        if cell(&n.left) {
            let lhs = n.left.span().byte_range();
            let rhs = n.right.span().byte_range();
            self.edits.push((
                lhs.start,
                rhs.start,
                "crate::rustbox_errno::set(".to_owned(),
            ));
            self.edits.push((rhs.end, rhs.end, ")".to_owned()));
            self.writes += 1;
        }
        self.value(&n.right);
        visit::visit_expr_assign(self, n);
    }
    fn visit_use_glob(&mut self, _: &'a syn::UseGlob) {
        self.ambiguous = true;
    }
    fn visit_item_mod(&mut self, _: &'a syn::ItemMod) {
        self.ambiguous = true;
    }
    fn visit_item_macro(&mut self, _: &'a syn::ItemMacro) {
        self.ambiguous = true;
    }
    fn visit_stmt_macro(&mut self, _: &'a syn::StmtMacro) {
        self.ambiguous = true;
    }
}

fn scan(source: &str) -> Result<Option<(usize, usize, Vec<Edit>)>, Box<dyn Error>> {
    let file = syn::parse_file(source)?;
    let mut declarations = vec![];
    for item in &file.items {
        let Item::ForeignMod(block) = item else {
            continue;
        };
        if !block.attrs.is_empty() || !block.abi.name.as_ref().is_some_and(|n| n.value() == "C") {
            continue;
        }
        for item in &block.items {
            let ForeignItem::Fn(f) = item else { continue };
            if f.sig.ident != NAME || !f.attrs.is_empty() || !matches!(f.vis, Visibility::Inherited)
            {
                continue;
            }
            let start = f.sig.fn_token.span.byte_range().start;
            let end = f.semi_token.span.byte_range().end;
            let signature: String = source[start..end].split_whitespace().collect();
            if signature == "fn__errno_location()->*mut::core::ffi::c_int;" {
                declarations.push((start, end));
            }
        }
    }
    let [(start, end)] = declarations.as_slice() else {
        return Ok(None);
    };
    let mut uses = Uses::default();
    uses.visit_file(&file);
    if uses.ambiguous
        || uses.reads + uses.writes == 0
        || mentions(source.parse()?) != 1 + uses.reads + uses.writes
    {
        return Ok(None);
    }
    uses.edits.push((*start, *end, String::new()));
    uses.edits.sort_by_key(|e| (e.0, e.1));
    if uses.edits.windows(2).any(|w| w[0].1 > w[1].0) {
        return Err("overlapping errno edits".into());
    }
    Ok(Some((uses.reads, uses.writes, uses.edits)))
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = PathBuf::from(std::env::args_os().nth(1).ok_or("expected source root")?);
    let names: Vec<PathBuf> = serde_json::from_reader(io::stdin().lock())?;
    let mut result = BTreeMap::new();
    for name in names {
        if !name.components().all(|c| matches!(c, Component::Normal(_)))
            || name.extension().and_then(|s| s.to_str()) != Some("rs")
        {
            return Err("invalid input path".into());
        }
        let source = fs::read_to_string(root.join(&name))?;
        if source.contains("fn __errno_location(") {
            if let Some(found) = scan(&source)? {
                result.insert(name, found);
            }
        }
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::scan;
    const DECL: &str = "extern \"C\" { fn __errno_location() -> *mut ::core::ffi::c_int; }";

    #[test]
    fn copies_and_assignments() {
        let original = format!("{DECL}\nunsafe fn sample() {{ let saved = *__errno_location(); *__errno_location() = f(*__errno_location(), saved); }}");
        let (reads, writes, edits) = scan(&original).unwrap().unwrap();
        assert_eq!((reads, writes), (2, 1));
        let mut result = original;
        for (start, end, replacement) in edits.into_iter().rev() {
            result.replace_range(start..end, &replacement);
        }
        assert!(result.contains("let saved = crate::rustbox_errno::get(); crate::rustbox_errno::set(f(crate::rustbox_errno::get(), saved));"));
        assert!(!result.contains("__errno_location"));
    }

    #[test]
    fn reject_address_and_ambiguous_bindings() {
        for stmt in [
            "let _p = __errno_location();",
            "let p = &raw mut *__errno_location();",
            "let ref p = *__errno_location();",
            "*__errno_location() += 1;",
            "let __errno_location = f;",
            "some_macro!(__errno_location);",
            "let b = *__errno_location() == ExternalValue;",
            "use other::*;",
        ] {
            let src =
                format!("{DECL}\nunsafe fn sample() {{ let a = *__errno_location(); {stmt} }}");
            assert!(scan(&src).unwrap().is_none(), "{stmt}");
        }
    }
}
