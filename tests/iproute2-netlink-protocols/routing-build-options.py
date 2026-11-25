#!/usr/bin/env python3
"""Check the regular shell driver's release selections from a symlinked checkout."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
with TemporaryDirectory() as temp:
    scratch = Path(temp)
    checkout = scratch / "source"
    checkout.mkdir()
    alias = scratch / "linked"
    alias.symlink_to(checkout, target_is_directory=True)
    scripts = checkout / "scripts"
    scripts.mkdir()
    build = scripts / "build_rustbox_multicall.sh"
    shutil.copy2(ROOT / "scripts" / build.name, build)
    for name in ("strings.json", "stdio.json", "layouts.json"):
        (checkout / name).write_text("{}")
    # Capture the normal link arguments without compiling or touching the live ELF.
    (scripts / "build_private_inline_tool.sh").write_text("#!/bin/sh\nexit 0\n")
    (scripts / "build_private_inline_tool.sh").chmod(0o755)
    runner = scripts / "run_multicall_tool.sh"
    runner.write_text(f"#!{sys.executable}\nimport sys, json\nprint(json.dumps(sys.argv[1:]))\n")
    runner.chmod(0o755)
    python = scratch / "python3"
    python.write_text(f"#!{sys.executable}\nimport os, sys\n"
                      "if sys.argv[1] == '-c': os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n")
    python.chmod(0o755)
    environment = dict(os.environ, PATH=str(scratch) + os.pathsep + os.environ["PATH"])

    def select(*args):
        return json.loads(subprocess.check_output([alias / "scripts" / build.name, *args], cwd=alias, env=environment))

    option = "--iproute2-routing-protocols"
    minimum = select(option, "--curl-manual")
    assert minimum.count(option) == 1 and "--curl-manual" in minimum
    assert minimum[minimum.index("--native-c-strings") + 1] == "/work/work/analysis/routing-protocol-native-inputs.json"
    combined = select(option, "--ncurses-termtypes", "layouts.json", "--bison-literal-lengths", "--tar-borrowed-timestamps",
                      "--native-c-strings", "strings.json", "--shared-stdio", "stdio.json")
    assert combined[combined.index("--native-c-strings") + 1] == "/work/strings.json" and combined.count(option) == 1
    assert all(flag in combined for flag in ("--curl-manual", "--bison-literal-lengths", "--tar-borrowed-timestamps",
                                             "--ncurses-termtypes", "--shared-stdio"))
    lz4 = "--lz4-benchmark-dictionary"
    simple = select(lz4)
    assert simple.count(lz4) == 1 and "--curl-manual" in simple
    assert simple[simple.index("--shared-stdio") + 1].endswith("/lz4-dictionary-inputs/shared_stdio_layouts.json")
    assert simple[simple.index("--native-c-strings") + 1].endswith("/lz4-dictionary-inputs/native_c_strings.json")
    both = select(lz4, option)
    assert both.count(lz4) == both.count(option) == 1
    assert both[both.index("--native-c-strings") + 1].endswith("/lz4-routing-dictionary-inputs/native_c_strings.json")
    explicit = select(lz4, option, "--native-c-strings", "strings.json", "--shared-stdio", "stdio.json")
    assert explicit.count(lz4) == explicit.count(option) == 1
    assert explicit[explicit.index("--native-c-strings") + 1] == "/work/strings.json"
    assert explicit[explicit.index("--shared-stdio") + 1] == "/work/stdio.json"
    earlier = select("--iproute2-netlink-protocols")
    assert lz4 not in earlier and option not in earlier
print("Verified minimum, combined and previous builds from a symlinked checkout.")
