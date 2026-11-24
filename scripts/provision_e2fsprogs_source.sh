#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/provision_e2fsprogs_source.py" download
status=$(
  docker run --rm --interactive --platform linux/amd64 \
    --volume "$root:/work" --workdir /work \
    rustbox-iproute2:2026-11-24 sh -eu -c '
      home=$(mktemp -d)
      chmod 700 "$home"
      GNUPGHOME="$home" gpg --batch --import /work/.cache/downloads/e2fsprogs-release-key.asc \
        >/dev/null 2>&1
      xz -dc /work/.cache/downloads/e2fsprogs-1.47.4.tar.xz | \
        GNUPGHOME="$home" gpg --batch --status-fd 1 --verify \
          /work/.cache/downloads/e2fsprogs-1.47.4.tar.xz.signature - \
          2>/dev/null
    '
)
printf "%s\n" "$status" | grep -Eq \
  '^\[GNUPG:\] VALIDSIG 2B69B954DBFE0879288137C9F2F95956950D81A3 '
python3 -B "$root/scripts/provision_e2fsprogs_source.py" extract-verified
