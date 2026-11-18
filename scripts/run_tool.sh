#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm \
  --volume "$root:/work" \
  --workdir /work \
  rustbox-tools:2026-11-19 "$@"

