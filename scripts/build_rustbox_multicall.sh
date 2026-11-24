#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/link_rustbox_multicall.py \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --m4-rust-library /work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-stable/target/release/libm4_1_4_21_normalized_audit.a \
    --m4-support-library /rustbox-m4/normalized-clang/lib/libm4.a \
    --pkgconf-rust-library /work/work/analysis/pkgconf-3.0.11/translations/c2rust-0.22.1/pkgconf-3.0.11-stable/target/release/libpkgconf_3_0_11_normalized_audit.a \
    --file-rust-library /work/work/analysis/file-5.48/translations/c2rust-0.22.1/file-5.48-stable/target/release/libfile_5_48_normalized_audit.a \
    --patch-rust-library /work/work/analysis/patch-2.8/translations/c2rust-0.22.1/patch-2.8-stable/target/release/libpatch_2_8_normalized_audit.a \
    --sed-rust-library /work/work/analysis/sed-4.10/translations/c2rust-0.22.1/sed-4.10-stable/target/release/libsed_4_10_normalized_audit.a \
    --diffutils-rust-library /work/work/analysis/diffutils-3.12/translations/c2rust-0.22.1/diffutils-3.12-stable/target/release/libdiffutils_3_12_normalized_audit.a \
    --grep-rust-library /work/work/analysis/grep-3.12/translations/c2rust-0.22.1/grep-3.12-stable/target/release/libgrep_3_12_normalized_audit.a \
    --gawk-rust-library /work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-core-stable/target/release/libgawk_5_4_0_core.a \
    --gawk-pma-residue /work/build/gawk-5.4.0-hybrid/c-residue/pma.o \
    --bc-rust-library /work/work/analysis/bc-1.08.2/translations/c2rust-0.22.1/bc-1.08.2-stable/target/release/libbc_1_08_2_normalized_audit.a \
    --attr-rust-library /work/work/analysis/attr-2.6.0/translations/c2rust-0.22.1/attr-2.6.0-stable/target/release/libattr_2_6_0_normalized_audit.a \
    --acl-rust-library /work/work/analysis/acl-2.4.0/translations/c2rust-0.22.1/acl-2.4.0-stable/target/release/libacl_2_4_0_normalized_audit.a \
    --lz4-rust-library /work/work/analysis/lz4-1.11.1/translations/c2rust-0.22.1/lz4-1.11.1-stable/target/release/liblz4_1_11_1_normalized_audit.a \
    --less-rust-library /work/work/analysis/less-710/translations/c2rust-0.22.1/less-710-stable/target/release/libless_710_normalized_audit.a \
    --gzip-rust-library /work/work/analysis/gzip-1.14/translations/c2rust-0.22.1/gzip-1.14-stable/target/release/libgzip_1_14_reachable_audit.a \
    --gzip-support-library /rustbox-gzip/normalized-clang/lib/libgzip.a \
    --xz-rust-library /work/work/analysis/xz-5.8.4/translations/c2rust-0.22.1/xz-5.8.4-stable/target/release/libxz_5_8_4_normalized_audit.a \
    --zstd-rust-library /work/work/analysis/zstd-1.5.7/translations/c2rust-0.22.1/zstd-1.5.7-stable/target/release/libzstd_1_5_7_normalized_audit.a \
    --tar-rust-library /work/work/analysis/tar-1.35/translations/c2rust-0.22.1/tar-1.35-stable/target/release/libtar_1_35_normalized_audit.a \
    --ncurses-rust-library /work/work/analysis/ncurses-6.6/translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable/target/release/libncurses_6_6_normalized_audit.a \
    --tar-c-residue-directory /work/work/analysis/tar-1.35/hybrid-artifacts/c-residue \
    --findutils-rust-library /work/work/analysis/findutils-4.10.0/translations/c2rust-0.22.1/findutils-4.10.0-stable/target/release/libfindutils_4_10_0_combined.a \
    --findutils-c-residue-directory /work/work/analysis/findutils-4.10.0/hybrid-artifacts/c-residue \
    --flex-rust-library /work/work/analysis/flex-2.6.4/translations/c2rust-0.22.1/flex-2.6.4-stable/target/release/libflex_2_6_4_normalized_audit.a \
    --bison-rust-library /work/work/analysis/bison-3.8.2/translations/c2rust-0.22.1/bison-3.8.2-stable/target/release/libbison_3_8_2_normalized_audit.a \
    --bison-c-residue-directory /work/work/analysis/bison-3.8.2/hybrid-artifacts/c-residue \
    --curl-rust-library /work/work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable/target/release/libcurl_8_23_0_normalized_audit.a \
    --curl-c-residue-directory /work/work/analysis/curl-8.23.0/hybrid-artifacts/c-residue \
    --inetutils-rust-directory /work/work/analysis/inetutils-2.8/program-translations/cargo-target/release \
    --inetutils-telnet-c-boundary /rustbox-inetutils/normalized-clang/lib/libgnu_a-printf-args.o \
    --iproute2-rust-directory /work/work/analysis/iproute2-7.3.0/program-translations/cargo-target \
    --e2fsprogs-rust-directory /work/work/analysis/e2fsprogs-1.47.4/program-translations/cargo-target \
    --kmod-rust-library /work/work/analysis/kmod-34.3/translations/c2rust-0.22.1/kmod-34.3-stable/target/release/libkmod_34_3_normalized_audit.a \
    --procps-rust-library /work/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1/procps-ng-4.0.7-nightly/target/release/libprocps_ng_4_0_7_normalized_audit.a \
    --shadow-rust-library /work/work/analysis/shadow-4.20.4/translations/c2rust-0.22.1/shadow-4.20.4-nightly/target/release/libshadow_4_20_4_normalized_audit.a \
    --reuse-isolation \
    --link-report /work/work/analysis/rustbox-multicall-link.json
