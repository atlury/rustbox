#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work --entrypoint sh rustbox-e2fsprogs:2026-11-24 -eu -c '
    build=/rustbox-e2fsprogs/normalized-gcc
    output=/work/work/analysis/e2fsprogs-1.47.4/program-closures/maps
    catalog=$(PYTHONPATH=/work/scripts python3 -B -c '\''
from normalize_e2fsprogs import ENTRYPOINTS
for name, source in ENTRYPOINTS:
    target = "mklost+found" if name == "mklost_found" else name
    directory = source.rsplit("/", 1)[0]
    print(f"{name}:{directory}:{target}")
'\'')

    set -- $catalog
    test "$#" -eq 20
    mkdir -p "$output"
    capture_pass()
    {
      for record in "$@"; do
        name=${record%%:*}
        remainder=${record#*:}
        directory=${remainder%%:*}
        target=${remainder#*:}
        map=$output/$name.map
        log=$output/$name-link.log

        test -x "$build/$directory/$target"
        rm -f "$build/$directory/$target" "$map" "$log"
        # Enter through the canonical top-level build so its configured
        # MCONFIG, recursive-make flags, and generated top-deps remain the
        # authority.  The synthetic target narrows that recursion to the one
        # ELF being mapped without bypassing top-level command propagation.
        make -C "$build" V=1 LDFLAGS="-Wl,-Map=$map" \
          --eval="rustbox-link-map: ; \$(MAKE) -C $directory $target" \
          rustbox-link-map >"$log" 2>&1
        test -x "$build/$directory/$target"
        test -s "$map"
      done
    }

    capture_pass "$@"
    (cd "$output" && sha256sum ./*.map >maps.sha256)
    capture_pass "$@"
    (cd "$output" && sha256sum -c maps.sha256 >reproducibility.log)
    test "$(wc -l <"$output/reproducibility.log")" -eq 20
    chmod -R a+rwX "$output"
  '
