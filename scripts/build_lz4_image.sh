#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-lz4:2026-11-21 \
  --build-arg BASE_IMAGE=rustbox-normalize:2026-11-19 \
  --file "$root/tools/Lz4.Dockerfile" "$root"
