#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tool_image=${RUSTBOX_TOOL_IMAGE:-rustbox-tools:2026-11-19}
exec docker run --rm \
  --platform linux/amd64 \
  --interactive \
  --volume "$root:/work" \
  --volume rustbox-coreutils-source-9.12:/rustbox-source:ro \
  --volume rustbox-coreutils-9.12:/rustbox-coreutils \
  --volume rustbox-util-linux-source-2.42.4:/rustbox-util-linux-source:ro \
  --volume rustbox-util-linux-2.42.4:/rustbox-util-linux \
  --volume rustbox-m4-1.4.21:/rustbox-m4 \
  --volume rustbox-pkgconf-3.0.11:/rustbox-pkgconf \
  --volume rustbox-file-5.48:/rustbox-file \
  --volume rustbox-patch-2.8:/rustbox-patch \
  --volume rustbox-sed-4.10:/rustbox-sed \
  --volume rustbox-diffutils-3.12:/rustbox-diffutils \
  --volume rustbox-grep-3.12:/rustbox-grep \
  --volume rustbox-bc-1.08.2:/rustbox-bc \
  --volume rustbox-attr-2.6.0:/rustbox-attr \
  --volume rustbox-acl-2.4.0:/rustbox-acl \
  --volume rustbox-lz4-1.11.1:/rustbox-lz4 \
  --volume rustbox-gzip-1.14:/rustbox-gzip \
  --volume rustbox-less-710:/rustbox-less \
  --volume rustbox-xz-5.8.4:/rustbox-xz \
  --volume rustbox-zstd-1.5.7:/rustbox-zstd \
  --volume rustbox-tar-1.35:/rustbox-tar \
  --volume rustbox-ncurses-6.6:/rustbox-ncurses \
  --volume rustbox-findutils-4.10.0:/rustbox-findutils \
  --volume rustbox-gawk-5.4.0:/rustbox-gawk \
  --volume rustbox-flex-2.6.4:/rustbox-flex \
  --volume rustbox-bison-3.8.2:/rustbox-bison \
  --volume rustbox-curl-8.23.0:/rustbox-curl \
  --volume rustbox-inetutils-2.8:/rustbox-inetutils \
  --volume rustbox-kmod-34.3:/rustbox-kmod \
  --volume rustbox-procps-ng-4.0.7:/rustbox-procps \
  --volume rustbox-shadow-4.20.4:/rustbox-shadow \
  --workdir /work \
  "$tool_image" "$@"

