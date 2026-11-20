#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-sed:2026-11-20 \
  --build-arg BASE_IMAGE=rustbox-patch:2026-11-20 \
  --file "$root/tools/Sed.Dockerfile" "$root"

