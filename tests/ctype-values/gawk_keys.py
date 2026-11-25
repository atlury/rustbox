"""Exercise GNU awk integer and string array subscripts at every first-byte value."""
# SPDX-License-Identifier: 0BSD
from hashlib import sha256
import os
import subprocess

SCRIPT = r'''
BEGIN { RS = sprintf("%c%c%c", 1, 2, 3) }
{
    key = $0 ""
    before = key in seen
    seen[key]++
    printf "%d %d %d %d %d\n", NR, length(key), before, seen[key], length(seen)
}
END {
    for (i = -16; i <= 16; i++)
        printf "%d %d %d\n", i, i in seen, seen[i]
}'''


def run(programs, work, *, subcommand=None):
    locales = sorted(set(subprocess.check_output(["locale", "-a"], text=True).splitlines()))
    if not {"C", "fr_FR.iso88591", "ja_JP.eucjp"} <= set(locales):
        raise ValueError("expected canonical locale coverage")
    keys = [bytes([i]) + suffix for i in range(256) for suffix in (b"", b"0", b"15", b"7x")]
    keys += [str(n).encode() for n in range(-16, 17)]
    keys += [b"-0", b"00", b"+0", b"01", b"-01", b"1e0", b"1.0", b"2147483647", b"2147483648",
             b"-2147483649", b"9007199254740993", b"9223372036854775808", b"18446744073709551616"]
    records = keys + list(reversed(keys))
    separator = bytes([1, 2, 3])
    assert not any(separator in key for key in records)
    stdin = separator.join(records) + separator
    memory = 0
    parsed = {}
    profiles = {}
    for loc in locales:
        for mode, opts in (("locale", []), ("bytes", ["-b"])):
            expected = None
            for name, binary in programs.items():
                for check in ([False, True] if loc in ("C", "fr_FR.iso88591") and mode == "locale" else [False]):
                    log = work / "keys-memcheck"
                    entry = work / "gawk"
                    entry.symlink_to(binary)
                    cmd = [str(subcommand), "gawk", *opts, SCRIPT] if name == "subcommand" and subcommand else ["./gawk", *opts, SCRIPT]
                    if check:
                        cmd = ["valgrind", "--error-exitcode=99", "--leak-check=no", "--log-file=" + str(log), *cmd]
                    result = subprocess.run(cmd, input=stdin, capture_output=True, timeout=100, cwd=work,
                                            env=dict(os.environ, LC_ALL=loc, TZ="UTC0"))
                    entry.unlink()
                    actual = (result.stdout, result.stderr)
                    lines = result.stdout.splitlines()
                    count = len(lines) - 33
                    if (result.returncode or count <= 0 or count > len(records) or mode == "bytes" and count != len(records)
                            or any(line.split(b" ", 1)[0] != str(i).encode() for i, line in enumerate(lines[:count], 1))
                            or expected is not None and expected != actual
                            or check and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                        raise ValueError((loc, mode, name, check, result.returncode, result.stderr[:300]))
                    expected = actual
                    memory += int(check)
            parsed[loc + "/" + mode] = count
            profiles[loc + "/" + mode] = [sha256(part).hexdigest() for part in expected]
    return dict(input_records_per_run=len(records), input_sha256=sha256(stdin).hexdigest(),
                locales=len(locales), profiles=profiles, parsed_records=parsed, memcheck_runs=memory)
