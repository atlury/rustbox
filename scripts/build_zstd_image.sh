#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-zstd:2026-11-22 \
  --build-arg BASE_IMAGE=rustbox-normalize:2026-11-19 \
  --file "$root/tools/Zstd.Dockerfile" "$root"
