#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The release linker and package regressions need the same Linux runtime libraries.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
image=rustbox-e2fsprogs:2026-11-24
if [ -n "${RUSTBOX_MULTICALL_TEST_BINARY:-}" ]; then
    candidate=$RUSTBOX_MULTICALL_TEST_BINARY
    case "$candidate" in
        /*) ;;
        *) echo "Expected an absolute path to the multicall test executable" >&2; exit 2 ;;
    esac
    if [ ! -f "$candidate" ] || [ ! -x "$candidate" ]; then
        echo "Missing multicall test executable: $candidate" >&2
        exit 2
    fi
    checksum=$(python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$candidate")
    volume=rustbox-test-elf-$checksum
    docker run --rm --network none --platform linux/amd64 \
        -v "$candidate:/input:ro" -v "$volume:/snapshot" "$image" sh -eu -c '
        cd /snapshot
        if [ ! -f rustbox ]; then
            # Rename on the same filesystem so concurrent readers only see a complete executable.
            staged=$(mktemp /snapshot/.rustbox.XXXXXX)
            trap "rm -f -- $staged" EXIT
            cp /input "$staged"
            printf "%s  %s\n" "$1" "$staged" | sha256sum --quiet -c -
            chmod 555 "$staged"
            mv "$staged" rustbox
        fi
        printf "%s  rustbox\n" "$1" | sha256sum --quiet -c -
    ' snapshot "$checksum"
    set -- --multicall-test-volume "$volume" "$@"
fi
RUSTBOX_TOOL_IMAGE=$image exec "$root/scripts/run_tool.sh" "$@"
