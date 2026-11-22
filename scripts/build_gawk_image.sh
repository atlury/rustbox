#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-gawk:2026-11-22 \
  --build-arg BASE_IMAGE=rustbox-findutils:2026-11-22 \
  --file "$root/tools/Gawk.Dockerfile" "$root"
