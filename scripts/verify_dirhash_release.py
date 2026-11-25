#!/usr/bin/env python3
"""Verify linked E2fsprogs and IPRoute2 conversions against the control release and local package suites."""
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
from curl_manual_replay import lookup as curl_replay
from iproute2_address_protocol_archive import ARCHIVE, validate_copy_results
from iproute2_route_name_archives import additional_lookup_records
from test_inline_release import SENSITIVE, all_packages
from verify_declaration_release import logged


def checked_package_retries(result, retries, previous, current, binary):
    """Accept a complete suite rerun only for a failed package on the same ELF and links."""
    identity = {"previous_link_report_sha256": digest(previous), "link_report_sha256": digest(current),
                "binary_sha256": digest(binary)}
    statuses = result["statuses"].copy()
    if any(result[k] != v for k, v in identity.items()) or any(type(v) is not int for v in statuses.values()):
        raise ValueError("initial package result belongs to another release or has invalid statuses")
    trace = []
    for path in retries:
        raw = path.read_bytes()
        retry = json.loads(raw)
        checks = retry["statuses"]
        if (not checks or any(retry[k] != v for k, v in identity.items())
                or any(type(code) is not int or code != 0 or statuses.get(name, 0) == 0 for name, code in checks.items())):
            raise ValueError(f"retry must pass previously failed complete suites on the same release: {path}")
        trace.append(dict(result_sha256=hashlib.sha256(raw).hexdigest(),
                          previous_statuses={name: statuses[name] for name in checks}, statuses=checks))
        statuses.update(checks)
    return statuses, trace


