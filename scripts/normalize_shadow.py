#!/usr/bin/env python3
"""Create deterministic multicall-entrypoint normalization for Shadow."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SIGNATURES = {
    "chage": ("int main (int argc, char **argv)",),
    "chfn": ("int main (int argc, char **argv)",),
    "chgpasswd": ("int main (int argc, char **argv)",),
    "chpasswd": ("int main (int argc, char **argv)",),
    "chsh": ("int main (int argc, char **argv)",),
    "faillog": ("int main (int argc, char **argv)",),
    "getsubids": ("int main(int argc, char *argv[])",),
    "gpasswd": ("int main (int argc, char **argv)",),
    "groupadd": ("int main (int argc, char **argv)",),
    "groupdel": ("int main (int argc, char **argv)",),
    "groupmod": ("int main (int argc, char **argv)",),
    "grpck": ("int main (int argc, char **argv)",),
    "grpconv": (
        "int main (int argc, char **argv)",
        "int\nmain(MAYBE_UNUSED int _1, char **argv)",
    ),
    "grpunconv": (
        "int main (int argc, char **argv)",
        "int\nmain(MAYBE_UNUSED int _1, char **argv)",
    ),
    "lastlog": ("int main (int argc, char **argv)",),
    "login": ("int main (int argc, char **argv)",),
    "newgidmap": ("int main(int argc, char **argv)",),
    "newgrp": ("int main (int argc, char **argv)",),
    "newuidmap": ("int main(int argc, char **argv)",),
    "newusers": ("int main (int argc, char **argv)",),
    "nologin": ("int main (void)",),
    "passwd": ("int\nmain(int argc, char **argv)",),
    "pwck": ("int main (int argc, char **argv)",),
    "pwconv": ("int main (int argc, char **argv)",),
    "pwunconv": ("int main (int argc, char **argv)",),
    "su": ("int main (int argc, char **argv)",),
    "useradd": ("int main (int argc, char **argv)",),
    "userdel": ("int main (int argc, char **argv)",),
    "usermod": ("int main (int argc, char **argv)",),
    "vipw": ("int main (int argc, char **argv)",),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_fragments(
    root: Path,
    relative: str,
    replacements: tuple[tuple[str, str], ...],
    kind: str,
) -> dict[str, object]:
    source = root / relative
    text = source.read_text()
    before = sha256(source)
    for original, replacement in replacements:
        if text.count(original) != 1:
            raise RuntimeError(f"Shadow normalization input changed: {relative}: {original!r}")
        text = text.replace(original, replacement, 1)
    source.write_text(text)
    return {
        "path": relative,
        "before_sha256": before,
        "after_sha256": sha256(source),
        "kind": kind,
        "fragment_replacements": len(replacements),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/shadow-4.20.4"
    state = json.loads((root / "work/upstream/.state/shadow.json").read_text())
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["shadow"]
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("canonical Shadow source is not signature-verified")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(canonical, output, symlinks=True)

    transformations = []
    for program, signatures in SIGNATURES.items():
        source = output / f"src/{program}.c"
        text = source.read_text()
        exported = f"rustbox_shadow_{program}_main"
        before = sha256(source)
        definitions = 0
        for signature in signatures:
            if text.count(signature) != 1:
                raise RuntimeError(f"Shadow entrypoint signature changed: {program}: {signature!r}")
            if program == "nologin":
                replacement = f"int {exported} (int argc, char **argv)"
            else:
                replacement = signature.replace("main", exported, 1)
            text = text.replace(signature, replacement, 1)
            definitions += 1
        if exported in source.read_text():
            raise RuntimeError(f"Shadow exported entrypoint already exists: {program}")
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            "int main(int argc, char **argv)\n"
            "{\n"
            f"\treturn {exported}(argc, argv);\n"
            "}\n"
            "#endif\n"
        )
        source.write_text(text + wrapper)
        transformations.append({
            "path": f"src/{program}.c",
            "entrypoint": exported,
            "conditional_definitions": definitions,
            "before_sha256": before,
            "after_sha256": sha256(source),
            "kind": "export entrypoint and retain standalone wrapper",
        })

    transformations.extend((
        replace_fragments(output, "lib/alloc/realloc.h", ((
            "\t_Generic(p, T *: (void)0);                                    \\\n",
            "",
        ),), "remove translation-only generic pointer type assertion"),
        replace_fragments(output, "lib/alloc/reallocf.h", ((
            "\t_Generic(p, T *: (void)0);                                    \\\n",
            "",
        ),), "remove translation-only generic pointer type assertion"),
        replace_fragments(output, "lib/search/l/lsearch.h", ((
            "\t_Generic(k, T *: (void)0, const T *: (void)0);                \\\n"
            "\t_Generic(a, T *: (void)0);                                    \\\n",
            "",
        ),), "remove translation-only generic search type assertions"),
        replace_fragments(output, "lib/search/l/lfind.h", ((
            "\t_Generic(k, T *: (void)0, const T *: (void)0);                \\\n"
            "\t_Generic(a, T *: (void)0, const T *: (void)0);                \\\n",
            "",
        ),), "remove translation-only generic search type assertions"),
        replace_fragments(output, "lib/search/sort/qsort.h", ((
            "\t_Generic(a, T *: (void)0);                                    \\\n",
            "",
        ),), "remove translation-only generic sort type assertion"),
        replace_fragments(output, "lib/cast.h", ((
            "#define const_cast(T, p)  _Generic(p, const T:  (T) (p))",
            "#define const_cast(T, p)  ((T) (p))",
        ),), "lower generic checked const cast to its selected C cast"),
        replace_fragments(output, "lib/string/strcmp/strprefix.h", ((
            "#define strprefix(s, prefix)                                          \\\n"
            "({                                                                    \\\n"
            "\tconst char  *p_;                                              \\\n"
            "\t                                                              \\\n"
            "\tp_ = strprefix_(s, prefix);                                   \\\n"
            "\t                                                              \\\n"
            "\t_Generic(s,                                                   \\\n"
            "\t\tconst char *:                     p_,                 \\\n"
            "\t\tconst void *:                     p_,                 \\\n"
            "\t\tchar *:        const_cast(char *, p_),                \\\n"
            "\t\tvoid *:        const_cast(char *, p_)                 \\\n"
            "\t);                                                            \\\n"
            "})",
            "#define strprefix(s, prefix)  strprefix_((s), (prefix))",
        ),), "lower generic prefix return qualification to selected pointer cast"),
        replace_fragments(output, "lib/string/strcmp/strcaseprefix.h", ((
            "#define strcaseprefix(s, prefix)                                      \\\n"
            "({                                                                    \\\n"
            "\tconst char  *p_;                                              \\\n"
            "\t                                                              \\\n"
            "\tp_ = strcaseprefix_(s, prefix);                               \\\n"
            "\t                                                              \\\n"
            "\t_Generic(s,                                                   \\\n"
            "\t\tconst char *:                     p_,                 \\\n"
            "\t\tconst void *:                     p_,                 \\\n"
            "\t\tchar *:        const_cast(char *, p_),                \\\n"
            "\t\tvoid *:        const_cast(char *, p_)                 \\\n"
            "\t);                                                            \\\n"
            "})",
            "#define strcaseprefix(s, prefix)  strcaseprefix_((s), (prefix))",
        ),), "lower generic case-prefix return qualification to selected pointer cast"),
        replace_fragments(output, "lib/string/strspn/stpspn.h", ((
            "#define stpspn(s, accept)                                                     \\\n"
            "({                                                                            \\\n"
            "\t__auto_type  s_ = s;                                                  \\\n"
            "\t                                                                      \\\n"
            "\ts_ + strspn(s_, accept);                                              \\\n"
            "})",
            "static inline void *\n"
            "rustbox_stpspn(const char *s, const char *accept)\n"
            "{\n"
            "\treturn (void *) (s + strspn(s, accept));\n"
            "}\n\n"
            "#define stpspn(s, accept)  rustbox_stpspn((s), (accept))",
        ),), "lower auto-typed forward span macro to a concrete inline function"),
        replace_fragments(output, "lib/string/strspn/stprcspn.h", ((
            "#define stprcspn(s, reject)                                           \\\n"
            "({                                                                    \\\n"
            "\t__auto_type  s_ = (s);                                        \\\n"
            "\t                                                              \\\n"
            "\tstrnul(s_) - strrcspn(s_, reject);                            \\\n"
            "})",
            "static inline void *\n"
            "rustbox_stprcspn(const char *s, const char *reject)\n"
            "{\n"
            "\treturn (void *) (strnul(s) - strrcspn(s, reject));\n"
            "}\n\n"
            "#define stprcspn(s, reject)  rustbox_stprcspn((s), (reject))",
        ),), "lower auto-typed rear complement span macro to a concrete inline function"),
        replace_fragments(output, "lib/string/strspn/stprspn.h", ((
            "#define stprspn(s, accept)                                            \\\n"
            "({                                                                    \\\n"
            "\t__auto_type  s_ = (s);                                        \\\n"
            "\t                                                              \\\n"
            "\tstrnul(s_) - strrspn_(s_, accept);                            \\\n"
            "})",
            "static inline void *\n"
            "rustbox_stprspn(const char *s, const char *accept)\n"
            "{\n"
            "\treturn (void *) (strnul(s) - strrspn_(s, accept));\n"
            "}\n\n"
            "#define stprspn(s, accept)  rustbox_stprspn((s), (accept))",
        ),), "lower auto-typed rear span macro to a concrete inline function"),
        replace_fragments(output, "lib/exit_if_null.h", (
            (
                "#define exit_if_null(p)                                               \\\n"
                "({                                                                    \\\n"
                "\t__auto_type  p_ = p;                                          \\\n"
                "\t                                                              \\\n"
                "\texit_if_null_(p_);                                            \\\n"
                "\tp_;                                                           \\\n"
                "})",
                "#define exit_if_null(p)  exit_if_null_(p)",
            ),
            ("inline void exit_if_null_(void *p);", "inline void *exit_if_null_(void *p);"),
            ("inline void\nexit_if_null_(void *p)", "inline void *\nexit_if_null_(void *p)"),
            ("\t}\n}\n\n\n#endif  // include guard", "\t}\n\treturn p;\n}\n\n\n#endif  // include guard"),
        ), "lower auto-typed null-check macro to a concrete pointer-returning inline function"),
        replace_fragments(output, "lib/exit_if_null.c", ((
            "extern inline void exit_if_null_(void *p);",
            "extern inline void *exit_if_null_(void *p);",
        ),), "match the concrete null-check inline function declaration"),
    ))

    a2i_original = """// a2i - alpha to integer
