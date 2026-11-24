#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

if [ "$#" -ne 1 ]; then
	echo "usage: $0 OUTPUT-DIRECTORY" >&2
	exit 2
fi

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
output=$1
compiler=${CC:-cc}

mkdir -p "$output"
"$compiler" -std=c11 -Os -Wall -Wextra -Werror \
	-ffunction-sections -fdata-sections \
	"$root/bridges/ncursesw6_config.c" \
	-Wl,--gc-sections -o "$output/ncursesw6-config"
"$compiler" -std=c11 -Os -Wall -Wextra -Werror \
	-ffunction-sections -fdata-sections -DRUSTBOX_MULTICALL \
	-c "$root/bridges/ncursesw6_config.c" \
	-o "$output/ncursesw6-config.o"
