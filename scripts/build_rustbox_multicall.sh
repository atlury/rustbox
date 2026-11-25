#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd -P)
lz4_dictionary=
if [ "${1:-}" = --lz4-benchmark-dictionary ]; then
    lz4_dictionary=1
    shift
fi
routing_protocols=
if [ "${1:-}" = --iproute2-routing-protocols ]; then
    routing_protocols=1
    shift
fi
term_manifest=
if [ "$#" -ge 2 ] && [ "$1" = --ncurses-termtypes ]; then
    term_manifest=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve(strict=True).relative_to(Path(sys.argv[2])))' "$2" "$root")
    shift 2
fi
va_manifest=
if [ "$#" -ge 2 ] && [ "$1" = --va-list-layouts ]; then
    va_manifest=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve(strict=True).relative_to(Path(sys.argv[2])))' "$2" "$root")
    shift 2
fi
bison_lengths=
if [ "${1:-}" = --bison-literal-lengths ]; then
    bison_lengths=1
    shift
fi
tar_timestamps=
if [ "${1:-}" = --tar-borrowed-timestamps ]; then
    tar_timestamps=1
    shift
fi
literal_manifest=
if [ "$#" -ge 2 ] && [ "$1" = --native-c-strings ]; then
    literal_manifest=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve(strict=True).relative_to(Path(sys.argv[2])))' "$2" "$root")
    shift 2
fi
stdio_manifest=
if [ "$#" -eq 2 ] && [ "$1" = --shared-stdio ]; then
    stdio_manifest=$(python3 -c 'import sys; from pathlib import Path; print(Path(sys.argv[1]).resolve(strict=True).relative_to(Path(sys.argv[2])))' "$2" "$root")
    set -- --curl-manual
fi
case "$#:${1:-}" in
    1:--iproute2-address-protocols) set -- --iproute2-address-protocols --e2fsprogs-dirhash-arrays /work/batches/e2fsprogs-trie-arrays.json ;;
    0:|1:--curl-manual) set -- --curl-manual --iproute2-netlink-protocols --iproute2-route-names --iproute2-address-protocol-copies --iproute2-address-protocols --e2fsprogs-dirhash-arrays /work/batches/e2fsprogs-trie-arrays.json ;;
    1:--iproute2-netlink-protocols) set -- --iproute2-netlink-protocols --iproute2-route-names --iproute2-address-protocol-copies --iproute2-address-protocols --e2fsprogs-dirhash-arrays /work/batches/e2fsprogs-trie-arrays.json ;;
    1:--iproute2-route-names) set -- --iproute2-route-names --iproute2-address-protocol-copies --iproute2-address-protocols --e2fsprogs-dirhash-arrays /work/batches/e2fsprogs-trie-arrays.json ;;
    1:--iproute2-address-protocol-copies) set -- --iproute2-address-protocol-copies --iproute2-address-protocols --e2fsprogs-dirhash-arrays /work/batches/e2fsprogs-trie-arrays.json ;;
    2:--e2fsprogs-dirhash-arrays) ;;
    *) echo "usage: $0 [--lz4-benchmark-dictionary] [--iproute2-routing-protocols] [--ncurses-termtypes MANIFEST] [--va-list-layouts MANIFEST] [--bison-literal-lengths] [--tar-borrowed-timestamps] [--native-c-strings MANIFEST] [--shared-stdio MANIFEST | --curl-manual | --iproute2-netlink-protocols | --iproute2-route-names | --iproute2-address-protocols | --iproute2-address-protocol-copies | --e2fsprogs-dirhash-arrays MANIFEST]" >&2; exit 2 ;;
esac
"$root/scripts/build_private_inline_tool.sh"
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-e2fsprogs
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-iproute2
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-inetutils
python3 -B "$root/scripts/batch_cargo_private_inlines.py" --release-args "$root/batches/multicall-inline-archives.args"
python3 -B "$root/scripts/prepare_second_inline_layers.py"
python3 -B "$root/scripts/check_cargo_foreign_declarations.py" --prepare
if [ "$1" = --iproute2-route-names ] || [ "$1" = --iproute2-netlink-protocols ] || [ "$1" = --curl-manual ]; then
    python3 -B "$root/scripts/build_iproute2_address_protocol_pilot.py" --prepare-copies
    python3 -B "$root/scripts/build_iproute2_route_names.py" --prepare
    if [ "$1" = --iproute2-netlink-protocols ] || [ "$1" = --curl-manual ]; then
        python3 -B "$root/scripts/build_iproute2_route_names.py" --netlink-protocols --prepare
    fi
    if [ "$1" = --curl-manual ]; then
        python3 -B "$root/scripts/curl_manual_archive.py" --prepare
    fi
