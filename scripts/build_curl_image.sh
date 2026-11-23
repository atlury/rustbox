#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-curl:2026-11-23 \
  --file "$root/tools/Curl.Dockerfile" "$root"
