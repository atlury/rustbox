#!/usr/bin/env python3
"""Mechanically make reachable C2Rust 0.22 output build on current stable Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path


EXTERN_TYPE = re.compile(r"^\s*pub type ([A-Za-z_][A-Za-z0-9_]*);\s*$")
STATIC_MUT = re.compile(r"^\s*(?:pub\s+)?static\s+mut\s+([A-Za-z_][A-Za-z0-9_]*):")
TYPE_ALIAS = re.compile(
    r"^\s*pub\s+type\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$"
)
LOCAL_VALUE_BINDING = re.compile(
    r"\b(?:let\s+(?:mut\s+)?|mut\s+)([A-Za-z_][A-Za-z0-9_]*)\s*:"
)
RUST_LITERAL = re.compile(
    r"(?:b|c)?r\#*\".*?\"\#*|(?:b|c)?\"(?:\\.|[^\"\\])*\"|b?'(?:\\.|[^'\\])*'"
)
NO_MANGLE_FUNCTION = re.compile(
    r'(?m)^#\[no_mangle\]\n'
    r'(?=(?:#\[[^\n]+\]\n)*pub\s+(?:(?:unsafe|extern\s+"C")\s+)*fn\s+'
    r'([A-Za-z_][A-Za-z0-9_]*))'
)
NO_MANGLE_STATIC = re.compile(
    r'(?m)^#\[no_mangle\]\n'
    r'(?=(?:#\[[^\n]+\]\n)*pub\s+static\s+(?:mut\s+)?'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*:)'
)
ATOMIC_XCHG_ACQUIRE_I32 = re.compile(
    r"::core::intrinsics::atomic_xchg_acquire\(\n"
    r"(?P<indent>\s*)&raw mut (?P<name>[A-Za-z_][A-Za-z0-9_]*),\n"
    r"(?P=indent)(?P<value>[^\n]+ as ::core::ffi::c_int),\n"
    r"(?P<close>\s*)\)"
)
WRITE_VOLATILE_BEFORE_IF = re.compile(
    r"(?ms)(?P<call>^(?P<indent>[ \t]*)::core::ptr::write_volatile\(\n"
    r".*?^(?P=indent)\))\n(?P=indent)if "
)
ASM_CAST_MUTABLE_BORROW = re.compile(
    r"(?m)^(?P<indent>[ \t]*)let (?P<name>fresh[0-9]+) = &mut "
    r"(?P<value>[A-Za-z_][A-Za-z0-9_]*);$"
)
REMOVED_FEATURES = {
    "#![feature(asm)]",
    "#![feature(c_variadic)]",
    "#![feature(core_intrinsics)]",
    "#![feature(extern_types)]",
    "#![feature(label_break_value)]",
    "#![feature(linkage)]",
    "#![feature(raw_ref_op)]",
    "#![feature(stdsimd)]",
}

CHECKED_ARITHMETIC_SUPPORT = r'''

// C23 stdckdint operations evaluate their operands at infinite precision,
// store the low destination bits, and report whether the mathematical result
// fits the destination type.  C2Rust 0.22 instead emits Rust's same-type
// overflowing_* methods, which reject valid C calls with mixed integer types.
// Keep this compatibility layer private to mechanically modernized crates.
#[doc(hidden)]
pub trait RustboxC2RustCkdInt: Copy {
    const MIN_I128: i128;
    const MAX_I128: i128;
    fn rustbox_to_i128(self) -> i128;
    fn rustbox_from_i128_wrapping(value: i128) -> Self;
}

macro_rules! rustbox_c2rust_ckd_signed {
    ($($type:ty),+ $(,)?) => {$ (
        impl RustboxC2RustCkdInt for $type {
            const MIN_I128: i128 = <$type>::MIN as i128;
            const MAX_I128: i128 = <$type>::MAX as i128;
            fn rustbox_to_i128(self) -> i128 { self as i128 }
            fn rustbox_from_i128_wrapping(value: i128) -> Self { value as Self }
        }
    )+};
}

macro_rules! rustbox_c2rust_ckd_unsigned {
    ($($type:ty),+ $(,)?) => {$ (
        impl RustboxC2RustCkdInt for $type {
            const MIN_I128: i128 = 0;
            const MAX_I128: i128 = <$type>::MAX as i128;
            fn rustbox_to_i128(self) -> i128 { self as i128 }
            fn rustbox_from_i128_wrapping(value: i128) -> Self { value as Self }
        }
    )+};
}

rustbox_c2rust_ckd_signed!(i8, i16, i32, i64, isize);
rustbox_c2rust_ckd_unsigned!(u8, u16, u32, u64, usize);

#[doc(hidden)]
pub fn rustbox_c2rust_ckd_add<O, A, B>(left: A, right: B) -> (O, bool)
where
    O: RustboxC2RustCkdInt,
    A: RustboxC2RustCkdInt,
    B: RustboxC2RustCkdInt,
{
    let left = left.rustbox_to_i128();
    let right = right.rustbox_to_i128();
    let exact = left.checked_add(right);
    let low_bits = left.wrapping_add(right);
    let overflow = exact.is_none_or(|value| value < O::MIN_I128 || O::MAX_I128 < value);
    (O::rustbox_from_i128_wrapping(low_bits), overflow)
}

#[doc(hidden)]
pub fn rustbox_c2rust_ckd_sub<O, A, B>(left: A, right: B) -> (O, bool)
where
    O: RustboxC2RustCkdInt,
    A: RustboxC2RustCkdInt,
    B: RustboxC2RustCkdInt,
{
    let left = left.rustbox_to_i128();
    let right = right.rustbox_to_i128();
    let exact = left.checked_sub(right);
    let low_bits = left.wrapping_sub(right);
    let overflow = exact.is_none_or(|value| value < O::MIN_I128 || O::MAX_I128 < value);
    (O::rustbox_from_i128_wrapping(low_bits), overflow)
}

#[doc(hidden)]
pub fn rustbox_c2rust_ckd_mul<O, A, B>(left: A, right: B) -> (O, bool)
where
    O: RustboxC2RustCkdInt,
    A: RustboxC2RustCkdInt,
    B: RustboxC2RustCkdInt,
{
    let left = left.rustbox_to_i128();
    let right = right.rustbox_to_i128();
    let exact = left.checked_mul(right);
    let low_bits = left.wrapping_mul(right);
    let overflow = exact.is_none_or(|value| value < O::MIN_I128 || O::MAX_I128 < value);
    (O::rustbox_from_i128_wrapping(low_bits), overflow)
}
'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matching_parenthesis(text: str, opening: int) -> int:
    """Find a generated Rust call's close delimiter without parsing its AST."""
    depth = 1
    quote: str | None = None
    escaped = False
    index = opening + 1
    while index < len(text):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise RuntimeError("unterminated C2Rust overflowing arithmetic call")


