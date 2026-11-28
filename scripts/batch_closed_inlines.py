#!/usr/bin/env python3
"""Cold-build and independently replay closed private helper groups across ranked archives."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile

from build_closed_inlines import SOURCE
from build_va_list_layout_batch import archive_folder
from check_cargo_private_inlines import ROOT, digest

EMPTY_DIAGNOSTIC = b"ValueError: these compiler-dead groups contain no raw pointer types"

def ranked_inputs(inventory, scalar_ffi):
    if scalar_ffi == "unused-types":
        from build_unused_c_types import SELECTOR
        ranked = sorted(inventory["archives"].items(), key=lambda item: (-item[1]["raw_pointer_types_removed"], item[0]))
        positive = {k: {"pointer_types": row["raw_pointer_types_removed"]} for k, row in ranked
                    if row["raw_pointer_types_removed"]}
        return positive, SELECTOR, "build_unused_c_types.py", None
    if not scalar_ffi:
        return inventory["archives"], SOURCE, "build_closed_inlines.py", EMPTY_DIAGNOSTIC
    from collections import Counter
    from build_scalar_ffi import SOURCE as ffi_source, SYMBOLS
    if scalar_ffi in ("all", "variadic"):
        driver = "build_scalar_ffi.py"
        if scalar_ffi == "variadic":
            from build_variadic_ffi import SELECTOR
            if inventory.get("variadic_scanner_sha256") != digest(SELECTOR):
                raise ValueError("ranking differs from the variadic declaration scanner")
            driver = "build_variadic_ffi.py"
        elif "variadic_scanner_sha256" in inventory:
            raise ValueError("variadic signatures require the variadic driver")
        ordered = {key: {"pointer_types": n} for key, n in sorted(inventory["archives"].items(), key=lambda item: (-item[1], item[0]))}
        return ordered, ffi_source, driver, b"ValueError: no repeated eligible libc interfaces in this crate"
    counts = Counter()
    for group in inventory["signatures"]:
        if group["signature"].split("(", 1)[0].removeprefix("fn ") in SYMBOLS:
            counts.update(group["archives"])
    ordered = {key: {"pointer_types": n} for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))}
    return ordered, ffi_source, "build_scalar_ffi.py", b"ValueError: no repeated eligible libc interfaces in this crate"


def run(link, ranking, output, packages, jobs, exclude=(), scalar_ffi=False, *, narrow_sweep=None, max_compiler_sources=None):
    inventory = json.loads(ranking.read_bytes())
    candidates, source, script, empty_diagnostic = ranked_inputs(inventory, scalar_ffi)
    parent = json.loads(link.read_bytes())
    signature = inventory["link_sha256"]
    if (digest(link) != signature or parent["binary"]["sha256"] != inventory["binary_sha256"]
            or digest(source) != inventory["scanner_sha256" if scalar_ffi == "unused-types" else "scanner_source_sha256"]):
        raise ValueError("ranking does not match the selected release and scanner")
    selected = {key: row for key, row in candidates.items()
                if (not packages or Path(key).parts[2] in packages) and Path(key).parts[2] not in exclude}
    if max_compiler_sources is not None:
        if scalar_ffi != "unused-types" or max_compiler_sources < 1:
            raise ValueError("a positive compiler-source limit requires the unused-type ranking")
        selected = {key: row for key, row in selected.items()
                    if inventory["archives"][key]["compiler_selected_sources"] <= max_compiler_sources}
    if not selected or set(packages) - {Path(key).parts[2] for key in selected}:
        raise ValueError("unknown or empty package selection")
    maximum = {}
    if narrow_sweep is not None:
        if scalar_ffi != "all":
            raise ValueError("a previous libc sweep applies only to the broader scalar ABI pass")
        narrow = json.loads((narrow_sweep / "results.json").read_bytes())
        if narrow["link_sha256"] != signature or narrow["ranking_sha256"] != digest(ranking):
            raise ValueError("previous libc sweep used another release or ranking")
        for key, row in narrow["identical"].items():
            if key in selected and selected[key]["pointer_types"] == row["raw_pointer_types_removed"]:
                maximum[key] = row
    output.mkdir(parents=True, exist_ok=True)
    driver = [sys.executable, "-B", ROOT / "scripts" / script, "--link", link]

    if scalar_ffi == "all":
        driver.append("--all-interfaces")

    def inspect(key):
        if key in maximum:
            old = archive_folder(narrow_sweep, key)
            row = maximum[key]
            if (digest(old / "pilot.json") != row["receipt_sha256"]
                    or row["candidate_sha256"] != row["control_sha256"]
                    or digest(old / Path(key).name) != row["candidate_sha256"]):
                raise ValueError("prior byte-identical maximum differs from its compiler receipt")
            return "at_maximum", row
        folder = archive_folder(output, key)
        log = folder.with_suffix(".log")
        build = [*driver, "--archive", key, "--output", folder]
        with folder.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not folder.exists():
                cached = previous.get("empty", {}).get(key)
                old_failure = previous.get("errors", {}).get(key)
                if log.is_file() and (cached or old_failure == str(subprocess.CalledProcessError(1, build))):
                    checksum = digest(log)
                    cached_matches = cached is None or cached == {"log": log.name, "log_sha256": checksum}
                    if cached_matches and digest(ROOT / key) == parent["source_library_sha256"][key]:
                        with log.open("rb") as stream:
                            if any(line.rstrip() == empty_diagnostic for line in stream):
                                return "empty", {"log": log.name, "log_sha256": checksum}
                with log.open("wb") as stream:
                    proc = subprocess.run(build,
                                          stdout=stream, stderr=subprocess.STDOUT)
                if proc.returncode:
                    with log.open("rb") as stream:
                        if any(line.rstrip() == empty_diagnostic for line in stream):
                            return "empty", {"log": log.name, "log_sha256": digest(log)}
                    proc.check_returncode()
            with log.open("ab") as stream:
                replay = [*build, "--replay"] if scalar_ffi in ("variadic", "unused-types") else [*driver, "--replay", folder]
                subprocess.run(replay, check=True, stdout=stream, stderr=subprocess.STDOUT)
            row = json.loads((folder / "pilot.json").read_bytes())
            if scalar_ffi == "variadic" and row.get("variadic_scanner_sha256") != inventory["variadic_scanner_sha256"]:
                raise ValueError("archive used a different variadic declaration scanner")
            if (bool(row.get("all_scalar_interfaces")) != (scalar_ffi == "all") or row["archive"] != key or row["control_binary_sha256"] != inventory["binary_sha256"]
                    or not 0 < row["raw_pointer_types_removed"] <= selected[key]["pointer_types"]):
                raise ValueError("compiler receipt does not match ranked candidate")
            if scalar_ffi == "unused-types" and any(row.get(field) != value for field, value in inventory["archives"][key].items()):
                raise ValueError("unused type closure differs from the ranked compiler inputs")
            category = "identical" if row["control_sha256"] == row["candidate_sha256"] else "changed"
            return category, {k: v for k, v in row.items() if k != "dead_sites"} | {"receipt_sha256": digest(folder / "pilot.json")}

    result = dict(link_sha256=signature, binary_sha256=inventory["binary_sha256"], ranking_sha256=digest(ranking),
                  selected=len(selected), identical={}, changed={}, empty={}, errors={})
    if max_compiler_sources is not None:
        result["max_compiler_sources"] = max_compiler_sources
    if narrow_sweep is not None:
        result["at_maximum"] = {}
    # Serialize supervisors sharing an output directory. Individual pilots survive interruptions.
    with (output / "batch.lock").open("a") as lock, ThreadPoolExecutor(max_workers=jobs) as pool:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot = output / "results.json"
        previous = json.loads(snapshot.read_bytes()) if snapshot.is_file() else {}
        scope = "all-scalar" if scalar_ffi == "all" else "libc" if scalar_ffi else "private-inlines"
        if scalar_ffi in ("variadic", "unused-types"):
            scope = scalar_ffi
        result["scope"] = scope
        if previous and (previous["link_sha256"] != signature or previous["ranking_sha256"] != result["ranking_sha256"]
                         or previous.get("scope", "libc" if scalar_ffi is True else "private-inlines") != scope):
            raise ValueError("output belongs to a different release, ranking or transformation")
        tasks = {pool.submit(inspect, key): key for key in selected}
        for task in as_completed(tasks):
            key = tasks[task]
            try:
                category, row = task.result()
                result[category][key] = row
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
                category = "errors"
                result[category][key] = str(exc)
            if digest(link) != signature:
                raise ValueError("release changed during batch")
            result["verified_pointer_types_removed"] = sum(r["raw_pointer_types_removed"] for r in result["identical"].values())
            with NamedTemporaryFile(mode="w", dir=output, delete=False) as tmp:
                json.dump(result, tmp, indent=2, sort_keys=True)
                tmp.write("\n")
            Path(tmp.name).replace(output / "results.json")
            print(Path(key).name, category, result["verified_pointer_types_removed"], flush=True)
    return not result["errors"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("ranking", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("--exclude-package", action="append", default=[])
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--unused-c-types", action="store_const", const="unused-types", dest="scalar_ffi")
    scope.add_argument("--variadic-ffi", action="store_const", const="variadic", dest="scalar_ffi")
    scope.add_argument("--all-scalar-ffi", action="store_const", const="all", dest="scalar_ffi")
    scope.add_argument("--scalar-ffi", action="store_true", help="use the scalar ABI ranking and cold-build driver")
    parser.add_argument("--narrow-sweep", type=Path, help="skip previous verified builds already at the ranked maximum")
    parser.add_argument("--max-compiler-sources", type=int, help="limit each unused-type trial to this many compiled source files")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    sys.exit(0 if run(args.link, args.ranking, args.output, args.package, args.jobs, args.exclude_package, args.scalar_ffi, narrow_sweep=args.narrow_sweep,
                      max_compiler_sources=args.max_compiler_sources) else 1)