#define a2i(T, n, s, endp, base, min, max)                            \\
({                                                                    \\
\tT            *n_ = n;                                         \\
\tQChar_of(s)  **endp_ = endp;                                  \\
\tT            min_ = min;                                      \\
\tT            max_ = max;                                      \\
\t                                                              \\
\tint  status;                                                  \\
\t                                                              \\
\t*n_ = _Generic((T){0},                                        \\
\t\tshort:              strtoi_,                          \\
\t\tint:                strtoi_,                          \\
\t\tlong:               strtoi_,                          \\
\t\tlong long:          strtoi_,                          \\
\t\tunsigned short:     strtou_noneg,                     \\
\t\tunsigned int:       strtou_noneg,                     \\
\t\tunsigned long:      strtou_noneg,                     \\
\t\tunsigned long long: strtou_noneg                      \\
\t)(s, (char **) endp_, base, min_, max_, &status);             \\
\t                                                              \\
\tif (status != 0)                                              \\
\t\terrno = status;                                       \\
\t-!!status;                                                    \\
})


#define a2sh(...)   a2i(short, __VA_ARGS__)
#define a2si(...)   a2i(int, __VA_ARGS__)
#define a2sl(...)   a2i(long, __VA_ARGS__)
#define a2sll(...)  a2i(long long, __VA_ARGS__)

