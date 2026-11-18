#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

rustbox-tool-report
printf '%-16s %s\n' abidiff "$(abidiff --version | head -1)"
printf '%-16s %s\n' abi-dumper "$(abi-dumper --version | head -1)"
printf '%-16s %s\n' abi-checker "$(abi-compliance-checker --version | head -1)"
printf '%-16s %s\n' pahole "$(pahole --version | head -1)"
printf '%-16s %s\n' creduce "$(creduce --version | head -1)"
printf '%-16s %s\n' cvise "$(cvise --version | head -1)"
printf '%-16s %s\n' c2rust-rustc \
  "$(RUSTUP_TOOLCHAIN=nightly-2023-04-15 rustc --version)"
