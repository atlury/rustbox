"""Pack a private, sentinel-terminated Rust C-string table as consecutive terminated byte slices."""
# SPDX-License-Identifier: GPL-3.0-or-later
from ast import literal_eval
from hashlib import sha256
import re

ENTRY = re.compile(rb'\s*c"((?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\[nt\\"])*)"\s*\.as_ptr\(\),')


def replace_table(data, name, capacity):
    header = b"static mut " + name + b": [*const ::core::ffi::c_char; " + str(capacity).encode() + b"] = [\n"
    tail = b"    ::core::ptr::null::<::core::ffi::c_char>(),\n];\n"
    start = data.index(header)
    end = data.index(b"];\n", start) + 3
    table = data[start:end]
    body = table[len(header):].removesuffix(tail)
    spellings = ENTRY.findall(body)
    if (not table.endswith(tail) or data.count(name) != 2 or len(spellings) != capacity - 1
            or ENTRY.sub(b"", body).strip()):
        raise ValueError("expected a private C-string table with one consumer and a final null slot")
    packed = b'static OPTION_HELP: &[u8] = concat!(\n' + b"".join(
        b'    "' + line + b'\\0",\n' for line in spellings) + b').as_bytes();\n'
    lines = [literal_eval('b"' + line.decode("ascii") + '"') for line in spellings]
    payload = b"".join(line + b"\0" for line in lines)
    return data[:start] + packed + data[end:], dict(lines=len(lines), empty_lines=lines.count(b""),
        catalog_bytes=len(payload), catalog_sha256=sha256(payload).hexdigest(), static_pointer_entries_removed=capacity)
