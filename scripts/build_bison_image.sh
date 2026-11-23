#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-bison:2026-11-23 \
  --file "$root/tools/Bison.Dockerfile" "$root"
