#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -u

first_line() { "$@" 2>&1 | sed -n '1p'; }
show() { label=$1; shift; printf '%-16s %s\n' "$label" "$(first_line "$@")"; }

show gcc cc --version
show clang clang-18 --version
show clang-tidy clang-tidy-18 --version
show coccinelle spatch --version
show c2rust c2rust --version
show cppcheck cppcheck --version
show sparse sparse --version
show splint splint -help version
show flawfinder flawfinder --version
printf '%-16s %s\n' codechecker \
  "$(/opt/codechecker/bin/python -c 'from importlib.metadata import version; print(version("codechecker"))')"
show valgrind valgrind --version
show afl++ afl-fuzz --version
show bear bear --version
show rustc rustc --version
show cargo cargo --version

