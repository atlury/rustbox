// SPDX-License-Identifier: 0BSD
//! Find closed sets of unused C layout declarations in a complete staticlib crate.
use proc_macro2::{TokenStream, TokenTree};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::path::{Component, Path};
use syn::spanned::Spanned;
use syn::visit::{self, Visit};
use syn::{Attribute, Fields, Item, Meta, Visibility};

type Names = BTreeSet<String>;

fn names(source: &str) -> Result<Names, Box<dyn Error>> {
    Ok(token_names(source.parse::<TokenStream>()?))
}

fn token_names(tokens: TokenStream) -> Names {
    let mut result = Names::new();
    let mut streams = vec![tokens];
    while let Some(stream) = streams.pop() {
        for token in stream {
            match token {
                TokenTree::Ident(id) => {
                    let name = id.to_string();
                    result.insert(name.trim_start_matches("r#").to_owned());
                }
                TokenTree::Group(group) => streams.push(group.stream()),
                _ => (),
            }
        }
    }
    result
}

fn layout_attrs(attrs: &[Attribute]) -> bool {
    attrs.iter().all(|attr| {
        let Meta::List(list) = &attr.meta else {
            return false;
        };
        let tokens = list.tokens.to_string().replace(' ', "");
        (list.path.is_ident("repr") && tokens == "C")
            || (list.path.is_ident("derive")
                && matches!(tokens.as_str(), "Copy,Clone" | "Clone,Copy"))
    })
}

fn candidate(item: &Item) -> Option<(&syn::Ident, &'static str)> {
    match item {
        Item::Struct(s)
            if matches!(s.vis, Visibility::Public(_))
                && s.generics.params.is_empty()
                && s.generics.where_clause.is_none()
                && layout_attrs(&s.attrs)
                && matches!(&s.fields, Fields::Named(fields) if fields.named.iter().all(|f| f.attrs.is_empty())) =>
        {
            Some((&s.ident, "struct"))
        }
        Item::Union(u)
            if matches!(u.vis, Visibility::Public(_))
                && u.generics.params.is_empty()
                && u.generics.where_clause.is_none()
                && layout_attrs(&u.attrs)
                && u.fields.named.iter().all(|f| f.attrs.is_empty()) =>
        {
            Some((&u.ident, "union"))
        }
        Item::Type(t)
            if matches!(t.vis, Visibility::Public(_))
                && t.attrs.is_empty()
                && t.generics.params.is_empty()
                && t.generics.where_clause.is_none() =>
        {
            Some((&t.ident, "type"))
        }
        _ => None,
    }
}

fn closure(mut live: Names, edges: &BTreeMap<String, Names>) -> Names {
    let mut queue: Vec<_> = live.iter().cloned().collect();
    while let Some(name) = queue.pop() {
        if let Some(next) = edges.get(&name) {
            for dependency in next {
                if live.insert(dependency.clone()) {
                    queue.push(dependency.clone());
                }
            }
        }
    }
    live
}

// A qualified path, an import or macro tokens may refer to a type in a
// different module even when a local type has exactly the same name.
struct ExternalNames(Names);

impl<'ast> Visit<'ast> for ExternalNames {
    fn visit_path(&mut self, path: &'ast syn::Path) {
        for segment in path
            .segments
            .iter()
            .skip(usize::from(path.leading_colon.is_none()))
        {
            self.0
                .insert(segment.ident.to_string().trim_start_matches("r#").into());
        }
        visit::visit_path(self, path);
    }

    fn visit_use_tree(&mut self, tree: &'ast syn::UseTree) {
        match tree {
            syn::UseTree::Name(name) => {
                self.0
                    .insert(name.ident.to_string().trim_start_matches("r#").into());
            }
            syn::UseTree::Rename(name) => {
                self.0
                    .insert(name.ident.to_string().trim_start_matches("r#").into());
            }
            _ => (),
        }
        visit::visit_use_tree(self, tree);
    }

    fn visit_macro(&mut self, mac: &'ast syn::Macro) {
        self.0.extend(token_names(mac.tokens.clone()));
        visit::visit_macro(self, mac);
    }

