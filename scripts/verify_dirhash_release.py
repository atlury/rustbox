#!/usr/bin/env python3
"""Verify an array-hardened multicall against its control release and all local package suites."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from test_inline_release import SENSITIVE, all_packages
from verify_declaration_release import logged


def verify(before, binary, output, jobs, independent_replay=None, chain_from=None):
    selected = LINK_REPORT.read_bytes()
    release = json.loads(selected)
    if digest(binary) != release["binary"]["sha256"]:
        raise ValueError("test executable differs from the linked directory hash release")
    output.mkdir()
    current = output / "release.json"
    current.write_bytes(selected)
    previous = output / "control.json"
    previous.write_bytes(before.read_bytes())
    scripts = ROOT / "scripts"

    def packages(names, folder):
        if folder == "independent" and independent_replay:
            result = json.loads(independent_replay.read_bytes())
        else:
            command = [sys.executable, "-B", scripts / "test_inline_release.py", previous, current, binary,
                       "--all-packages", "--jobs", str(jobs), "--output", output / folder]
            for name in sorted(names):
                command.extend(["--package", name])
            logged(command, output / f"{folder}.log")
            result = json.loads((output / folder / "results.json").read_bytes())
        statuses = result["statuses"]
        if (set(statuses) != names or any(type(code) is not int or code != 0 for code in statuses.values())
                or result["binary_sha256"] != digest(binary)
                or result["link_report_sha256"] != digest(current)
                or result["previous_link_report_sha256"] != digest(previous)):
            raise ValueError(f"package coverage differs for {folder}")
        return statuses

    tasks = [
        ("dispatcher", ["test_rustbox_multicall.sh"]),
        ("batch-differential", ["test_rustbox_batch_differential.sh"]),
        ("iproute2-live", ["test_iproute2_rtattr.sh", "--multicall"]),
        ("e2fsprogs-dirhash", ["test_e2fsprogs_dirhash_arrays.sh", "--multicall"]),
        ("e2fsprogs-bitcount", ["test_e2fsprogs_bitcount.sh", "--multicall"]),
        ("e2fsprogs-crc16", ["test_e2fsprogs_crc16.sh", "--multicall"]),
    ]
    if any("hangul" in row for row in release["e2fsprogs_dirhash_arrays"].values()):
        tasks.append(("e2fsprogs-hangul", ["test_e2fsprogs_hangul.sh", "--multicall"]))
    if any("trie" in row for row in release["e2fsprogs_dirhash_arrays"].values()):
        tasks.append(("e2fsprogs-utf8-trie", ["test_e2fsprogs_utf8_trie.sh", "--multicall"]))
    if chain_from:
        original = output / "original-control.json"
        original.write_bytes(chain_from.read_bytes())
        with (output / "intermediate-inventory.json").open("wb") as stream:
            subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", previous,
                            "--verify-dirhash-from", original], cwd=ROOT, stdout=stream, check=True)
    inventory = output / "inventory.json"
    with inventory.open("wb") as stream:
        subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", current,
                        "--verify-dirhash-from", previous], cwd=ROOT, stdout=stream, check=True)
    registered = all_packages()
    with ThreadPoolExecutor(max_workers=1) as worker:
        independent = worker.submit(packages, registered - SENSITIVE, "independent")
        for name, (tool, *args) in tasks:
            logged([scripts / tool, *args], output / f"{name}.log")
            print(f"{name} passed", flush=True)
        statuses = independent.result()
    statuses.update(packages(registered & SENSITIVE, "sensitive"))
    for family in ("inetutils", "e2fsprogs", "iproute2", "curl", "rustbox"):
        logged([scripts / f"summarize_{family}_multicall.sh"], output / f"summary-{family}.log")
    if LINK_REPORT.read_bytes() != selected or digest(binary) != release["binary"]["sha256"]:
        raise ValueError("release changed during verification")
    result = {"link_report_sha256": hashlib.sha256(selected).hexdigest(), "previous_link_report_sha256": digest(previous),
              "binary_sha256": release["binary"]["sha256"], "packages": statuses, "passed_checks": [name for name, _ in tasks]}
    if chain_from:
        intermediate = json.loads((output / "intermediate-inventory.json").read_bytes())
        result["original_link_report_sha256"] = digest(original)
        result["intermediate_binary_sha256"] = intermediate["binary_sha256"]
        result["intermediate_raw_pointer_type_tokens"] = intermediate["all"]["raw_pointer_type_tokens"]
    if "e2fsprogs-hangul" in result["passed_checks"]:
        log = (output / "e2fsprogs-hangul.log").read_text()
        pilot = json.loads((ROOT / "evidence/e2fsprogs-hangul-pilot.json").read_bytes())
        archive, = (row for name, row in release["e2fsprogs_dirhash_arrays"].items() if Path(name).parent.name == "debugfs")
        counts = [int(n) for n in re.findall(r"^(\d+) canonical ", log, re.M)]
        fields = ("leaf_buffer_comparisons", "public_nls_comparisons", "memcheck_comparisons", "debugfs_commands")
        parent_sha = archive["trie"]["parent_archive_sha256"] if "trie" in archive else archive["candidate_sha256"]
        if (counts != [pilot[k] for k in fields] or "ERROR SUMMARY: 0 errors" not in log
                or parent_sha != pilot["debugfs_archive_sha256"]):
            raise ValueError("multicall Hangul tests differ from the verified pilot coverage or archive")
        result["hangul"] = dict(zip(fields, counts), debugfs_archive_sha256=archive["candidate_sha256"])
    if "e2fsprogs-utf8-trie" in result["passed_checks"]:
        log = (output / "e2fsprogs-utf8-trie.log").read_text()
        pilot = json.loads((ROOT / "evidence/e2fsprogs-utf8-trie-pilot.json").read_bytes())
        counts = re.findall(r"^(\d+) trie leaf selections and (\d+) public NLS cases matched", log, re.M)
        expected = [(pilot["canonical_leaf_selections"], pilot["canonical_nls_cases"]),
                    (pilot["memcheck_leaf_selections"], pilot["memcheck_nls_cases"])]
        if ([(int(x), int(y)) for x, y in counts] != expected or "ERROR SUMMARY: 0 errors" not in log
                or f'{pilot["debugfs_commands"]} canonical debugfs Hangul commands matched' not in log
                or result["hangul"]["debugfs_archive_sha256"] != pilot["candidate_sha256"]):
            raise ValueError("multicall trie comparisons differ from the exhaustively tested archive")
        result["trie"] = {key: pilot[key] for key in ("canonical_leaf_selections", "canonical_nls_cases",
                                                      "memcheck_leaf_selections", "memcheck_nls_cases", "debugfs_commands")}
    (output / "replays.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(f"Verified the directory hash conversion and {len(registered)} package suites", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path, help="saved link report from before the live conversion")
    parser.add_argument("binary", type=Path, help="saved copy of the newly linked Linux ELF")
    parser.add_argument("output", type=Path, help="new results directory")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--independent-replay", type=Path,
                        help="verified results from all independent packages for this exact release and control")
    parser.add_argument("--chain-from", type=Path, help="also verify the intermediate archive migration against its original release")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    verify(args.previous.resolve(), args.binary.resolve(), args.output.resolve(), args.jobs, args.independent_replay, args.chain_from)
