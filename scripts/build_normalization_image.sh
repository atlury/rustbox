#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
expected=sha256:404e3f20b5fba03160fae5622b6067a2122388a36b57fae29be671d83f6ebf29
actual=$(docker image inspect rustbox-tools:2026-11-19 --format '{{.Id}}')
if test "$actual" != "$expected"; then
  echo "base image ID $actual, expected $expected" >&2
  exit 1
fi
exec docker build --tag rustbox-normalize:2026-11-19 \
  --build-arg BASE_IMAGE=rustbox-tools:2026-11-19 \
  --file "$root/tools/Normalization.Dockerfile" "$root"
