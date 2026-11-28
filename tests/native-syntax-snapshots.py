#!/usr/bin/env python3
"""A later Cargo build can replace its release path while an earlier compiler census is still running."""
# SPDX-License-Identifier: 0BSD
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_c_string_sources import native_snapshot


def identity(path):
    st = path.stat()
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns


with TemporaryDirectory() as work:
    release = Path(work) / "release"
    release.mkdir()
    built = release / "scanner"
    paths = []
    for status in (4, 7):
        new = release / "new"
        new.write_text(f"#!/bin/sh\nexit {status}\n")
        new.chmod(0o755)
        new.replace(built)
        paths.append(native_snapshot(built, identity(built)))
        if status == 4:
            first_id = identity(built)
    native_snapshot.cache_clear()
    try:
        native_snapshot(built, first_id)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("a stale file identity selected the replacement scanner")
    built.unlink()
    assert paths[0] != paths[1]
    assert [subprocess.run([path]).returncode for path in paths] == [4, 7]
print("Both original scanner versions ran after the build directory entry was replaced and unlinked.")
