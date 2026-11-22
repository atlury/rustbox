#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/summarize_findutils_translation.py"
