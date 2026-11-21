#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-gzip:2026-11-21 \
  --build-arg BASE_IMAGE=rustbox-grep:2026-11-21 \
  --file "$root/tools/Gzip.Dockerfile" "$root"
