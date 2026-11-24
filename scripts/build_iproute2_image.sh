#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --platform linux/amd64 \
  --tag rustbox-iproute2:2026-11-24 \
  --file "$root/tools/Iproute2.Dockerfile" "$root"