def remove_bool_call_integer_comparisons(text: str) -> tuple[str, int]:
    """Remove C2Rust's redundant integer comparison from bool-returning calls."""
    names = set()
    signature = re.compile(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    for match in signature.finditer(text):
        opening = text.find("(", match.start())
        closing = matching_parenthesis(text, opening)
        if re.match(r"\s*->\s*bool\b", text[closing + 1:]):
            names.add(match.group(1))
    rewrites = 0
    for name in sorted(names):
        pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
        search_from = 0
        while match := pattern.search(text, search_from):
            opening = text.find("(", match.start())
            closing = matching_parenthesis(text, opening)
            suffix = re.match(r"\s*!=\s*0\b", text[closing + 1:])
            if suffix is None:
                search_from = closing + 1
                continue
            text = text[:closing + 1] + text[closing + 1 + suffix.end():]
            rewrites += 1
            search_from = closing + 1
    return text, rewrites


def rewrite_checked_arithmetic(text: str) -> tuple[str, int]:
    """Replace C2Rust's invalid same-type spelling of C23 ckd_* calls."""
    pattern = re.compile(r"\.overflowing_(add|sub|mul)\(")
    rewrites = 0
    search_from = 0
    while match := pattern.search(text, search_from):
        statement = text.rfind("let (", 0, match.start())
        previous_semicolon = text.rfind(";", 0, match.start())
        if statement < 0 or statement < previous_semicolon:
            raise RuntimeError("overflowing arithmetic is not in C2Rust tuple form")
        equals = text.find("=", statement, match.start())
        if equals < 0:
            raise RuntimeError("C2Rust overflowing arithmetic has no result binding")
        receiver_start = equals + 1
        while text[receiver_start].isspace():
            receiver_start += 1
        receiver = text[receiver_start:match.start()].strip()
        if not receiver:
            raise RuntimeError("C2Rust overflowing arithmetic has no receiver")
        opening = match.end() - 1
        closing = matching_parenthesis(text, opening)
        argument = text[opening + 1:closing].strip()
        operation = match.group(1)
        replacement = (
            f"crate::rustbox_c2rust_ckd_{operation}("
            f"{receiver}, {argument})"
        )
        text = text[:receiver_start] + replacement + text[closing + 1:]
        rewrites += 1
        search_from = receiver_start + len(replacement)
    return text, rewrites


def rewrite_asm_cast_mutable_borrows(text: str) -> tuple[str, int]:
    """Use a raw pointer for C2Rust's inline-assembly output destination.

    C2Rust keeps an `&mut` binding alive across the copied input value and the
    final result read.  Current stable Rust correctly rejects those overlapping
    accesses.  The assembly compatibility helper needs a mutable reference only
    at each call boundary, so retain C's raw-pointer aliasing and create the
    short-lived references at those two calls.
    """
    rewrites = 0
    search_from = 0
    while match := ASM_CAST_MUTABLE_BORROW.search(text, search_from):
        function_end = text.find('\nunsafe extern "C" fn ', match.end())
        if function_end < 0:
            function_end = len(text)
        body = text[match.end():function_end]
        name = match.group("name")
        cast_in = f"c2rust_asm_casts::AsmCast::cast_in({name},"
        cast_out = f"c2rust_asm_casts::AsmCast::cast_out({name},"
        if body.count(cast_in) != 1 or body.count(cast_out) != 1:
            search_from = match.end()
            continue
        replacement = (
            f'{match.group("indent")}let {name} = &raw mut '
            f'{match.group("value")};'
        )
        text = text[:match.start()] + replacement + text[match.end():]
        function_end += len(replacement) - (match.end() - match.start())
        body_start = match.start() + len(replacement)
        body = text[body_start:function_end]
        body = body.replace(cast_in, f"c2rust_asm_casts::AsmCast::cast_in(&mut *{name},", 1)
        body = body.replace(cast_out, f"c2rust_asm_casts::AsmCast::cast_out(&mut *{name},", 1)
        text = text[:body_start] + body + text[function_end:]
        rewrites += 1
        search_from = body_start + len(body)
    return text, rewrites


def has_only_pointer_uses(line: str, name: str) -> bool:
    """Accept every occurrence only when it denotes or constructs a raw pointer."""
    escaped = re.escape(name)
    # A spelling inside a byte/string/character literal or trailing comment is
    # data, not a Rust identifier use.  C2Rust commonly emits option names that
    # happen to match opaque C tags (for example b"exclude\\0").
    residual = RUST_LITERAL.sub("", line)
    residual = "\n".join(line.split("//", 1)[0] for line in residual.splitlines())
    # A C field and an opaque tag can legitimately share a spelling.  Remove
    # Rust field/argument labels and field accesses before classifying
    # occurrences in type position.  A dot cannot introduce a Rust type path.
    residual = re.sub(rf"\b{escaped}\s*:", "", residual)
    residual = re.sub(rf"\.\s*{escaped}\b", "", residual)
    allowed = (
        rf"\*(?:mut|const)\s+{escaped}\b",
        rf"\bnull(?:_mut)?\s*::\s*<\s*{escaped}\s*,?\s*>",
    )
    for pattern in allowed:
        residual = re.sub(pattern, "", residual)
    return re.search(rf"\b{escaped}\b", residual) is None


def has_by_value_type_use(text: str, name: str) -> bool:
    """Detect type-position uses after a local shadows an opaque C tag.

    Rust keeps type and value identifiers in separate namespaces.  C2Rust can
    therefore emit both ``pub type kwset;`` and ``let mut kwset: kwset_t`` in
    one module.  Bare occurrences in that local's expressions are values, but
    the constructs below still denote a by-value type and must remain fatal.
    """
    escaped = re.escape(name)
    residual = RUST_LITERAL.sub("", text)
    residual = "\n".join(line.split("//", 1)[0] for line in residual.splitlines())
    residual = re.sub(rf"\*(?:mut|const)\s+{escaped}\b", "", residual)
    residual = re.sub(
        rf"\bnull(?:_mut)?\s*::\s*<\s*{escaped}\s*,?\s*>", "", residual
    )
    forbidden = (
        rf"(?<!:):\s*{escaped}\b",
        rf"->\s*{escaped}\b",
        rf"\bas\s+{escaped}\b",
        rf"::\s*<\s*{escaped}\b",
        rf"\btype\s+[A-Za-z_][A-Za-z0-9_]*\s*=[^;\n]*\b{escaped}\b",
        rf"\bstruct\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^;\n]*\b{escaped}\b",
        rf"\[\s*{escaped}\s*;",
    )
    return any(re.search(pattern, residual, re.DOTALL) for pattern in forbidden)


def alias_has_only_pointer_uses(
    lines: list[str], name: str, visited: frozenset[str] = frozenset()
) -> bool:
    """Accept an opaque alias chain only when every leaf use is a pointer use."""
    if name in visited:
        return False
    descendants = visited | {name}
    for index, line in enumerate(lines):
        if not re.search(rf"\b{re.escape(name)}\b", line):
            continue
        alias = TYPE_ALIAS.match(line)
        if alias is not None and alias.group(1) == name:
            continue
        if alias is not None and alias.group(2) == name:
            if not alias_has_only_pointer_uses(lines, alias.group(1), descendants):
                return False
            continue
        if not has_only_pointer_uses(line, name):
            # C2Rust can line-wrap null_mut::<Opaque,>() and raw-pointer type
            # arguments.  Classify the complete local construct rather than
            # treating the continuation line as a by-value opaque use.
            context = "\n".join(lines[max(0, index - 2):index + 3])
            if not has_only_pointer_uses(context, name):
                return False
    return True


def deduplicate_no_mangle_functions(root: Path) -> list[dict[str, object]]:
    """Mangle archive members shadowed by a configured program definition.

    C archives only extract a member when one of its symbols is needed.  A
    Rust crate compiles every translated module together, so an otherwise
    unused gnulib member can collide with the program's configured override.
    Keep the program definition exported and retain each shadowed function as
    ordinary mangled Rust code.
    """
    definitions: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        for match in NO_MANGLE_FUNCTION.finditer(text):
            definitions.setdefault(match.group(1), []).append(path)

    changes = []
    for name, paths in sorted(definitions.items()):
        if len(paths) == 1:
            continue
        ordered = sorted(
            paths,
            key=lambda path: ("src/src" not in path.relative_to(root).as_posix(),
                              path.relative_to(root).as_posix()),
        )
        kept = ordered[0]
        for path in ordered[1:]:
            text = path.read_text(encoding="utf-8")
            matches = [match for match in NO_MANGLE_FUNCTION.finditer(text)
                       if match.group(1) == name]
            if len(matches) != 1:
                raise RuntimeError(f"cannot uniquely mangle duplicate export {name} in {path}")
            match = matches[0]
            text = text[:match.start()] + text[match.start() + len("#[no_mangle]\n"):]
            path.write_text(text, encoding="utf-8")
            changes.append({
                "symbol": name,
                "kept": kept.relative_to(root).as_posix(),
                "mangled": path.relative_to(root).as_posix(),
            })
    return changes


def deduplicate_no_mangle_statics(root: Path) -> list[dict[str, object]]:
    """Mangle duplicate globals that came from separate C executables.

    C2Rust combines every compilation-database action into one crate.  Two
    canonical programs can therefore contribute same-named public globals
    that never collided in C.  Keep the first deterministic definition at its
    C ABI name and give later definitions ordinary Rust-mangled linkage.
    """
    definitions: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        for match in NO_MANGLE_STATIC.finditer(text):
            definitions.setdefault(match.group(1), []).append(path)

    changes = []
    for name, paths in sorted(definitions.items()):
        if len(paths) == 1:
            continue
        ordered = sorted(paths, key=lambda path: path.relative_to(root).as_posix())
        kept = ordered[0]
        for path in ordered[1:]:
            text = path.read_text(encoding="utf-8")
            matches = [match for match in NO_MANGLE_STATIC.finditer(text)
                       if match.group(1) == name]
            if len(matches) != 1:
                raise RuntimeError(f"cannot uniquely mangle duplicate static {name} in {path}")
            match = matches[0]
            text = text[:match.start()] + text[match.start() + len("#[no_mangle]\n"):]
            path.write_text(text, encoding="utf-8")
            changes.append({
                "symbol": name,
                "kept": kept.relative_to(root).as_posix(),
                "mangled": path.relative_to(root).as_posix(),
            })
    return changes


def deduplicate_function_static_exports(root: Path) -> list[dict[str, object]]:
    """Mangle program-local statics that collide with an exported function.

    Separate C executables may use one spelling for a global variable and an
    unrelated function.  A compile-audit crate combines those namespaces.
    Preserve the function ABI and retain the directly referenced Rust static
    under its ordinary mangled symbol.
    """
    functions: dict[str, Path] = {}
    statics: dict[str, Path] = {}
    for path in sorted(root.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        for match in NO_MANGLE_FUNCTION.finditer(text):
            if match.group(1) in functions:
                raise RuntimeError(f"duplicate function survived: {match.group(1)}")
            functions[match.group(1)] = path
        for match in NO_MANGLE_STATIC.finditer(text):
            if match.group(1) in statics:
                raise RuntimeError(f"duplicate static survived: {match.group(1)}")
            statics[match.group(1)] = path

    changes = []
    for name in sorted(functions.keys() & statics.keys()):
        path = statics[name]
        text = path.read_text(encoding="utf-8")
        matches = [
            match for match in NO_MANGLE_STATIC.finditer(text)
            if match.group(1) == name
        ]
        if len(matches) != 1:
            raise RuntimeError(f"cannot uniquely mangle cross-kind export {name}")
        match = matches[0]
        text = text[:match.start()] + text[match.start() + len("#[no_mangle]\n"):]
        path.write_text(text, encoding="utf-8")
        changes.append({
            "symbol": name,
            "kept": functions[name].relative_to(root).as_posix(),
            "mangled": path.relative_to(root).as_posix(),
            "kind": "function-over-static",
        })
    return changes


def transform_rust(
    path: Path, *, install_checked_arithmetic_support: bool = False
) -> dict[str, object] | None:
    before = path.read_text(encoding="utf-8")
    lines = before.splitlines()
    opaque = [match.group(1) for line in lines if (match := EXTERN_TYPE.match(line))]
    external_linkage_attributes = sum(
        line.strip() == '#[linkage = "external"]' for line in lines
    )
    kept = [
        line for line in lines
        if not EXTERN_TYPE.match(line)
        and line not in REMOVED_FEATURES
        and line.strip() != '#[linkage = "external"]'
    ]

    # C permits `await` as a field name while modern Rust reserves it.  Keep
    # the generated C layout and spelling with Rust's raw-identifier syntax.
    await_field_rewrites = 0
    rewritten = []
    for line in kept:
        changed, definitions = re.subn(r"\bawait(?=\s*:)", "r#await", line)
        changed, accesses = re.subn(r"(?<=\.)await\b", "r#await", changed)
        await_field_rewrites += definitions + accesses
        rewritten.append(changed)
    kept = rewritten

    mutable_statics = {
        match.group(1) for line in kept if (match := STATIC_MUT.match(line))
    }
    local_value_bindings = {
        match.group(1) for line in kept if (match := LOCAL_VALUE_BINDING.search(line))
    }
    raw_static_pointer_rewrites: list[str] = []
    for name in sorted(mutable_statics):
        mutable_pattern = re.compile(rf"&mut\s+{re.escape(name)}\s+as\s+\*mut\b")
        const_pattern = re.compile(rf"&\s*{re.escape(name)}\s+as\s+\*const\b")
        rewritten = []
        for line in kept:
            changed, mutable_count = mutable_pattern.subn(
                f"&raw mut {name} as *mut", line
            )
            changed, const_count = const_pattern.subn(
                f"&raw const {name} as *const", changed
            )
            if mutable_count or const_count:
                raw_static_pointer_rewrites.extend(
                    [name] * (mutable_count + const_count)
                )
            rewritten.append(changed)
        kept = rewritten

    for name in opaque:
        uses = [
            (index, line)
            for index, line in enumerate(kept)
            if re.search(rf"\b{re.escape(name)}\b", line)
        ]
        for index, line in uses:
            alias = TYPE_ALIAS.match(line)
            if alias is not None and alias.group(2) == name:
                if alias_has_only_pointer_uses(kept, alias.group(1)):
                    continue
            if not has_only_pointer_uses(line, name):
                context = "\n".join(kept[max(0, index - 2):index + 3])
                if not has_only_pointer_uses(context, name):
                    if name in local_value_bindings and not has_by_value_type_use(context, name):
                        continue
                    raise RuntimeError(f"{path}: opaque type {name} has non-pointer use: {line}")

    # C variadics are stable now, but C2Rust 0.22 emitted the old internal
    # VaListImpl spelling and borrowed it through as_va_list().  The stable
    # public type is VaList itself; clone() is its stable va_copy operation and
    # supplies an independently owned cursor to each by-value C ABI call.  Rust
    # 1.99 renamed the cursor-reading method from arg() to next_arg().
    va_list_impl_rewrites = sum(line.count("::core::ffi::VaListImpl") for line in kept)
    as_va_list_rewrites = sum(line.count(".as_va_list()") for line in kept)
    va_arg_rewrites = sum(line.count(".arg::<") for line in kept)
    kept = [
        line.replace("::core::ffi::VaListImpl", "::core::ffi::VaList")
        .replace(".as_va_list()", ".clone()")
        .replace(".arg::<", ".next_arg::<")
        for line in kept
    ]

    # GCC's __sync_lock_test_and_set on a volatile sig_atomic_t becomes the
    # old internal atomic_xchg_acquire intrinsic.  For C int, AtomicI32::swap
    # has the same aligned atomic exchange and acquire ordering on stable Rust.
    # Keep this deliberately narrow: any other type/shape remains visible as
    # an unsupported intrinsic instead of being guessed at.
    joined = "\n".join(kept)
    atomic_xchg_acquire_rewrites = 0

    def stable_atomic_exchange(match: re.Match[str]) -> str:
        nonlocal atomic_xchg_acquire_rewrites
        atomic_xchg_acquire_rewrites += 1
        indent = match.group("indent")
        return (
            "::core::sync::atomic::AtomicI32::from_ptr(\n"
            f"{indent}&raw mut {match.group('name')},\n"
            f"{match.group('close')})\n"
            f"{indent}.swap(\n"
            f"{indent}    {match.group('value')},\n"
            f"{indent}    ::core::sync::atomic::Ordering::Acquire,\n"
            f"{indent})"
        )

    joined = ATOMIC_XCHG_ACQUIRE_I32.sub(stable_atomic_exchange, joined)
    joined, asm_cast_mutable_borrow_rewrites = rewrite_asm_cast_mutable_borrows(joined)

    # Gnulib's memset_explicit compiler barrier carries an otherwise empty
    # assembly template plus one input operand.  Current Rust requires every
    # operand to be named in the template.  Mention it inside an assembly
    # comment: emitted machine code stays empty while the compiler dependency
    # that prevents dead-store elimination is preserved.
    empty_asm_input_rewrites = joined.count(
        'asm!("\\n", in (reg) & s, options(preserves_flags, att_syntax));'
    )
    joined = joined.replace(
        'asm!("\\n", in (reg) & s, options(preserves_flags, att_syntax));',
        'asm!("/* {0} */", in (reg) & s, options(preserves_flags, att_syntax));',
    )

    # Rust has no integer-to-bool cast.  C2Rust emits this spelling for C's
    # exact `_Bool` conversion (zero is false, every nonzero value is true).
    # Preserve that conversion directly instead of guessing at the integer
    # expression that produced it.
    joined, integer_to_bool_rewrites = re.subn(
        r"\)\s+as bool", ") != 0", joined
    )
    joined, bool_call_comparison_rewrites = remove_bool_call_integer_comparisons(joined)

    # C2Rust 0.22 can omit the statement terminator between an expanded
    # volatile decrement and the following loop condition.  Match only a
    # complete write_volatile call whose closing delimiter and `if` share the
    # same indentation.
    def terminate_write_volatile(match: re.Match[str]) -> str:
        return f"{match.group('call')};\n{match.group('indent')}if "

    joined, write_volatile_semicolon_rewrites = WRITE_VOLATILE_BEFORE_IF.subn(
        terminate_write_volatile, joined
    )
    joined, checked_arithmetic_rewrites = rewrite_checked_arithmetic(joined)

    # gnulib's hash-set prime table is declared as size_t while its values
    # above INT_MAX are emitted by C2Rust as c_ulong.  Both types have the same
    # width and representation on the pinned x86_64 GNU target; make that
    # target fact explicit so stable Rust accepts the array initializer.
    size_t_array_literal_rewrites = 0
    size_t_array_sentinel_rewrites = 0
    if path.name == "gl_hash_set.rs":
        size_t_array_literal_rewrites = joined.count(
            "as ::core::ffi::c_ulong,"
        )
        size_t_array_sentinel_rewrites = joined.count("    SIZE_MAX,\n];")
        if size_t_array_literal_rewrites != 126 \
                or size_t_array_sentinel_rewrites != 1:
            raise RuntimeError(f"{path}: gnulib size_t prime table changed")
        joined = joined.replace(
            "as ::core::ffi::c_ulong,",
            "as ::core::ffi::c_ulong as size_t,",
        ).replace("    SIZE_MAX,\n];", "    SIZE_MAX as size_t,\n];")

    if install_checked_arithmetic_support:
        if "pub trait RustboxC2RustCkdInt" in joined:
            raise RuntimeError(f"{path}: checked-arithmetic support already exists")
        joined += CHECKED_ARITHMETIC_SUPPORT
    kept = joined.splitlines()

    definitions: list[str] = []
    for name in opaque:
        definitions.extend(
            [
                "#[repr(C)]",
                f"pub struct {name} {{",
                "    _private: [u8; 0],",
                "}",
            ]
        )
    after = "\n".join([*definitions, *kept]) + "\n"
    if after == before:
        return None
    path.write_text(after, encoding="utf-8")
    result = {
        "path": str(path),
        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "opaque_pointer_types": opaque,
        "raw_static_pointer_rewrites": raw_static_pointer_rewrites,
        "va_list_impl_rewrites": va_list_impl_rewrites,
        "as_va_list_rewrites": as_va_list_rewrites,
        "await_field_rewrites": await_field_rewrites,
        "va_arg_rewrites": va_arg_rewrites,
        "atomic_xchg_acquire_i32_rewrites": atomic_xchg_acquire_rewrites,
        "asm_cast_mutable_borrow_rewrites": asm_cast_mutable_borrow_rewrites,
        "empty_asm_input_rewrites": empty_asm_input_rewrites,
        "integer_to_bool_rewrites": integer_to_bool_rewrites,
        "bool_call_comparison_rewrites": bool_call_comparison_rewrites,
        "write_volatile_semicolon_rewrites": write_volatile_semicolon_rewrites,
        "checked_arithmetic_rewrites": checked_arithmetic_rewrites,
        "size_t_array_literal_rewrites": size_t_array_literal_rewrites,
        "size_t_array_sentinel_rewrites": size_t_array_sentinel_rewrites,
        "checked_arithmetic_support": install_checked_arithmetic_support,
    }
    if external_linkage_attributes:
        result["external_linkage_attributes_removed"] = external_linkage_attributes
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    if not (source / "Cargo.toml").is_file() or source == output:
        raise RuntimeError("input must be a C2Rust crate and output must differ")
    if output.parent != source.parent or not output.name.endswith("-stable") or output.is_symlink():
        raise RuntimeError("output must be a non-symlink *-stable sibling of input")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns("target", "Cargo.lock"),
        )
        rust_sources = sorted(staged.rglob("*.rs"))
        has_checked_arithmetic = any(
            ".overflowing_" in path.read_text(encoding="utf-8")
            for path in rust_sources
        )
        changes: list[dict[str, object]] = []
        for path in rust_sources:
            change = transform_rust(
                path,
                install_checked_arithmetic_support=(
                    has_checked_arithmetic and path == staged / "lib.rs"
                ),
            )
            if change is not None:
                change["path"] = str(path.relative_to(staged))
                changes.append(change)
        duplicate_exports_mangled = [
            *deduplicate_no_mangle_functions(staged),
            *deduplicate_no_mangle_statics(staged),
            *deduplicate_function_static_exports(staged),
        ]
        (staged / "rust-toolchain.toml").write_text(
            '[toolchain]\nchannel = "1.99.0"\nprofile = "minimal"\n', encoding="utf-8"
        )
        if any("#![feature(" in path.read_text(encoding="utf-8") for path in staged.rglob("*.rs")):
            raise RuntimeError("stable output still contains a feature gate")
        manifest = {
            "schema": 1,
            "input_cargo_sha256": digest(source / "Cargo.toml"),
            "stable_toolchain": "1.99.0",
            "changes": changes,
        }
        if duplicate_exports_mangled:
            manifest["duplicate_exports_mangled"] = duplicate_exports_mangled
        (staged / "rustbox-modernization.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
