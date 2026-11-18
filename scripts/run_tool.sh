#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm \
  --platform linux/amd64 \
  --interactive \
  --volume "$root:/work" \
  --volume rustbox-coreutils-source-9.12:/rustbox-source:ro \
  --volume rustbox-coreutils-9.12:/rustbox-coreutils \
  --workdir /work \
  rustbox-tools:2026-11-19 "$@"