elif [ "$1" = --iproute2-address-protocol-copies ]; then
    python3 -B "$root/scripts/build_iproute2_address_protocol_pilot.py" --prepare-copies
elif [ "$1" = --iproute2-address-protocols ]; then
    python3 -B "$root/scripts/build_iproute2_address_protocol_pilot.py" --prepare
fi
if [ -n "$bison_lengths" ]; then
    python3 -B "$root/scripts/bison_length_archive.py"
    set -- "$@" --bison-literal-lengths
fi
if [ -n "$tar_timestamps" ]; then
    python3 -B "$root/scripts/tar_timespec_archive.py"
    set -- "$@" --tar-borrowed-timestamps
fi
if [ -n "$lz4_dictionary" ]; then
    if [ -z "$stdio_manifest" ] || [ -z "$literal_manifest" ]; then
        inputs=work/analysis/lz4-dictionary-inputs
        if [ -n "$routing_protocols" ]; then
            inputs=work/analysis/lz4-routing-dictionary-inputs
            python3 -B "$root/scripts/lz4_dictionary_archive.py" --parent-manifests "$root/$inputs" --routing
        else
            python3 -B "$root/scripts/lz4_dictionary_archive.py" --parent-manifests "$root/$inputs"
        fi
        stdio_manifest=${stdio_manifest:-$inputs/shared_stdio_layouts.json}
        literal_manifest=${literal_manifest:-$inputs/native_c_strings.json}
    fi
    python3 -B "$root/scripts/lz4_dictionary_archive.py"
    set -- "$@" --lz4-benchmark-dictionary
fi
if [ -n "$stdio_manifest" ]; then
    python3 -B "$root/scripts/prepare_shared_stdio.py" prepare "$root/$stdio_manifest"
    set -- "$@" --shared-stdio "/work/$stdio_manifest"
fi
if [ -n "$routing_protocols" ] && [ -z "$literal_manifest" ]; then
    literal_manifest=work/analysis/routing-protocol-native-inputs.json
    python3 -B "$root/scripts/stage_routing_protocol_archives.py" --native-manifest "$root/$literal_manifest"
fi
if [ -n "$literal_manifest" ]; then
    python3 -B "$root/scripts/prepare_native_c_strings.py" prepare --cargo-only "$root/$literal_manifest"
    set -- "$@" --native-c-strings "/work/$literal_manifest"
fi
if [ -n "$routing_protocols" ]; then
    python3 -B "$root/scripts/stage_routing_protocol_archives.py"
    set -- "$@" --iproute2-routing-protocols
fi
if [ -n "$va_manifest" ]; then
    python3 -B "$root/scripts/prepare_va_list_layouts.py" prepare --cargo-only "$root/$va_manifest"
    set -- "$@" --va-list-layouts "/work/$va_manifest"
fi
if [ -n "$term_manifest" ]; then
    python3 -B "$root/scripts/prepare_ncurses_termtypes.py" prepare "$root/$term_manifest"
    set -- "$@" --ncurses-termtypes "/work/$term_manifest"
fi
unset RUSTBOX_MULTICALL_TEST_BINARY
exec "$root/scripts/run_multicall_tool.sh" python3 -B /work/scripts/link_rustbox_multicall.py \
    @/work/batches/multicall-inline-archives.args \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --m4-support-library /rustbox-m4/normalized-clang/lib/libm4.a \
    --gawk-pma-residue /work/build/gawk-5.4.0-hybrid/c-residue/pma.o \
    --gzip-support-library /rustbox-gzip/normalized-clang/lib/libgzip.a \
    --tar-c-residue-directory /work/work/analysis/tar-1.35/hybrid-artifacts/c-residue \
    --findutils-c-residue-directory /work/work/analysis/findutils-4.10.0/hybrid-artifacts/c-residue \
    --bison-c-residue-directory /work/work/analysis/bison-3.8.2/hybrid-artifacts/c-residue \
    --curl-c-residue-directory /work/work/analysis/curl-8.23.0/hybrid-artifacts/c-residue \
    --inetutils-rust-directory /work/work/analysis/inetutils-2.8/program-translations/cargo-target/release \
    --inetutils-telnet-c-boundary /rustbox-inetutils/normalized-clang/lib/libgnu_a-printf-args.o \
    --iproute2-rust-directory /work/work/analysis/iproute2-7.3.0/program-translations/cargo-target \
    --e2fsprogs-rust-directory /work/work/analysis/e2fsprogs-1.47.4/program-translations/cargo-target \
    --reuse-isolation \
    --link-report /work/work/analysis/rustbox-multicall-link.json "$@"
