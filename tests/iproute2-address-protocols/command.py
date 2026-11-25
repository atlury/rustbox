"""Compare the complete address-protocol pilot with canonical ip in one isolated Linux network namespace."""
import json
import os
from pathlib import Path
import subprocess
import sys

if sys.argv[1] == "--multicall":
    _, canonical, binary = sys.argv[1:]
    targets = [(binary, ["ip"]), (binary, ["rustbox", "ip"])]
else:
    canonical, control, pilot = sys.argv[1:]
    targets = [(control, ["ip"]), (pilot, ["ip"])]
etc = Path("/etc/iproute2")
if not os.path.ismount(etc):
    raise RuntimeError("expected a private configuration mount")
(etc / "rt_addrprotos").write_bytes(b"0 custom-zero\n127 custom-high\n255 raw-\xff\n")
commands = [
    ["-j", "address", "show", "dev", "lo"],
    ["-br", "address", "show", "dev", "lo"],
    ["-4", "-Numeric", "address", "show", "dev", "lo"],
]
for protocol in ("kernel_lo", "kernel_ra", "custom-zero", "custom-high", b"raw-\xff", "0xff", "unknown", "256"):
    commands.append(["-j", "address", "show", "dev", "lo", "proto", protocol])
for protocol in ("kernel_lo", "custom-zero", "custom-high", b"raw-\xff", "0xff", "unknown"):
    commands.append(["address", "add", "192.0.2.1/32", "dev", "no-rustbox0", "proto", protocol])
statuses = []
for args in commands:
    old = subprocess.run(["ip", *args], executable=canonical, capture_output=True, timeout=15)
    for exe, prefix in targets:
        new = subprocess.run([*prefix, *args], executable=exe, capture_output=True, timeout=15)
        if (old.returncode, old.stdout, old.stderr) != (new.returncode, new.stdout, new.stderr):
            raise ValueError((args, exe, old.returncode, new.returncode, old.stdout, new.stdout, old.stderr, new.stderr))
    if args[:2] == ["address", "add"]:
        expected = b'"proto" value is invalid' if args[-1] == "unknown" else b'Cannot find device "no-rustbox0"'
        if old.returncode == 0 or expected not in old.stderr:
            raise ValueError(("expected canonical address parser to reach the indicated failure", args, old.stderr))
    statuses.append(old.returncode)
if statuses[0] or not any(statuses) or not any(code == 0 for code in statuses[3:]):
    raise ValueError(("expected successful and rejected address-protocol queries", statuses))
print(f"{len(commands)} public ip commands matched canonical status and both output streams.")
Path("/tmp/addrprot-commands.json").write_text(json.dumps({
    "public_commands": len(commands), "canonical_successes": statuses.count(0),
    "canonical_failures_matched": len(statuses) - statuses.count(0),
}))