def verify(before, binary, output, jobs, independent_replay=None, chain_from=None, copy_replay=None, fresh_curl=False, independent_retries=()):
    selected = LINK_REPORT.read_bytes()
    release = json.loads(selected)
    if digest(binary) != release["binary"]["sha256"]:
        raise ValueError("test executable differs from the linked release")
    output.mkdir()
    current = output / "release.json"
    current.write_bytes(selected)
    previous = output / "control.json"
    previous.write_bytes(before.read_bytes())
    scripts = ROOT / "scripts"

    package_retries = []
    if independent_retries and not independent_replay:
        raise ValueError("independent retries require the full set of original package results")

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
        if folder == "independent" and independent_retries:
            statuses, trace = checked_package_retries(result, independent_retries, previous, current, binary)
            package_retries.extend(trace)
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
    address_record = release.get("iproute2_address_protocols")
    prior = json.loads(previous.read_bytes())
    address_change = any(release.get(k) != prior.get(k) for k in ("iproute2_address_protocols", "iproute2_address_protocol_copies"))
    if address_record:
        tasks.append(("iproute2-address-protocols", ["test_iproute2_address_protocols.sh", "--multicall"]))
    if copy_replay and not release.get("iproute2_address_protocol_copies"):
        raise ValueError("archive replay supplied for a release without IPRoute2 address-protocol copies")
    copies = additional_lookup_records(release)
    if copies:
        image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", "rustbox-e2fsprogs:2026-11-24"], text=True).strip()
        tasks.append(("iproute2-address-protocol-copies", ["test_iproute2_address_protocols.sh", "--linked-copies"]))
    netlink = release.get("iproute2_netlink_protocols", {})
    if netlink:
        tasks.append(("iproute2-netlink-protocols", ["test_iproute2_netlink_protocols.py", "--linked", "--link", current,
                                                    "--batch", output / "netlink-comparisons", "--jobs", "3"]))
    timestamps = release.get("tar_borrowed_timestamps")
    if timestamps:
        tasks.append(("tar-borrowed-timestamps", ["test_tar_timestamp_multicall.py", "--link", current, "--binary", binary]))
    packed_manual = release.get("curl_manual")
    saved_curl = None
    curl_receipt = ROOT / "evidence/curl-manual-multicall-comparison.json"
    if packed_manual and not fresh_curl:
        curl_image = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}",
                                              "rustbox-e2fsprogs:2026-11-24"], text=True).strip()
        saved_curl = curl_replay(release, curl_image, curl_receipt)
    if packed_manual:
        tasks.append(("curl-manual", ["test_curl_manual_pilot.py", "--linked", "--link", current]))
    routes = netlink or release.get("iproute2_route_names", {})
    if routes:
        tasks.append(("iproute2-route-names", ["test_iproute2_route_names.py", "--linked", "--link", current,
                                              "--batch", output / "route-name-comparisons", "--jobs", "3"]))
    if chain_from:
        original = output / "original-control.json"
        original.write_bytes(chain_from.read_bytes())
        with (output / "intermediate-inventory.json").open("wb") as stream:
            subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", previous,
                            "--verify-dirhash-from", original], cwd=ROOT, stdout=stream, check=True)
    inventory = output / "inventory.json"
    with inventory.open("wb") as stream:
        subprocess.run([sys.executable, "-B", scripts / "audit_linked_pointers.py", current,
                        "--verify-tar-timestamps-from" if timestamps else "--verify-curl-manual-from" if packed_manual else "--verify-netlink-protocols-from" if netlink else "--verify-route-names-from" if routes else
                        "--verify-address-protocols-from" if address_change else "--verify-dirhash-from", previous], cwd=ROOT, stdout=stream, check=True)
    registered = all_packages()
    with ThreadPoolExecutor(max_workers=2) as worker:
        independent = None
        if not independent_replay:
            independent = worker.submit(packages, registered - SENSITIVE, "independent")
        # These comparisons use independent read-only inputs and private Docker
        # filesystems. Queue them beside the package suites and wait at their gates.
        comparisons = {}
        for name, (tool, *args) in tasks:
            if name == "curl-manual" and saved_curl is not None:
                continue
            if name in {"iproute2-route-names", "iproute2-netlink-protocols", "curl-manual"}:
                comparisons[name] = worker.submit(logged, [scripts / tool, *args], output / f"{name}.log")
        for name, (tool, *args) in tasks:
            log = output / f"{name}.log"
            if name == "curl-manual" and saved_curl is not None:
                log.write_text(json.dumps(saved_curl, indent=2, sort_keys=True) + "\n")
                print("Reused completed curl comparisons for the identical ELF, image, driver and oracle inputs", flush=True)
            elif name in comparisons:
                comparisons[name].result()
            elif copy_replay and name == "iproute2-address-protocol-copies":
                data = copy_replay.read_bytes()
                pilot = json.loads((ROOT / "evidence/iproute2-address-protocol-pilot.json").read_bytes())
                validate_copy_results(copies, json.loads(data), pilot["lookup_checks"], image_id)
                log.write_bytes(data)
            else:
                logged([scripts / tool, *args], log)
            print(f"{name} passed", flush=True)
        statuses = independent.result() if independent else packages(registered - SENSITIVE, "independent")
    statuses.update(packages(registered & SENSITIVE, "sensitive"))
    for family in ("inetutils", "e2fsprogs", "iproute2", "curl", "rustbox"):
        logged([scripts / f"summarize_{family}_multicall.sh"], output / f"summary-{family}.log")
    if LINK_REPORT.read_bytes() != selected or digest(binary) != release["binary"]["sha256"]:
        raise ValueError("release changed during verification")
    result = {"link_report_sha256": hashlib.sha256(selected).hexdigest(), "previous_link_report_sha256": digest(previous),
              "binary_sha256": release["binary"]["sha256"], "packages": statuses, "passed_checks": [name for name, _ in tasks]}
    if timestamps:
        result["tar_borrowed_timestamps"] = json.loads((output / "tar-borrowed-timestamps.log").read_bytes())
    if package_retries:
        result["package_retries"] = dict(original_result_sha256=digest(independent_replay), completed=package_retries)
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
    if address_record:
        log = (output / "iproute2-address-protocols.log").read_text()
        pilot = json.loads((ROOT / "evidence/iproute2-address-protocol-pilot.json").read_bytes())
        checks = pilot["lookup_checks"]
        commands = json.loads(log.splitlines()[-1])
        if (address_record["candidate_sha256"] != pilot["candidate_sha256"] or commands != pilot["command_checks"]
                or f'{checks["lookup_results_per_variant"]} address-protocol results matched across {checks["configurations"]} isolated configurations' not in log
                or f'{checks["memcheck_runs"]} Memcheck runs completed with zero errors.' not in log):
            raise ValueError("multicall IPRoute2 comparison differs from the verified pilot")
        result["iproute2_address_protocols"] = {"archive_sha256": routes.get(str(ARCHIVE), address_record)["candidate_sha256"],
                                                "lookup_results": checks["lookup_results_per_variant"],
                                                "memcheck_runs": checks["memcheck_runs"], "commands_per_dispatch_mode": commands}
    if records := copies:
        batch = json.loads((output / "iproute2-address-protocol-copies.log").read_text().splitlines()[-1])
        pilot = json.loads((ROOT / "evidence/iproute2-address-protocol-pilot.json").read_bytes())
        validate_copy_results(records, batch, pilot["lookup_checks"], image_id)
        if copy_replay:
            batch["replay_basis"] = "identical parent and candidate archives, oracle and test inputs"
        result["iproute2_address_protocol_copies"] = batch
    if routes:
        data = json.loads((output / "route-name-comparisons/results.json").read_bytes())
        pilot = json.loads((ROOT / "evidence/iproute2-route-names-pilot.json").read_bytes())
        if data.keys() != routes.keys():
            raise ValueError("incomplete scope/realm archive comparison")
        namespaces = prior["iproute2_namespaced_symbols"]
        for key, row in routes.items():
            actual = data[key]
            public = key == str(ARCHIVE)
            if (any(actual[k] != v for k, v in row.items()) or actual["profiles"] != pilot["profiles"]
                    or actual["driver_sha256"] != pilot["driver_sha256"] or actual["canonical_sources"] != pilot["canonical_sources"]
                    or actual["multicall_sha256"] != digest(binary) or actual["memcheck_runs"] != pilot["memcheck_runs"]
                    or actual["public_commands"] != (pilot["public_commands"] if public else 0)
                    or actual["public_successes"] != (pilot["public_successes"] if public else 0)):
                raise ValueError(f"unexpected canonical scope/realm replay for {key}")
            name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
            observed = actual["strong_symbol_changes"]
            original = set(namespaces[name])
            final = set(release["iproute2_namespaced_symbols"][name])
            if observed != {"added": sorted(final - original), "removed": sorted(original - final)}:
                raise ValueError(f"independent scope/realm symbol comparison differs for {name}")
        result["iproute2_route_names"] = {
            "archive_sha256": {k: v["candidate_sha256"] for k, v in routes.items()},
            "control_sha256": {k: v["control_sha256"] for k, v in routes.items()},
            "profiles": pilot["profiles"], "canonical_sources": pilot["canonical_sources"], "driver_sha256": pilot["driver_sha256"],
            "memcheck_runs": sum(v["memcheck_runs"] for v in data.values()),
            "public_commands_per_dispatch_mode": pilot["public_commands"],
            "lookup_results": sum(r["lookup_rows"] for v in data.values() for r in v["profiles"]),
            "strong_symbol_changes": {k: v["strong_symbol_changes"] for k, v in data.items() if any(v["strong_symbol_changes"].values())},
        }
    if netlink:
        replay = json.loads((output / "netlink-comparisons/results.json").read_bytes())
        if replay.keys() != netlink.keys() or any(r["multicall_sha256"] != digest(binary) for r in replay.values()):
            raise ValueError("incomplete netlink protocol release comparison")
        profiles = [p for r in replay.values() for p in r["profiles"]]
        result["iproute2_netlink_protocols"] = {
            "canonical_lookups": sum(p["forward"] + p["reverse"] for p in profiles),
            "public_commands_per_dispatch_mode": sum(p["public_commands"] for p in profiles),
            "memcheck_runs": sum(r["memcheck_runs"] for r in replay.values()),
            "archive_sha256": {k: v["candidate_sha256"] for k, v in replay.items()},
        }
    if packed_manual:
        checked = json.loads((output / "curl-manual.log").read_bytes())
        baseline = json.loads((ROOT / "evidence/curl-manual-pilot.json").read_bytes())
        if checked != dict(baseline, multicall_sha256=digest(binary)):
            raise ValueError("linked curl manual replay differs from the qualified archive, cases or outputs")
        result["curl_manual"] = checked
        if saved_curl is not None:
            result["curl_manual_replay_sha256"] = digest(curl_receipt)
    (output / "replays.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(f"Verified the linked executable with {len(tasks)} integration checks and {len(registered)} package suites", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous", type=Path, help="saved link report from before the live conversion")
    parser.add_argument("binary", type=Path, help="saved copy of the newly linked Linux ELF")
    parser.add_argument("output", type=Path, help="new results directory")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--independent-replay", type=Path,
                        help="verified results from all independent packages for this exact release and control")
    parser.add_argument("--independent-retry", action="append", type=Path, default=[],
                        help="complete successful rerun of failed packages for the same ELF and both link reports")
    parser.add_argument("--copy-replay", type=Path, help="completed canonical comparisons for the exact address-protocol archive and test hashes")
    parser.add_argument("--chain-from", type=Path, help="also verify the intermediate archive migration against its original release")
    parser.add_argument("--fresh-curl", action="store_true", help="rerun all curl manual cases even if the precise inputs and tested ELF match")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    verify(args.previous.resolve(), args.binary.resolve(), args.output.resolve(), args.jobs, args.independent_replay, args.chain_from, args.copy_replay, args.fresh_curl, args.independent_retry)
