#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/link_rustbox_multicall.py \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --m4-rust-library /work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-stable/target/release/libm4_1_4_21_normalized_audit.a \
    --m4-support-library /rustbox-m4/normalized-clang/lib/libm4.a \
    --pkgconf-rust-library /work/work/analysis/pkgconf-3.0.11/translations/c2rust-0.22.1/pkgconf-3.0.11-stable/target/release/libpkgconf_3_0_11_normalized_audit.a \
    --file-rust-library /work/work/analysis/file-5.48/translations/c2rust-0.22.1/file-5.48-stable/target/release/libfile_5_48_normalized_audit.a \
    --patch-rust-library /work/work/analysis/patch-2.8/translations/c2rust-0.22.1/patch-2.8-stable/target/release/libpatch_2_8_normalized_audit.a \
    --link-report /work/work/analysis/rustbox-multicall-link.json
