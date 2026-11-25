#!/usr/bin/env python3
"""Verify curl's bounded month read in HTTP requests from the complete multicall executable."""
# SPDX-License-Identifier: curl
import argparse
from email.utils import formatdate
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread

from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_curl_inputs
from preview_cargo_multicall import preview
from test_curl_month_pilot import cases


class Capture(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get_all("If-Modified-Since", []),
                                 self.headers.get_all("If-Unmodified-Since", [])))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


def calendar_requests(engines, extra_dates=()):
    inputs, times, _ = cases()
    valid = inputs.decode("latin1").splitlines()[:len(times)]
    checked = {}
    with HTTPServer(("127.0.0.1", 0), Capture) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        expected, command = [], []
        for day, timestamp in [*zip(valid, times, strict=True), *extra_dates]:
            header = [formatdate(timestamp, usegmt=True)]
            for sign in ("", "-"):
                path = f"/date/{len(expected)}"
                if command:
                    command.append("--next")
                command.extend(["--silent", "--show-error", "--noproxy", "*", "--max-time", "10",
                                "--time-cond", sign + day, origin + path])
                expected.append((path, [] if sign else header, header if sign else []))
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for name, executable in engines.items():
                server.seen = []
                proc = subprocess.run([*executable, "--disable", *command], capture_output=True,
                                      timeout=300, env=dict(os.environ, TZ="UTC", LC_ALL="C"))
                if proc.returncode or proc.stdout or proc.stderr or server.seen != expected:
                    raise ValueError(f"curl time conditions differ for {name}: status {proc.returncode}, "
                                     f"{len(server.seen)} requests, stderr {proc.stderr[:256]!r}")
                checked[name] = len(server.seen)
        finally:
            server.shutdown()
            worker.join()
    return dict(http_requests=checked, observed_headers_sha256=sha256(json.dumps(expected).encode()).hexdigest())


def commands(elf, tmp, extra_dates=()):
    oracle = ROOT / "work/analysis/curl-8.23.0/oracle"
    refs = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
    engines = {}
    for name in ("gcc", "clang"):
        binary = oracle / ("curl-" + name)
        if digest(binary) != refs[name]["sha256"]:
            raise ValueError(f"unrecognized canonical curl {name} executable")
        engines[name] = [binary]
    symlink = tmp / "curl"
    symlink.symlink_to(elf)
    engines.update(applet=[symlink], subcommand=[elf, "curl"])
    return calendar_requests(engines, extra_dates)


def namespace(path, residues, release, stage):
    if [obj.name for obj in residues] != ["mprintf.o"]:
        raise ValueError("expected curl's mprintf C object")
    archive, objects, symbols = namespace_curl_inputs(path, residues, stage)
    if symbols != release["curl_namespaced_symbols"]:
        raise ValueError("curl's linked symbols changed")
    return archive, objects


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent", "log", "pilot", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    qualified = json.loads((ROOT / "evidence/curl-month-array-pilot.json").read_bytes())
    preview(args.parent, args.log, args.pilot, args.output, qualified, namespace, commands)
