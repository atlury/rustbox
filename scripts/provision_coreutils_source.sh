#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
"$root/scripts/verify_source_tree.py" coreutils
python3 -c 'import json; assert json.load(open("work/upstream/.state/coreutils.json"))["signature_verified"] is True'

docker volume create rustbox-coreutils-source-9.12 >/dev/null
exec docker run --rm \
  --platform linux/amd64 \
  --volume "$root:/work:ro" \
  --volume rustbox-coreutils-source-9.12:/rustbox-source \
  --workdir /work \
  rustbox-tools:2026-11-19 sh -eu -c '
    source=/rustbox-source/coreutils-9.12
    if test ! -e "$source"; then
      cp -a work/upstream/coreutils-9.12 "$source"
      printf "%s\n" a480198559733e9b3da999e90543ac6f888a2caa544d8d664c5a1f17e528e210 \
        > /rustbox-source/archive.sha256
      chmod -R a-w "$source"
    fi
    test "$(cat /rustbox-source/archive.sha256)" = \
      a480198559733e9b3da999e90543ac6f888a2caa544d8d664c5a1f17e528e210
    diff -qr work/upstream/coreutils-9.12 "$source"
  '