    fn visit_attribute(&mut self, attr: &'ast Attribute) {
        if let Meta::List(list) = &attr.meta {
            self.0.extend(token_names(list.tokens.clone()));
        }
        visit::visit_attribute(self, attr);
    }
}

type Site = (String, &'static str, usize, usize);
#[derive(Default)]
struct Module {
    roots: Names,
    edges: BTreeMap<String, Names>,
    pointers: Names,
    ranges: Vec<Site>,
}

fn removable(module: &Module, external: &Names) -> Names {
    let edges = &module.edges;
    let mut roots = module.roots.clone();
    let mut pointers = module.pointers.clone();
    roots.extend(
        edges
            .keys()
            .filter(|name| external.contains(*name))
            .cloned(),
    );
    let live = closure(roots, edges);
    let mut reverse: BTreeMap<String, Names> = BTreeMap::new();
    for (name, refs) in edges {
        if !live.contains(name) {
            for dependency in refs {
                reverse
                    .entry(dependency.clone())
                    .or_default()
                    .insert(name.clone());
            }
        }
    }
    pointers.retain(|name| !live.contains(name));
    closure(pointers, &reverse)
}

fn main() -> Result<(), Box<dyn Error>> {
    let root = std::env::args_os()
        .nth(1)
        .ok_or("expected crate directory")?;
    let files: Names = serde_json::from_reader(std::io::stdin().lock())?;
    let mut external = ExternalNames(Names::new());
    let mut modules = BTreeMap::new();
    let mut whole = Module::default();
    for module in files {
        let path = Path::new(&module);
        if !path.components().all(|c| matches!(c, Component::Normal(_)))
            || path.extension().is_none_or(|x| x != "rs")
        {
            return Err("expected crate-relative compiler input".into());
        }
        let text = std::fs::read_to_string(Path::new(&root).join(path))?;
        let ast = syn::parse_file(&text)?;
        let mut outside = text.as_bytes().to_vec();
        external.visit_file(&ast);
        if ast.items.iter().any(|item| matches!(item, Item::Mod(_))) {
            external.0.extend(names(&text)?);
        }
        let mut graph = Module::default();
        for item in &ast.items {
            let Some((id, kind)) = candidate(item) else {
                continue;
            };
            let span = item.span().byte_range();
            let definition = &text[span.clone()];
            let name = id.to_string().trim_start_matches("r#").to_owned();
            // Count dependencies conservatively, even identifiers used as field names.
            graph
                .edges
                .entry(name.clone())
                .or_default()
                .extend(names(definition)?);
            if definition.contains("*mut ") || definition.contains("*const ") {
                graph.pointers.insert(name.clone());
            }
            graph.ranges.push((name, kind, span.start, span.end));
            outside[span].fill(b' ');
        }
        graph.roots = names(std::str::from_utf8(&outside)?)?;
        whole.roots.extend(graph.roots.iter().cloned());
        whole.pointers.extend(graph.pointers.iter().cloned());
        for (name, refs) in &graph.edges {
            whole
                .edges
                .entry(name.clone())
                .or_default()
                .extend(refs.iter().cloned());
        }
        // Bare identifiers without a local definition may resolve via a glob.
        let other_names = graph
            .roots
            .iter()
            .chain(graph.edges.values().flatten())
            .filter(|name| !graph.edges.contains_key(*name));
        external.0.extend(other_names.cloned());
        modules.insert(module, graph);
    }
    let crate_unused = removable(&whole, &Names::new());
    let mut sites: BTreeMap<_, _> = modules
        .into_iter()
        .map(|(path, mut graph)| {
            let local_unused = removable(&graph, &external.0);
            graph
                .ranges
                .retain(|(name, ..)| crate_unused.contains(name) || local_unused.contains(name));
            (path, graph.ranges)
        })
        .collect();
    sites.retain(|_, rows| !rows.is_empty());
    serde_json::to_writer(std::io::stdout().lock(), &sites)?;
    Ok(())
}
