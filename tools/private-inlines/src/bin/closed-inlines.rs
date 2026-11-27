// SPDX-License-Identifier: 0BSD
use proc_macro2::{TokenStream, TokenTree};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::io;
use std::ops::Range;
use std::path::{Component, Path};
use syn::{Item, Meta, Visibility};

type Sites = BTreeMap<String, usize>;
type Plan = BTreeMap<String, ([usize; 2], bool)>;

fn identifiers(tokens: TokenStream, visit: &mut impl FnMut(String)) {
    for token in tokens {
        match token {
            TokenTree::Ident(name) => visit(name.to_string()),
            TokenTree::Group(group) => identifiers(group.stream(), visit),
            _ => {}
        }
    }
}

fn plan(source: &str, sites: Option<&Sites>) -> Result<Plan, Box<dyn Error>> {
    let ast = syn::parse_file(source)?;
    let mut spans = BTreeMap::<String, Range<usize>>::new();
    for item in ast.items {
        if matches!(item, Item::Mod(_)) {
            return Ok(Plan::new());
        }
        let Item::Fn(f) = item else { continue };
        let [attr] = &f.attrs[..] else { continue };
        if !matches!(f.vis, Visibility::Inherited)
            || !matches!(&attr.meta, Meta::Path(p) if p.is_ident("inline"))
        {
            continue;
        }
        let name = f.sig.ident.to_string();
        let start = f.sig.ident.span().byte_range().start;
        if sites.is_some_and(|s| s.get(&name) != Some(&start)) {
            continue;
        }
        let span = attr.pound_token.span.byte_range().start
            ..f.block.brace_token.span.close().byte_range().end;
        if spans.insert(name, span).is_some() {
            return Ok(Plan::new());
        }
    }
    if spans.is_empty() {
        return Ok(Plan::new());
    }

    // Count references outside candidate bodies, including types, attributes and macro tokens.
    let mut outside: BTreeMap<_, usize> = spans.keys().map(|name| (name.clone(), 0)).collect();
    identifiers(source.parse()?, &mut |name| {
        if let Some(count) = outside.get_mut(&name) {
            *count += 1;
        }
    });
    let single: BTreeSet<_> = outside
        .iter()
        .filter(|(_, count)| **count == 1)
        .map(|(name, _)| name.clone())
        .collect();
    let mut edges = BTreeMap::new();
    for (name, span) in &spans {
        let mut calls = BTreeSet::new();
        identifiers(source[span.clone()].parse()?, &mut |id| {
            if let Some(count) = outside.get_mut(&id) {
                *count -= 1;
                calls.insert(id);
            }
        });
        edges.insert(name.clone(), calls);
    }

    // Keep the transitive dependencies of every function referenced outside the group.
    let mut queue: Vec<_> = outside
        .into_iter()
        .filter(|(_, n)| *n > 0)
        .map(|(n, _)| n)
        .collect();
    while let Some(name) = queue.pop() {
        if let Some(calls) = edges.remove(&name) {
            queue.extend(calls);
        }
    }
    Ok(edges
        .into_keys()
        .map(|name| {
            let span = &spans[&name];
            let referenced = !single.contains(&name);
            (name, ([span.start, span.end], referenced))
        })
        .collect())
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args_os()
        .nth(1)
        .ok_or("expected a crate directory")?;
    // Null entries request a source-only estimate. A build supplies rustc's exact dead-code sites.
    let inputs: BTreeMap<String, Option<Sites>> = serde_json::from_reader(io::stdin().lock())?;
    let mut output = BTreeMap::new();
    for (path, sites) in inputs {
        if Path::new(&path).extension().is_none_or(|x| x != "rs")
            || !Path::new(&path)
                .components()
                .all(|part| matches!(part, Component::Normal(_)))
        {
            return Err("expected a crate-relative Rust source".into());
        }
        let source = fs::read_to_string(Path::new(&root).join(&path))?;
        let ranges = plan(&source, sites.as_ref())?;
        if !ranges.is_empty() {
            output.insert(path, ranges);
        }
    }
    serde_json::to_writer(io::stdout().lock(), &output)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_live_edges_and_rejects_stale_compiler_offsets() {
        let src = r#"
#[inline] fn a() { b(); }
#[inline] fn b() { a(); }
#[inline] fn c() { d(); }
#[inline] fn d() {}
pub fn entry() { c(); }
"#;
        let all = plan(src, None).unwrap();
        assert_eq!(
            all.keys().map(String::as_str).collect::<Vec<_>>(),
            ["a", "b"]
        );
        let mut sites = Sites::from([
            ("a".into(), src.find("fn a").unwrap() + 3),
            ("b".into(), src.find("fn b").unwrap() + 3),
        ]);
        assert_eq!(plan(src, Some(&sites)).unwrap(), all);
        sites.insert("a".into(), 0);
        assert!(plan(src, Some(&sites)).unwrap().is_empty());
        assert!(plan(&format!("{src}\nmod child;"), None)
            .unwrap()
            .is_empty());
    }
}
