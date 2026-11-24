#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    output=/work/work/analysis/e2fsprogs-1.47.4/program-hybrids
    hybrids=/rustbox-e2fsprogs/program-hybrids
    programs="badblocks chattr debugfs dumpe2fs e2freefrag e2fsck e2image e2initrd_helper e2undo e4crypt e4defrag filefrag fsck fuse2fs logsave lsattr mke2fs mklost_found resize2fs tune2fs"

    python3 -B /work/tests/e2fsprogs-hybrid-differential.py \
      --canonical-root /rustbox-e2fsprogs/stage-gcc \
      --hybrid-root "$hybrids" \
      --output "$output/differential.json"

    rm -f "$output"/valgrind-*.log "$output"/valgrind-*.out
    temporary=$(mktemp -d)
    trap '\''rm -rf "$temporary"'\'' EXIT HUP INT TERM
    for name in $programs; do
      (
        cd "$temporary"
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible \
          --log-file="$output/valgrind-$name.log" \
          "$hybrids/$name" --help >"$output/valgrind-$name.out" 2>&1 || true
      )
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes" "$output/valgrind-$name.log"
      fi
    done
    test "$(find "$output" -name "valgrind-*.log" -type f | wc -l)" -eq 20
    chmod -R a+rwX "$output"
  '
