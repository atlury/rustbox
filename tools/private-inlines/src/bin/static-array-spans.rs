// SPDX-License-Identifier: 0BSD
use std::collections::BTreeMap;
use std::error::Error;
use std::io;
use std::path::{Component, PathBuf};
use syn::{Expr, Item};

// Return the byte intervals occupied by top-level array initializers.
// The independent C-string matcher supplies the verified literal edit spans.
fn main() -> Result<(), Box<dyn Error>> {
    let root = PathBuf::from(std::env::args_os().nth(1).ok_or("expected crate root")?);
    let files: Vec<PathBuf> = serde_json::from_reader(io::stdin().lock())?;
    let mut ranges = BTreeMap::new();
    for path in files {
        if path.extension().and_then(|s| s.to_str()) != Some("rs")
            || !path.components().all(|c| matches!(c, Component::Normal(_)))
        {
            return Err("expected crate-relative Rust module".into());
        }
        let source = std::fs::read_to_string(root.join(&path))?;
        let mut arrays = Vec::new();
        for item in syn::parse_file(&source)?.items {
            let expr = match item {
                Item::Static(item) => item.expr,
                Item::Const(item) => item.expr,
                _ => continue,
            };
            if let Expr::Array(array) = *expr {
                let brackets = array.bracket_token.span;
                arrays.push((brackets.open().byte_range().end, brackets.close().byte_range().start));
            }
        }
        ranges.insert(path, arrays);
    }
    serde_json::to_writer(io::stdout().lock(), &ranges)?;
    Ok(())
}
