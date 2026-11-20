#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker build --tag rustbox-file:2026-11-20 \
  --build-arg BASE_IMAGE=rustbox-normalize:2026-11-19 \
  --file "$root/tools/File.Dockerfile" "$root"
