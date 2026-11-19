#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
expected=sha256:41a351ca225bcf38b4d49adbf4a4c9224bdd7268c526e0522e3696049401f382
actual=$(docker image inspect rustbox-tools:2026-11-19 --format '{{.Id}}')
if test "$actual" != "$expected"; then
  echo "base image ID $actual, expected $expected" >&2
  exit 1
fi
exec docker build --tag rustbox-normalize:2026-11-19 \
  --build-arg BASE_IMAGE=rustbox-tools:2026-11-19 \
  --file "$root/tools/Normalization.Dockerfile" "$root"
