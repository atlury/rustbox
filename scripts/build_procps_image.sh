#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-procps:2026-11-24 \
  --file "$root/tools/Procps.Dockerfile" "$root"
