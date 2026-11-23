#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-inetutils:2026-11-23 \
  --file "$root/tools/Inetutils.Dockerfile" "$root"
