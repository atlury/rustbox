#!/usr/bin/env python3
"""Live counts may change digit width while the column still ends at the same position."""
from pathlib import Path
from runpy import run_path

mask = run_path(str(Path(__file__).with_name("util-linux-small-13-differential.py")))["mask_pid_count"]
header = b"        NS TYPE NPROCS\n"
one = header + b"4026532739 pid       9\n"
two = header + b"4026532739 pid      10\n"
assert mask(one) == mask(two)
assert mask(two) != mask(two.replace(b"      10", b"     10"))
assert mask(two) != mask(two.replace(b"4026532739", b"4026532738"))
for malformed in (b"4026532739 pid     1x", b"4026532739 pid\n10", b"4026532739 ipc     10"):
    assert mask(malformed) == malformed
print("Masked decimal counts across a digit-width change while retaining the row, column alignment and namespace ID.")
