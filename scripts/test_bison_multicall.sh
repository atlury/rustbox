#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    binary=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    oracle=/work/work/analysis/bison-3.8.2/oracle/gcc-root
    source=/work/work/upstream/bison-3.8.2
    evidence=/work/work/analysis/bison-3.8.2/multicall
    aliases=$(mktemp -d /tmp/rustbox-bison-aliases.XXXXXX)
    trap '\''rm -rf "$aliases"'\'' EXIT HUP INT TERM
    mkdir -p "$evidence"
    ln -s "$binary" "$aliases/bison"
    ln -s "$binary" "$aliases/yacc"

    python3 -B /work/tests/bison-oracle-differential.py \
      --gcc "$oracle/usr/bin/bison" \
      --gcc-datadir "$oracle/usr/share/bison" \
      --clang "$aliases/bison" \
      --clang-datadir "$oracle/usr/share/bison" \
      --right-embedded --source "$source" \
      --output "$evidence/differential.json"
    python3 -B /work/tests/bison-yacc-frontend.py \
      --canonical "$oracle/usr/bin/yacc" \
      --canonical-datadir "$oracle/usr/share/bison" \
      --hybrid "$aliases/yacc" \
      --hybrid-datadir "$oracle/usr/share/bison" \
      --hybrid-embedded --output "$evidence/yacc-frontend.json"

    datadir=$(env -u BISON_PKGDATADIR -u M4 \
      "$aliases/bison" --print-datadir)
    test -d "$datadir/skeletons"
    test -d "$datadir/m4sugar"
    test -d "$datadir/xslt"
    for resource in \
      bison-default.css m4sugar/foreach.m4 m4sugar/m4sugar.m4 \
      skeletons/yacc.c skeletons/lalr1.cc \
      xslt/bison.xsl xslt/xml2dot.xsl xslt/xml2text.xsl xslt/xml2xhtml.xsl
    do
      cmp "$oracle/usr/share/bison/$resource" "$datadir/$resource"
    done
    printf "%s\n" "$datadir" >"$evidence/print-datadir.txt"

    stripped="$aliases/rustbox.stripped"
    cp "$binary" "$stripped"
    strip --strip-all "$stripped"
    stripped_bytes=$(stat -c %s "$stripped")
    stripped_sha256=$(sha256sum "$stripped" | awk '\''{ print $1 }'\'')
    printf '\''{"bytes": %s, "sha256": "%s"}\n'\'' \
      "$stripped_bytes" "$stripped_sha256" >"$evidence/size.json"

    env -u BISON_PKGDATADIR -u M4 \
      valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-help.log" \
      "$aliases/bison" --help >/dev/null
    grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-help.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
  '
