#!/usr/bin/env python3
"""Compare real-terminal color and NO_COLOR behavior through both Rustbox dispatch modes."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import errno
from hashlib import sha256
import json
import os
from pathlib import Path
import pty
import subprocess
from tempfile import TemporaryDirectory
import tty

ROOT = Path(__file__).resolve().parents[2]


def terminal(command, binary, env):
    master, slave = pty.openpty()
    with os.fdopen(master, "rb", buffering=0) as reader:
        def collect():
            result = bytearray()
            while True:
                try:
                    data = reader.read(4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                if not data:
                    break
                result.extend(data)
            return bytes(result)

        with ThreadPoolExecutor(max_workers=1) as pool:
            try:
                tty.setraw(slave)
                output = pool.submit(collect)
                process = subprocess.run(command, executable=binary, env=env, stdout=slave,
                                         stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
            finally:
                os.close(slave)
            return process.returncode, output.result(), process.stderr


def verify(elf, directory):
    alias = directory / "ip"
    alias.symlink_to(elf)
    canonical = {compiler: Path("/rustbox-iproute2/programs-" + compiler) / "ip"
                 for compiler in ("gcc", "clang-18")}
    pins = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())["canonical"]
    for cc, path in canonical.items():
        if sha256(path.read_bytes()).hexdigest() != pins[cc]["canonical_sha256"]["ip"]:
            raise ValueError(f"canonical binary changed for {cc}")

    commands = {"gcc": (["ip"], canonical["gcc"]), "clang": (["ip"], canonical["clang-18"]),
                "symlink": (["ip"], alias), "subcommand": ([elf, "ip"], elf)}
    profiles = []
    for background in ("0;7", "1;0"):
        for no_color in (None, "", "1"):
            env = dict(os.environ, LC_ALL="C", COLORFGBG=background, TERM="xterm")
            if no_color is None:
                env.pop("NO_COLOR", None)
            else:
                env["NO_COLOR"] = no_color
            for options in ((), ("-c=auto",), ("-c=always",), ("-c=never",), ("-j", "-c=auto")):
                args = [*options, "-br", "address", "show", "dev", "lo"]
                observations = {name: terminal([*prefix, *args], path, env)
                                for name, (prefix, path) in commands.items()}
                status, stdout, stderr = observations["gcc"]
                if len(set(observations.values())) != 1 or status or stderr or not stdout:
                    raise ValueError((background, no_color, options, observations))
                colored = b"\x1b[" in stdout
                if options and colored != (options in (("-c=auto",), ("-c=always",))):
                    raise ValueError(("terminal color mode", options, colored))
                profiles.append(dict(background=background, no_color=no_color, options=options,
                                     color=colored, stdout_sha256=sha256(stdout).hexdigest()))
    return dict(elf_sha256=sha256(elf.read_bytes()).hexdigest(), profiles=profiles,
                profiles_checked=len(profiles), dispatch_comparisons=4 * len(profiles))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        print(json.dumps(verify(args.elf.resolve(), Path(temp)), indent=2, sort_keys=True))