#define a2uh(...)   a2i(unsigned short, __VA_ARGS__)
#define a2ui(...)   a2i(unsigned int, __VA_ARGS__)
#define a2ul(...)   a2i(unsigned long, __VA_ARGS__)
#define a2ull(...)  a2i(unsigned long long, __VA_ARGS__)

#define str2i(T, ...)  a2i(T, __VA_ARGS__, NULL, 0, minof(T), maxof(T))

#define str2sh(...)    str2i(short, __VA_ARGS__)
#define str2si(...)    str2i(int, __VA_ARGS__)
#define str2sl(...)    str2i(long, __VA_ARGS__)
#define str2sll(...)   str2i(long long, __VA_ARGS__)

#define str2uh(...)    str2i(unsigned short, __VA_ARGS__)
#define str2ui(...)    str2i(unsigned int, __VA_ARGS__)
#define str2ul(...)    str2i(unsigned long, __VA_ARGS__)
#define str2ull(...)   str2i(unsigned long long, __VA_ARGS__)
"""
    a2i_portable = """// a2i - alpha to integer
#define a2i_parser(T, parser, n, s, endp, base, min, max)             \\
({                                                                    \\
\tT      *n_ = n;                                                \\
\tchar  **endp_ = (char **) endp;                               \\
\tT       min_ = min;                                           \\
\tT       max_ = max;                                           \\
\t                                                              \\
\tint  status;                                                  \\
\t                                                              \\
\t*n_ = parser(s, endp_, base, min_, max_, &status);             \\
\t                                                              \\
\tif (status != 0)                                              \\
\t\terrno = status;                                       \\
\t-!!status;                                                    \\
})


