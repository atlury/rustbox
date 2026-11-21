#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tool_image=${RUSTBOX_TOOL_IMAGE:-rustbox-tools:2026-11-19}
exec docker run --rm \
  --platform linux/amd64 \
  --interactive \
  --volume "$root:/work" \
  --volume rustbox-coreutils-source-9.12:/rustbox-source:ro \
  --volume rustbox-coreutils-9.12:/rustbox-coreutils \
  --volume rustbox-util-linux-source-2.42.4:/rustbox-util-linux-source:ro \
  --volume rustbox-util-linux-2.42.4:/rustbox-util-linux \
  --volume rustbox-m4-1.4.21:/rustbox-m4 \
  --volume rustbox-pkgconf-3.0.11:/rustbox-pkgconf \
  --volume rustbox-file-5.48:/rustbox-file \
  --volume rustbox-patch-2.8:/rustbox-patch \
  --volume rustbox-sed-4.10:/rustbox-sed \
  --volume rustbox-diffutils-3.12:/rustbox-diffutils \
  --volume rustbox-grep-3.12:/rustbox-grep \
  --volume rustbox-bc-1.08.2:/rustbox-bc \
  --volume rustbox-attr-2.6.0:/rustbox-attr \
  --volume rustbox-acl-2.4.0:/rustbox-acl \
  --volume rustbox-lz4-1.11.1:/rustbox-lz4 \
  --workdir /work \
  "$tool_image" "$@"

