"""Share the verified glibc FILE struct and its three opaque pointees in a single Cargo crate."""
# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
from pathlib import Path
import re

from prune_private_inlines import POINTER

# Digests cover the full translated definition, including repr and derive attributes.
DEFINITIONS = {
    "_IO_FILE": "43d4d57a841001cb6cd181b7611c32b417b99cd9f081824935150d3e7153d874",
    "_IO_marker": "9d8dfbfecb5db7758aad82268c1f1eca36a9a1ef6c7c85d888bf9bb5761a8918",
    "_IO_codecvt": "fa0eb369ce7eab5440643020e61ae4b29d59c8217d74744cf1e470c658595482",
    "_IO_wide_data": "ce2ab55b2909e60e0d9ed4585793e4ce3684a73262018aca3fcb605192fc00ae",
}
ALIASES = (b"pub type __off_t = ::core::ffi::c_long;", b"pub type __off64_t = ::core::ffi::c_long;",
           b"pub type size_t = usize;")
DECL = re.compile(rb"^(?:#\[[^\n]*\]\n)*pub struct (_IO_FILE|_IO_marker|_IO_codecvt|_IO_wide_data) \{\n[^{}]*?^\}\n", re.M)
GZIP_OWNER = Path("src/normalized_source/gzip.rs")


def declarations(data):
    if b"pub struct _IO_FILE {" not in data:
        return {}
    entries = {}
    for m in DECL.finditer(data):
        name = m[1].decode("ascii")
        if name in entries or hashlib.sha256(m[0]).hexdigest() != DEFINITIONS[name]:
            raise ValueError(f"unexpected glibc layout for {name}")
        entries[name] = m
    lines = data.splitlines()
    if entries.keys() != DEFINITIONS.keys() or any(lines.count(alias) != 1 for alias in ALIASES):
        raise ValueError("incomplete glibc FILE family or differing field aliases")
    return entries


def eligible(data):
    try:
        return bool(declarations(data))
    except ValueError:
        return False


def share(data, owner):
    entries = declarations(data)
    pieces = []
    end = 0
    if owner.suffix != ".rs" or not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", part) for part in owner.with_suffix("").parts):
        raise ValueError("expected a regular translated Rust module path")
    namespace = b"crate::" + b"::".join(part.encode("ascii") for part in owner.with_suffix("").parts)
    for name, m in entries.items():
        pieces += [data[end:m.start()], b"pub use " + namespace + b"::" + name.encode("ascii") + b";",
                   b"\n" * m[0].count(b"\n")]
        end = m.end()
    candidate = b"".join([*pieces, data[end:]])
    if entries and len(POINTER.findall(data)) - len(POINTER.findall(candidate)) != 18:
        raise ValueError("unexpected raw-pointer change in FILE layout")
    return candidate
