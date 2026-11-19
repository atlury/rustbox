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
  --workdir /work \
  "$tool_image" "$@"

