#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    build=/rustbox-iproute2/normalized-gcc
    output=/work/work/analysis/iproute2-7.3.0/program-closures/maps
    catalog=$(PYTHONPATH=/work/scripts python3 -B -c '\''
from normalize_iproute2 import ENTRYPOINTS
for name, (source, _) in sorted(ENTRYPOINTS.items()):
    print(f"{name}:{source}")
'\'')

    # Invoke every subdirectory through the top-level makefile.  IPRoute2 uses
    # .EXPORT_ALL_VARIABLES there to publish LIBNETLINK, LDLIBS, feature flags,
    # and configured paths; a direct subdirectory make silently loses them.
    set -- $catalog
    test "$#" -eq 18
    mkdir -p "$output"
    capture_pass()
    {
      for record in "$@"; do
        name=${record%%:*}
        source=${record#*:}
        directory=${source%/*}
        map=$output/$name.map
        log=$output/$name-link.log

        test -x "$build/$directory/$name"
        rm -f "$build/$directory/$name" "$map" "$log"
        # Four misc targets compile and link their C source in one gcc command.
        # Saved temporaries give their otherwise-random /tmp/cc*.o a stable name
        # in the map; the option is inert for the other link-only invocations.
        make -C "$build" V=1 SHARED_LIBS=n "CC=gcc -save-temps=obj" HOSTCC=gcc \
          LDFLAGS="-Wl,-Map=$map" \
          --eval="rustbox-link-map: ; \$(MAKE) -C $directory $name" \
          rustbox-link-map >"$log" 2>&1
        test -x "$build/$directory/$name"
        test -s "$map"
        rm -f "$build/$directory/$name-$name.i" \
          "$build/$directory/$name-$name.o" "$build/$directory/$name-$name.s"
      done
    }

    # Capture twice and retain a machine-checkable byte-reproducibility gate.
    capture_pass "$@"
    (cd "$output" && sha256sum ./*.map >maps.sha256)
    capture_pass "$@"
    (cd "$output" && sha256sum -c maps.sha256 >reproducibility.log)
    test "$(wc -l <"$output/reproducibility.log")" -eq 18
    chmod -R a+rwX "$output"
  '
