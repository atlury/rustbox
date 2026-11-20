#!/usr/bin/env python3
"""Stage GNU patch with deterministic multicall entrypoint normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def replace_exact(path: Path, replacements: list[tuple]) -> None:
    text = path.read_text()
    for replacement in replacements:
        before, after = replacement[:2]
        expected = replacement[2] if len(replacement) == 3 else 1
        if text.count(before) != expected:
            raise RuntimeError(
                f"normalization precondition failed in {path}: "
                f"expected {expected} occurrences of {before!r}"
            )
        text = text.replace(before, after)
    path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/patch-2.8"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["patch"]
    state = json.loads((repository / "work/upstream/.state/patch.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"GNU patch source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("canonical GNU patch release signature is not verified")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        target = staged / "src/patch.c"
        before = target.read_text()
        signature = "int\nmain (int argc, char **argv)\n{"
        replacement = (
            "int rustbox_patch_main (int argc, char **argv);\n\n"
            "int\n"
            "rustbox_patch_main (int argc, char **argv)\n{"
        )
        if before.count(signature) != 1 or "rustbox_patch_main" in before:
            raise RuntimeError("GNU patch entrypoint normalization precondition failed")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int\n"
            "main (int argc, char **argv)\n"
            "{\n"
            "  return rustbox_patch_main (argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        target.write_text(before.replace(signature, replacement) + wrapper)
        if target.read_text().count("rustbox_patch_main") != 3:
            raise RuntimeError("GNU patch entrypoint normalization postcondition failed")

        parser_source = staged / "lib/parse-datetime.c"
        parser_before = parser_source.read_text()
        line_directive = re.compile(r'^#line \d+ "parse-datetime\.(?:c|y)"\n', re.MULTILINE)
        if len(line_directive.findall(parser_before)) != 158:
            raise RuntimeError("GNU patch generated-parser line-directive precondition failed")
        diagnostic = 'dbg_printf (_("error: %s:%d\\n"), __FILE__, __LINE__);'
        preserved = 'dbg_printf (_("error: %s:%d\\n"), "parse-datetime.y", 2158);'
        if parser_before.count(diagnostic) != 1:
            raise RuntimeError("GNU patch generated-parser diagnostic precondition failed")
        parser_after = line_directive.sub("", parser_before.replace(diagnostic, preserved))
        if "#line " in parser_after or "__FILE__" in parser_after or "__LINE__" in parser_after:
            raise RuntimeError("GNU patch generated-parser source remap remains")
        parser_source.write_text(parser_after)

        replace_exact(staged / "lib/backupfile.c", [
            ("        all_9s &= (p[versionlen] == '9');",
             "        all_9s = (p[versionlen] == '9') && all_9s;"),
        ])
        replace_exact(staged / "lib/malloca.c", [
            ("  idx_t nplus;\n  if (!ckd_add (&nplus, n, plus) && !xalloc_oversized (nplus, 1))",
             "  idx_t nplus;\n  if (n <= (size_t) (IDX_MAX - plus)\n      && (nplus = (idx_t) n + plus, !xalloc_oversized (nplus, 1)))"),
        ])
        replace_exact(staged / "lib/mktime.c", [
            ("  ckd_sub (&negative_offset_guess, 0, off);",
             "  ckd_sub (&negative_offset_guess, (int) 0, (int) off);"),
            ("    if (! ckd_add (&ot, t, delta * direction))",
             "    if (! ckd_add (&ot, t, (long_int) (delta * direction)))"),
            ("  ckd_sub (offset, *offset, negative_offset_guess);",
             "  ckd_sub (offset, *offset, (mktime_offset_t) negative_offset_guess);"),
        ])

        parser_helpers_anchor = "static bool\ndebugging (parser_control const *pc)\n"
        parser_helpers = (
            "static bool\n"
            "ckd_int_add_intmax (int *result, intmax_t left, intmax_t right)\n"
            "{\n"
            "  intmax_t value;\n"
            "  if (ckd_add (&value, left, right) || value < INT_MIN || INT_MAX < value)\n"
            "    return true;\n"
            "  *result = (int) value;\n"
            "  return false;\n"
            "}\n\n"
            "static bool\n"
            "ckd_int_sub_intmax (int *result, intmax_t left, intmax_t right)\n"
            "{\n"
            "  intmax_t value;\n"
            "  if (ckd_sub (&value, left, right) || value < INT_MIN || INT_MAX < value)\n"
            "    return true;\n"
            "  *result = (int) value;\n"
            "  return false;\n"
            "}\n\n"
        )
        replace_exact(parser_source, [
            (parser_helpers_anchor, parser_helpers + parser_helpers_anchor),
            ("ckd_add (&pc->time_zone, pc->time_zone, (yyvsp[-2].intval))",
             "ckd_int_add_intmax (&pc->time_zone, pc->time_zone, (yyvsp[-2].intval))"),
            ("ckd_sub (&pc->year.value, 0, (yyvsp[0].textintval).value)",
             "ckd_sub (&pc->year.value, (intmax_t) 0, (yyvsp[0].textintval).value)", 2),
            ("ckd_sub (&pc->day, 0, (yyvsp[-1].textintval).value)",
             "ckd_sub (&pc->day, (intmax_t) 0, (yyvsp[-1].textintval).value)"),
            ("ckd_sub (&pc->month, 0, (yyvsp[-1].textintval).value)",
             "ckd_sub (&pc->month, (intmax_t) 0, (yyvsp[-1].textintval).value)"),
            ("ckd_sub (&pc->day, 0, (yyvsp[0].textintval).value)",
             "ckd_sub (&pc->day, (intmax_t) 0, (yyvsp[0].textintval).value)"),
            ("overflow |= ckd_mul (&n_minutes, s.value, 60);",
             "overflow = ckd_mul (&n_minutes, s.value, (intmax_t) 60) || overflow;"),
            ("overflow |= (s.negative\n                   ? ckd_sub (&n_minutes, n_minutes, mm)\n                   : ckd_add (&n_minutes, n_minutes, mm));",
             "overflow = (s.negative\n              ? ckd_sub (&n_minutes, n_minutes, mm)\n              : ckd_add (&n_minutes, n_minutes, mm)) || overflow;"),
            ("? ckd_sub (tm_year, -TM_YEAR_BASE, year)\n      : ckd_sub (tm_year, year, TM_YEAR_BASE)",
             "? ckd_int_sub_intmax (tm_year, -TM_YEAR_BASE, year)\n      : ckd_int_sub_intmax (tm_year, year, TM_YEAR_BASE)"),
            ("ckd_mul (&value, value, 10)",
             "ckd_mul (&value, value, (intmax_t) 10)"),
            ("ckd_add (&value, value, sign < 0 ? '0' - c : c - '0')",
             "ckd_add (&value, value, (intmax_t) (sign < 0 ? '0' - c : c - '0'))"),
            ("ckd_sub (&s, s, 1)", "ckd_sub (&s, s, (intmax_t) 1)"),
            ("ckd_add (&pc.year.value, tmp.tm_year, TM_YEAR_BASE)",
             "ckd_add (&pc.year.value, (intmax_t) tmp.tm_year, (intmax_t) TM_YEAR_BASE)"),
            ("ckd_add (&probe, Start, quarter * (90 * 24 * 60 * 60))",
             "ckd_add (&probe, Start, (time_t) quarter * (90 * 24 * 60 * 60))"),
            ("ckd_add (&tm.tm_mon, pc.month, -1)",
             "ckd_int_add_intmax (&tm.tm_mon, pc.month, -1)"),
            ("ckd_add (&tm.tm_mday, pc.day, 0)",
             "ckd_int_add_intmax (&tm.tm_mday, pc.day, 0)"),
            ("ckd_mul (&dayincr, day_ordinal, 7)",
             "ckd_mul (&dayincr, day_ordinal, (intmax_t) 7)"),
            ("ckd_add (&dayincr, (pc.day_number - tm.tm_wday + 7) % 7,\n                             dayincr)",
             "ckd_add (&dayincr,\n                             (intmax_t) ((pc.day_number - tm.tm_wday + 7) % 7),\n                             dayincr)"),
            ("ckd_add (&tm.tm_mday, dayincr, tm.tm_mday)",
             "ckd_int_add_intmax (&tm.tm_mday, dayincr, tm.tm_mday)"),
            ("ckd_add (&year, tm.tm_year, pc.rel.year)",
             "ckd_int_add_intmax (&year, tm.tm_year, pc.rel.year)"),
            ("ckd_add (&month, tm.tm_mon, pc.rel.month)",
             "ckd_int_add_intmax (&month, tm.tm_mon, pc.rel.month)"),
            ("ckd_add (&day, tm.tm_mday, pc.rel.day)",
             "ckd_int_add_intmax (&day, tm.tm_mday, pc.rel.day)"),
            ("overflow |= ckd_sub (&delta, pc.time_zone, utcoff);",
             "overflow = ckd_sub (&delta, (intmax_t) pc.time_zone,\n                              (intmax_t) utcoff) || overflow;"),
            ("overflow |= ckd_sub (&t1, Start, delta);",
             "overflow = ckd_sub (&t1, Start, (time_t) delta) || overflow;"),
            ("ckd_mul (&d1, pc.rel.hour, 60 * 60)",
             "ckd_mul (&d1, pc.rel.hour, (intmax_t) (60 * 60))"),
            ("ckd_mul (&d2, pc.rel.minutes, 60)",
             "ckd_mul (&d2, pc.rel.minutes, (intmax_t) 60)"),
            ("ckd_add (&t4, t3, d4)",
             "ckd_add (&t4, (time_t) t3, (time_t) d4)"),
        ])

        replace_exact(staged / "src/inp.c", [
            ("  idx_t size;\n  if (ckd_add (&size, instat.st_size, 0))\n    xalloc_die ();",
             "  if (instat.st_size < 0 || IDX_MAX < instat.st_size)\n    xalloc_die ();\n  idx_t size = (idx_t) instat.st_size;"),
        ])
        replace_exact(staged / "src/merge.c", [
            ("ckd_add (&diags, diags, 3)", "ckd_add (&diags, diags, (idx_t) 3)"),
        ])
        replace_exact(target, [
            ("\tsomefailed |= skip_rest_of_patch;",
             "\tsomefailed = skip_rest_of_patch || somefailed;"),
            ("overflow |= ckd_mul (&value, value, 10);",
             "overflow = ckd_mul (&value, value, (intmax_t) 10) || overflow;"),
            ("overflow |= ckd_add (&value, value, negative ? '0' - *p : *p - '0');",
             "overflow = ckd_add (&value, value,\n                              (intmax_t) (negative ? '0' - *p : *p - '0'))\n                 || overflow;"),
        ])
        replace_exact(staged / "src/pch.c", [
            ("    reverse_flag ^=\n      ok_to_reverse (",
             "    reverse_flag = reverse_flag !=\n      ok_to_reverse ("),
            ("overflow |= ckd_mul (&n, n, 10);",
             "overflow = ckd_mul (&n, n, (idx_t) 10) || overflow;"),
            ("overflow |= ckd_add (&n, n, *s - '0');",
             "overflow = ckd_add (&n, n, (idx_t) (*s - '0')) || overflow;"),
            ("int s0len = ckd_add (&s0len, s - s0, 0) ? -1 : s0len;",
             "int s0len = INT_MAX < s - s0 ? -1 : (int) (s - s0);"),
            ("ptrn_spaces_eaten |= (repl_beginning != 0);",
             "ptrn_spaces_eaten = (repl_beginning != 0) || ptrn_spaces_eaten;"),
            ("got_invalid_byte |= c == invalid_byte;",
             "got_invalid_byte = (c == invalid_byte) || got_invalid_byte;", 3),
        ])
        replace_exact(staged / "src/safe.c", [
            ("  idx_t symlinksize;\n  if (ckd_add (&symlinksize, st.st_size, 1 + sizeof *symlink))\n    xalloc_die ();",
             "  idx_t symlink_extra = (idx_t) (1 + sizeof *symlink);\n  if (st.st_size < 0 || IDX_MAX - symlink_extra < st.st_size)\n    xalloc_die ();\n  idx_t symlinksize = (idx_t) st.st_size + symlink_extra;"),
            ("int pathlen = ckd_sub (&pathlen, full_pathlen, 0) ? -1 : pathlen;",
             "int pathlen = INT_MAX < full_pathlen ? -1 : (int) full_pathlen;"),
        ])
        replace_exact(staged / "src/util.c", [
            ("\t  idx_t alloc;\n\t  if (ckd_add (&alloc, fromst->st_size, 1))\n\t    xalloc_die ();",
             "\t  if (fromst->st_size < 0 || IDX_MAX - 1 < fromst->st_size)\n\t    xalloc_die ();\n\t  idx_t alloc = (idx_t) fromst->st_size + 1;"),
            ("      idx_t alloc;\n      if (ckd_add (&alloc, fromst->st_size, 1))\n\txalloc_die ();",
             "      if (fromst->st_size < 0 || IDX_MAX - 1 < fromst->st_size)\n\txalloc_die ();\n      idx_t alloc = (idx_t) fromst->st_size + 1;"),
        ])

        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization added or removed GNU patch source-tree files")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        expected_changed = [
            "lib/backupfile.c", "lib/malloca.c", "lib/mktime.c",
            "lib/parse-datetime.c", "src/inp.c", "src/merge.c", "src/patch.c",
            "src/pch.c", "src/safe.c", "src/util.c",
        ]
        if changed != expected_changed:
            raise RuntimeError(f"unexpected GNU patch normalized sources: {changed}")

        transformations = [
            {
                "source": "lib/parse-datetime.c",
                "canonical_sha256": sha256(canonical / "lib/parse-datetime.c"),
                "normalized_sha256": sha256(parser_source),
                "operation": "materialize the sole __FILE__/__LINE__ expansion, remove 158 generated diagnostic line remaps that reverse Clang source offsets, and make checked-integer destination widths and eager Boolean accumulation explicit",
                "engine": "exact deterministic generated-source rewrite",
            },
            {
                "source": "src/patch.c",
                "canonical_sha256": sha256(canonical / "src/patch.c"),
                "normalized_sha256": sha256(target),
                "operation": "export rustbox_patch_main with a conditional standalone main wrapper and make checked-integer widths and eager Boolean accumulation explicit",
                "engine": "exact deterministic source rewrite",
            },
        ]
        recorded = {item["source"] for item in transformations}
        for name in changed:
            if name not in recorded:
                transformations.append({
                    "source": name,
                    "canonical_sha256": sha256(canonical / name),
                    "normalized_sha256": sha256(staged / name),
                    "operation": "make checked-integer operands and Boolean accumulation explicit for C2Rust while preserving configured x86_64 semantics",
                    "engine": "exact deterministic translator-compatibility rewrite",
                })
        for item in transformations:
            item["normalized_sha256"] = sha256(staged / item["source"])
        manifest = {
            "schema": 1,
            "release": release["version"],
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "transformations": transformations,
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": 10, "entrypoints": 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
