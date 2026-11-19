#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
"$root/scripts/verify_source_tree.py" util-linux
python3 -c 'import json; assert json.load(open("work/upstream/.state/util-linux.json"))["signature_verified"] is True'

docker volume create rustbox-util-linux-source-2.42.4 >/dev/null
exec docker run --rm \
  --platform linux/amd64 \
  --volume "$root:/work:ro" \
  --volume rustbox-util-linux-source-2.42.4:/rustbox-util-linux-source \
  --workdir /work \
  rustbox-tools:2026-11-19 sh -eu -c '
    source=/rustbox-util-linux-source/util-linux-2.42.4
    if test ! -e "$source"; then
      cp -a work/upstream/util-linux-2.42.4 "$source"
      printf "%s\n" fbd62a100ab7bb8746ba0661255c3c48185b1e9021507c624da01fbc696330ec \
        > /rustbox-util-linux-source/archive.sha256
      chmod -R a-w "$source"
    fi
    test "$(cat /rustbox-util-linux-source/archive.sha256)" = \
      fbd62a100ab7bb8746ba0661255c3c48185b1e9021507c624da01fbc696330ec
    diff -qr work/upstream/util-linux-2.42.4 "$source"
  '
