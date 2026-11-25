// SPDX-License-Identifier: 0BSD
use proc_macro2::{TokenStream, TokenTree};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io::{self, BufRead};
use std::path::{Component, PathBuf};
use syn::spanned::Spanned;
use syn::{ForeignItem, Item, Visibility};

fn count_names(tokens: TokenStream, counts: &mut BTreeMap<String, usize>) {
    for token in tokens {
        match token {
            TokenTree::Ident(id) => *counts.entry(id.to_string()).or_default() += 1,
            TokenTree::Group(group) => count_names(group.stream(), counts),
            _ => {}
        }
    }
}

// Read rustc diagnostics on stdin. Select only unattributed private declarations
// from a plain extern "C" block in a leaf module of this compilation.
fn main() -> Result<(), Box<dyn Error>> {
    let mut unused: BTreeMap<PathBuf, BTreeSet<(usize, String)>> = BTreeMap::new();
    for line in io::stdin().lock().lines() {
        let record: Value = serde_json::from_str(&line?)?;
        if record["level"] == "error" {
            return Err("compiler reported an error".into());
        }
        if record["code"]["code"] != "dead_code" {
            continue;
        }
        let message = record["message"].as_str().ok_or("missing message")?;
        let name = message
            .strip_prefix("function `")
            .or_else(|| message.strip_prefix("static `"));
        let Some(name) = name.and_then(|s| s.strip_suffix("` is never used")) else {
            continue;
        };
        for span in record["spans"].as_array().ok_or("missing spans")? {
            if span["is_primary"] != true || !span["expansion"].is_null() {
                continue;
            }
            let path = PathBuf::from(span["file_name"].as_str().ok_or("missing filename")?);
            if !path.components().all(|c| matches!(c, Component::Normal(_))) {
                return Err("expected a crate-relative compiler input".into());
            }
            let offset = usize::try_from(span["byte_start"].as_u64().ok_or("missing offset")?)?;
            unused
                .entry(path)
                .or_default()
                .insert((offset, name.into()));
        }
    }
    let mut result = BTreeMap::new();
    for (path, names) in unused {
        let source = fs::read_to_string(&path)?;
        let ast = syn::parse_file(&source)?;
        if ast.items.iter().any(|item| matches!(item, Item::Mod(_))) {
            continue;
        }
        let mut counts = BTreeMap::new();
        count_names(source.parse()?, &mut counts);
        let mut ranges = Vec::new();
        for item in ast.items {
            let Item::ForeignMod(block) = item else {
                continue;
            };
            if !block.attrs.is_empty()
                || block.abi.name.as_ref().map(|s| s.value()).as_deref() != Some("C")
            {
                continue;
            }
            for decl in block.items {
                let (ident, start, end) = match decl {
                    ForeignItem::Fn(f)
                        if f.attrs.is_empty() && matches!(f.vis, Visibility::Inherited) =>
                    {
                        (
                            f.sig.ident.clone(),
                            f.sig.span().byte_range().start,
                            f.semi_token.span.byte_range().end,
                        )
                    }
                    ForeignItem::Static(s)
                        if s.attrs.is_empty() && matches!(s.vis, Visibility::Inherited) =>
                    {
                        (
                            s.ident,
                            s.static_token.span.byte_range().start,
                            s.semi_token.span.byte_range().end,
                        )
                    }
                    _ => continue,
                };
                let name = ident.to_string();
                if counts.get(&name) == Some(&1)
                    && names.contains(&(ident.span().byte_range().start, name))
                {
                    ranges.push([start, end]);
                }
            }
        }
        if !ranges.is_empty() {
            result.insert(path, ranges);
        }
    }
    serde_json::to_writer(io::stdout().lock(), &result)?;
    Ok(())
}
