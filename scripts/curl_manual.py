"""Replace curl's private manual pointer array with one immutable byte buffer."""
# SPDX-License-Identifier: curl
from hashlib import sha256
from pathlib import Path
import re

from check_cargo_private_inlines import ROOT
from prune_private_inlines import POINTER

MODULE = Path("src/src/tool_hugehelp.rs")
CONTROL_SHA = "95fe5376476cf0f4904ae8ad99a25dcd4bee3b5c023aded403007148030e301b"
# curl's generated manual uses ASCII and exactly these escapes before its NUL.
# Matching the full initializer rejects missing entries and embedded NUL bytes.
LINE = re.compile(rb'\s*b"((?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\["\\nt])*)\\0"\s+as\s+\*const u8\s+as\s+\*const ::core::ffi::c_char,')


def replace_manual(control):
    if sha256(control).hexdigest() != CONTROL_SHA:
        raise ValueError("unexpected compiler-selected curl manual source")
    opening = b"static mut curlman: [*const ::core::ffi::c_char; 5705] = ["
    start = control.index(opening)
    position = start + len(opening)
    lines = []
    while line := LINE.match(control, position):
        lines.append(line[1])
        position = line.end()
    if len(lines) != 5704 or not control.startswith(b"\n    ::core::ptr::null::<::core::ffi::c_char>(),\n];", position):
        raise ValueError("expected all 5,704 manual lines followed by one null pointer")
    upstream = (ROOT / "work/upstream/curl-8.23.0/src/tool_hugehelp.c").read_bytes()
    if sha256(upstream).hexdigest() != "1d5b521607a902351b40a45166e9b49b0b32b96ccfb2afb7c52c9168011e6ac1":
        raise ValueError("canonical curl manual source changed")
    # Both languages assign the same bytes to the limited escapes accepted above.
    original = b"static const char * const curlman[] = {\n" + b"".join(b'  "' + item + b'",\n' for item in lines) + b"  NULL\n};"
    if upstream.count(original) != 1:
        raise ValueError("manual records differ from the canonical C table")
    literals = b"".join(b'    "' + item + b'\\0",\n' for item in lines)
    replacement = (ROOT / "compat/curl/manual.rs").read_bytes()
    candidate = control[:start] + b"static CURL_MANUAL: &[u8] = concat!(\n" + literals + b").as_bytes();\n\n" + replacement
    return candidate, {"control_module_sha256": CONTROL_SHA, "candidate_module_sha256": sha256(candidate).hexdigest(),
                       "raw_pointer_types_removed_in_pilot_module": len(POINTER.findall(control)) - len(POINTER.findall(candidate))}
