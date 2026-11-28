#!/usr/bin/env python3
"""Compare both immutable GNU tar table rewrites in the same candidate executable."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from build_tar_name_tables import substitute
from check_cargo_private_inlines import digest
from test_tar_exclusion_tables import exercise as exclusions, main
from test_tar_argmatch_tables import exercise as options


def exercise(programs, directory, memcheck=False):
    return dict(exclusions=exclusions(programs, directory, memcheck),
                argmatch=options(programs, directory, memcheck),
                harness_sha256={p.name:digest(p) for p in
                                (Path(exclusions.__code__.co_filename), Path(options.__code__.co_filename))})


if __name__ == "__main__":
    main(Path(__file__).name, substitute, exercise)
