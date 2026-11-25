#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_private_inline_tool.sh"
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-e2fsprogs
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-iproute2
python3 -B "$root/scripts/check_cargo_private_inlines.py" --prepare-inetutils
python3 -B "$root/scripts/batch_cargo_private_inlines.py" --release-args "$root/batches/multicall-inline-archives.args"
python3 -B "$root/scripts/prepare_second_inline_layers.py"
python3 -B "$root/scripts/check_cargo_foreign_declarations.py" --prepare
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
    --link-report /work/work/analysis/rustbox-multicall-link.json
