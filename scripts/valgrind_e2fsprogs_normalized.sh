#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    stage=/rustbox-e2fsprogs/stage-normalized-gcc
    evidence=/work/work/analysis/e2fsprogs-1.47.4/normalization
    inventory=$evidence/gcc-installed-executables.txt
    export LC_ALL=C
    export PATH="$stage/sbin:$stage/usr/sbin:$stage/usr/bin:$stage/usr/lib:/usr/sbin:/usr/bin:/sbin:/bin"
    while IFS= read -r relative; do
      test -n "$relative" || continue
      name=$(printf "%s" "$relative" | tr / _)
      path=$stage/$relative
      if file "$path" | grep -q ELF; then
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible \
          --log-file="$evidence/valgrind-$name.log" \
          "$path" --help >"$evidence/valgrind-$name.out" 2>&1 || true
      else
        bash -n "$path"
        printf "script syntax valid; native Valgrind not applicable\n" \
          >"$evidence/valgrind-$name.log"
      fi
    done <"$inventory"
    chmod -R a+rwX "$evidence"
  '
