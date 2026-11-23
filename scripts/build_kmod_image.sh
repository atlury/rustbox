#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-kmod:2026-11-24 \
  --file "$root/tools/Kmod.Dockerfile" "$root"