#define a2sh(...)   a2i_parser(short, strtoi_, __VA_ARGS__)
#define a2si(...)   a2i_parser(int, strtoi_, __VA_ARGS__)
#define a2sl(...)   a2i_parser(long, strtoi_, __VA_ARGS__)
#define a2sll(...)  a2i_parser(long long, strtoi_, __VA_ARGS__)

#define a2uh(...)   a2i_parser(unsigned short, strtou_noneg, __VA_ARGS__)
#define a2ui(...)   a2i_parser(unsigned int, strtou_noneg, __VA_ARGS__)
#define a2ul(...)   a2i_parser(unsigned long, strtou_noneg, __VA_ARGS__)
#define a2ull(...)  a2i_parser(unsigned long long, strtou_noneg, __VA_ARGS__)

#define str2i_signed(T, ...) \\
\ta2i_parser(T, strtoi_, __VA_ARGS__, NULL, 0, minof(T), maxof(T))
#define str2i_unsigned(T, ...) \\
\ta2i_parser(T, strtou_noneg, __VA_ARGS__, NULL, 0, minof(T), maxof(T))

#define str2sh(...)    str2i_signed(short, __VA_ARGS__)
#define str2si(...)    str2i_signed(int, __VA_ARGS__)
#define str2sl(...)    str2i_signed(long, __VA_ARGS__)
#define str2sll(...)   str2i_signed(long long, __VA_ARGS__)

