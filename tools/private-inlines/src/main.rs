// SPDX-License-Identifier: 0BSD
use proc_macro2::{TokenStream, TokenTree};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::error::Error;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Component, Path, PathBuf};
use syn::{Item, Meta, Visibility};

// Only unreferenced, private inline functions in leaf modules are eligible.
// Requiring a single identifier token also excludes calls from other dead items.
fn identifiers(tokens: TokenStream, counts: &mut HashMap<String, usize>) {
    for token in tokens {
        match token {
            TokenTree::Ident(id) => *counts.entry(id.to_string()).or_default() += 1,
            TokenTree::Group(group) => identifiers(group.stream(), counts),
            _ => {}
        }
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let [root, diagnostics, output] = &args[..] else {
        return Err("usage: rustbox-inline-audit CRATE RUSTC_JSON EMPTY_OUTPUT".into());
    };
    let out = Path::new(output);
    fs::create_dir(out)?;
    let mut candidates: BTreeMap<PathBuf, BTreeSet<(usize, String)>> = BTreeMap::new();
    for line in BufReader::new(fs::File::open(diagnostics)?).lines() {
        let record: Value = serde_json::from_str(&line?)?;
        if record["level"] == "error" {
            return Err("compiler reported an error".into());
        }
        if record["code"]["code"] != "dead_code" {
            continue;
        }
        let Some(name) = record["message"]
            .as_str()
            .and_then(|s| s.strip_prefix("function `"))
            .and_then(|s| s.strip_suffix("` is never used"))
        else {
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
            let start = usize::try_from(span["byte_start"].as_u64().ok_or("missing offset")?)?;
            candidates
                .entry(path)
                .or_default()
                .insert((start, name.to_owned()));
        }
    }
    let mut removals = BTreeMap::new();
    let mut functions = 0usize;
    let mut files = 0usize;
    for (path, eligible) in candidates {
        let source = fs::read_to_string(Path::new(root).join(&path))?;
        let ast = syn::parse_file(&source)?;
        if ast.items.iter().any(|i| matches!(i, Item::Mod(_))) {
            continue;
        }
        let mut counts = HashMap::new();
        identifiers(source.parse().map_err(|_| "invalid tokens")?, &mut counts);
        let mut ranges = Vec::new();
        for item in ast.items {
            let Item::Fn(f) = item else {
                continue;
            };
            let name = f.sig.ident.to_string();
            if !eligible.contains(&(f.sig.ident.span().byte_range().start, name.clone()))
                || counts.get(&name) != Some(&1)
                || !matches!(f.vis, Visibility::Inherited)
                || f.attrs.len() != 1
                || !matches!(&f.attrs[0].meta, Meta::Path(p) if p.is_ident("inline"))
            {
                continue;
            }
            ranges.push(
                f.attrs[0].pound_token.span.byte_range().start
                    ..f.block.brace_token.span.close().byte_range().end,
            );
        }
        if ranges.is_empty() {
            continue;
        }
        removals.insert(
            path.clone(),
            ranges.iter().map(|r| [r.start, r.end]).collect::<Vec<_>>(),
        );
        functions += ranges.len();
        files += 1;
        let mut data = source.into_bytes();
        for range in ranges.into_iter().rev() {
            // Preserve source line numbering used by diagnostics and assertion messages.
            data.splice(
                range.clone(),
                vec![b'\n'; data[range].iter().filter(|&&b| b == b'\n').count()],
            );
        }
        let destination = out.join(path);
        fs::create_dir_all(destination.parent().ok_or("missing parent")?)?;
        fs::write(destination, data)?;
    }
    serde_json::to_writer(fs::File::create(out.join("ranges.json"))?, &removals)?;
    println!("{functions} private inline functions in {files} files");
    Ok(())
}
