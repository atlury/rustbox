#!/usr/bin/env python3
"""Exercise the compiled FTP list parser via libcurl's public wildcard and chunk APIs."""
# SPDX-License-Identifier: curl
import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import socket
from socketserver import StreamRequestHandler, TCPServer
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest

DRIVER = Path(__file__).with_suffix(".c")


class Listing(StreamRequestHandler):
    def reply(self, message):
        self.wfile.write(message + b"\r\n")

    def handle(self):
        self.connection.settimeout(30)
        self.reply(b"220 test server ready")
        data = None
        with ExitStack() as sockets:
            for command in self.rfile:
                verb = command.split()[0].upper()
                if verb == b"EPSV":
                    data = sockets.enter_context(socket.socket())
                    data.bind(("127.0.0.1", 0))
                    data.listen(1)
                    data.settimeout(30)
                    self.reply(b"229 Entering Extended Passive Mode (|||" + str(data.getsockname()[1]).encode() + b"|)")
                elif verb == b"LIST" and data is not None:
                    self.reply(b"150 Opening data connection")
                    with data.accept()[0] as peer:
                        peer.sendall(self.server.listing)
                    self.reply(b"226 Transfer complete")
                    self.server.list_count += 1
                elif verb == b"QUIT":
                    self.reply(b"221 Bye")
                    return
                else:
                    self.reply({b"USER": b"331 Password required", b"PASS": b"230 Logged in",
                                b"PWD": b'257 "/"', b"TYPE": b"200 OK"}.get(verb, b"502 Unsupported command"))


def fixtures():
    modes = [stat.filemode(stat.S_IFREG | mode)[1:].encode() for mode in range(4096)]
    def line(word, name):
        return b"-" + word + b" 1 owner group 42 Jan 01 2020 " + name + b"\r\n"
    names = [f"f{mode:04o}".encode() for mode in range(len(modes))]
    good = b"".join(line(word, name) for word, name in zip(modes, names))
    expected = [b"entry " + name + b" " + word + b" " + f"{mode:o} 1".encode()
                for mode, (word, name) in enumerate(zip(modes, names))]
    # Include an allowed character in the wrong column, a raw byte and early separators.
    invalid = [b"xrwxrwxrw", b"rwxrwxrwS", b"rw\xffrwxrwx", b"rwx", b"rwxrwxrwxr"]
    return [good, *(line(word, b"invalid") for word in invalid)], expected


def compare(link, pilot):
    if pilot is None:
        return compare_archives({}, [])
    record = json.loads((pilot / "pilot.json").read_bytes())
    release = json.loads(link.read_bytes())
    parent = ROOT / record["archive"]
    candidate = pilot / parent.name
    setup = ROOT / "work/analysis/curl-8.23.0"
    residue = setup / "hybrid-artifacts/c-residue/mprintf.o"
    if (digest(parent) != record["control_sha256"] or digest(candidate) != record["candidate_sha256"]
            or release["source_library_sha256"][record["archive"]] != digest(parent)
            or release["source_library_sha256"][str(residue.relative_to(ROOT))] != digest(residue)
            or release["binary"]["sha256"] != record["control_binary_sha256"]):
        raise ValueError("unexpected curl archive or parent")
    return compare_archives(record, [("parent", parent), ("candidate", candidate), ("memcheck", candidate)])


def compare_archives(record, variants):
    setup = ROOT / "work/analysis/curl-8.23.0"
    oracle = setup / "oracle"
    residue = setup / "hybrid-artifacts/c-residue/mprintf.o"
    canonical = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
    builds = [("gcc", oracle / "libcurl-gcc.a"), ("clang", oracle / "libcurl-clang.a"), *variants]
    listings, expected = fixtures()
    urls, servers = [], []
    with ExitStack() as contexts, TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for listing in listings:
            server = contexts.enter_context(TCPServer(("127.0.0.1", 0), Listing))
            server.listing = listing
            server.list_count = 0
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            thread.start()
            contexts.callback(thread.join)
            contexts.callback(server.shutdown)
            servers.append(server)
            urls.append(f"ftp://127.0.0.1:{server.server_address[1]}/*")
        baseline = None
        for build, archive in builds:
            executable = directory / ("candidate" if build == "memcheck" else build)
            if build in canonical and digest(archive) != canonical[build]["static_libcurl_sha256"]:
                raise ValueError("canonical curl archive has changed")
            cmd = [executable, *urls]
            if build == "memcheck":
                log = directory / "memcheck.log"
                cmd = ["valgrind", "--error-exitcode=91", "--leak-check=full", f"--log-file={log}", *cmd]
            else:
                subprocess.run(["clang-18", "-Wall", "-Wextra", "-Werror", "-O2", "-Wl,--gc-sections",
                                "-I" + str(ROOT / "work/upstream/curl-8.23.0/include"), DRIVER,
                                *([] if build in canonical else [residue]), archive, "-ldl", "-lpthread", "-lm", "-lrt",
                                "-o", executable], check=True)
            result = subprocess.run(cmd, capture_output=True, timeout=180, check=True)
            lines = result.stdout.splitlines()
            entries = [line for line in lines if line.startswith(b"entry ")]
            statuses = [line for line in lines if line.startswith(b"status ")]
            if (sorted(entries) != sorted(expected) or statuses != [b"status 0"] + [b"status 87"] * (len(urls) - 1)
                    or result.stderr or (baseline is not None and result.stdout != baseline)):
                raise ValueError((build, len(entries), statuses, result.stderr, lines[:3]))
            if build == "memcheck" and "ERROR SUMMARY: 0 errors" not in log.read_text():
                raise ValueError("candidate Memcheck failed")
            baseline = result.stdout
        if any(s.list_count != len(builds) for s in servers):
            raise ValueError("incomplete public FTP transfers")
    return dict(record, known_modes=len(expected), rejected_listings=len(urls)-1, transfers=len(builds)*len(urls),
                builds=[name for name, _ in builds], output_sha256=sha256(baseline).hexdigest(),
                listing_sha256=[sha256(s).hexdigest() for s in listings], driver_sha256=digest(DRIVER))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path, nargs="?")
    p.add_argument("pilot", type=Path, nargs="?")
    args = p.parse_args()
    if (args.link is None) != (args.pilot is None):
        p.error("supply both link and pilot, or neither for canonical-only checks")
    print(json.dumps(compare(args.link, args.pilot), indent=2, sort_keys=True))
