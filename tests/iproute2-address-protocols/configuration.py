"""Compare address-protocol name tables using only the two tmpfs mounts of the test container."""
from itertools import zip_longest
import os
from pathlib import Path
import subprocess

etc = Path("/etc/iproute2")
vendor = Path("/usr/share/iproute2")
if not all(os.path.ismount(directory) and not any(directory.iterdir()) for directory in (etc, vendor)):
    raise RuntimeError("expected the two empty IPRoute2 configuration mounts")
for directory in (etc, vendor):
    (directory / "rt_addrprotos.d").mkdir()
base = vendor / "rt_addrprotos"
local = etc / "rt_addrprotos"
vendor_drop = vendor / "rt_addrprotos.d"
local_drop = etc / "rt_addrprotos.d"
vendor_files = {base: b"200 vendor\n33 vendor-only\n25 duplicate\n15 duplicate\n201 raw-\xff\n",
                vendor_drop / "10-extra.conf": b"202 extra\n", vendor_drop / "ignored.txt": b"203 ignored\n"}
local_files = {local: b"200 local\n11 duplicate\n35 duplicate\n", local_drop / "10-extra.conf": b"204 local-extra\n"}
profiles = [
    ({}, {b"kernel_lo": 1, b"vendor": None}),
    (vendor_files, {b"vendor": 200, b"vendor-only": 33, b"extra": 202, b"duplicate": 15, b"raw-\xff": 201}),
    ({**vendor_files, **local_files}, {b"local": 200, b"vendor": None, b"vendor-only": None, b"extra": None,
                                      b"local-extra": 204, b"duplicate": 11}),
    ({local: b"200 local\ninvalid-line\n202 extra\n"}, {b"local": 200, b"extra": None}),
]
total = 0
for profile, (files, expected) in enumerate(profiles, start=1):
    for path, contents in files.items():
        path.write_bytes(contents)
    runs = [subprocess.run([f"/tmp/{variant}"], capture_output=True) for variant in ("canonical", "translated")]
    a, b = runs
    if a.returncode or b.returncode or a.stderr != b.stderr:
        raise ValueError(("address-protocol status or diagnostics differ", profile, a.returncode, b.returncode, a.stderr, b.stderr))
    if a.stdout != b.stdout:
        rows = zip_longest(a.stdout.splitlines(keepends=True), b.stdout.splitlines(keepends=True))
        raise ValueError(("address-protocol output differs", profile, next(row for row in rows if row[0] != row[1])))
    if bool(a.stderr) != (b"invalid-line" in files.get(local, b"")):
        raise ValueError(("unexpected canonical diagnostics", a.stderr))
    lines = a.stdout.splitlines()
    for name, value in {**expected, b"ignored": None, b"0xff": 255, b"256": None}.items():
        suffix = b"-1 177" if value is None else b"0 " + str(value).encode()
        if b"R 0 " + name + b" " + suffix not in lines:
            raise ValueError(("canonical configuration expectation failed", name, suffix))
    total += len(lines)
    for path in files:
        path.unlink()
print(f"{total} address-protocol results matched across {len(profiles)} isolated configurations")