#define str2uh(...)    str2i_unsigned(unsigned short, __VA_ARGS__)
#define str2ui(...)    str2i_unsigned(unsigned int, __VA_ARGS__)
#define str2ul(...)    str2i_unsigned(unsigned long, __VA_ARGS__)
#define str2ull(...)   str2i_unsigned(unsigned long long, __VA_ARGS__)
"""
    transformations.append(replace_fragments(
        output, "lib/atoi/a2i.h", ((a2i_original, a2i_portable),),
        "lower generic integer parser selection to explicit signed and unsigned parsers",
    ))

    direct_parser_replacements = {
        "lib/gettime.c": (("a2i(time_t,", "a2i_parser(time_t, strtoi_,"),),
        "src/usermod.c": (
            ("a2i(id_t, &first,", "a2i_parser(id_t, strtou_noneg, &first,"),
            ("a2i(id_t, &last,", "a2i_parser(id_t, strtou_noneg, &last,"),
        ),
        "lib/limits.c": (
            ("a2i(rlim_t,", "a2i_parser(rlim_t, strtou_noneg,"),
            ("str2i(mode_t, &mask, value)", "str2i_unsigned(mode_t, &mask, value)"),
            ("str2i(mode_t, &mask, val)", "str2i_unsigned(mode_t, &mask, val)"),
        ),
        "lib/atoi/getnum.h": (
            ("a2i(gid_t,", "a2i_parser(gid_t, strtou_noneg,"),
            ("a2i(pid_t,", "a2i_parser(pid_t, strtoi_,"),
            ("a2i(uid_t,", "a2i_parser(uid_t, strtou_noneg,"),
        ),
    }
    for relative, replacements in direct_parser_replacements.items():
        transformations.append(replace_fragments(
            output, relative, replacements,
            "make target ABI integer parser selection explicit",
        ))

    search_replacements = {
        "lib/addgrps.c": (
            ("LSEARCH(gid_t, &grp->gr_gid, gids, &n);",
             "(void) lsearch(&grp->gr_gid, gids, &n, sizeof(gid_t), cmp_uint);"),
        ),
        "lib/adds.h": (
            ("QSORT(long, addend, n);", "qsort(addend, n, sizeof(long), cmp_long);"),
        ),
        "src/newgrp.c": (
            ("LFIND(gid_t, &grp->gr_gid, gids, ngroups)",
             "lfind(&grp->gr_gid, gids, &ngroups, sizeof(gid_t), cmp_uint)"),
            ("LSEARCH(gid_t, &gid, gids, &ngroups);",
             "(void) lsearch(&gid, gids, &ngroups, sizeof(gid_t), cmp_uint);"),
        ),
    }
    for relative, replacements in search_replacements.items():
        transformations.append(replace_fragments(
            output, relative, replacements,
            "lower generic search or sort selection to target ABI comparator",
        ))

    mutable_prefix_replacements = {
        "lib/user_busy.c": ((
            "tmp_d_name = strprefix(tmp_d_name, \".\") ?: tmp_d_name;",
            "tmp_d_name = (char *) strprefix(tmp_d_name, \".\") ?: tmp_d_name;",
        ),),
        "lib/limits.c": (
            ("cp = strprefix(cp, \",\") ?: cp;", "cp = (char *) strprefix(cp, \",\") ?: cp;"),
            ("val = strprefix(cp, \"pri=\");", "val = (char *) strprefix(cp, \"pri=\");"),
            ("val = strprefix(cp, \"ulimit=\");", "val = (char *) strprefix(cp, \"ulimit=\");"),
            ("val = strprefix(cp, \"umask=\");", "val = (char *) strprefix(cp, \"umask=\");"),
        ),
    }
    for relative, replacements in mutable_prefix_replacements.items():
        transformations.append(replace_fragments(
            output, relative, replacements,
            "make intentional mutable prefix pointer casts explicit",
        ))

    manifest = {
        "schema": 1,
        "release": "4.20.4",
        "canonical_sha256": release["sha256"],
        "entrypoint_engines": len(SIGNATURES),
        "public_programs": 32,
        "aliases": {"sg": "newgrp", "vigr": "vipw"},
        "changed_files": len({record["path"] for record in transformations}),
        "transformations": transformations,
    }
    manifest_path = output / "rustbox-normalization.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "entrypoints": len(SIGNATURES),
        "programs": 32,
        "transformations": len(transformations),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
