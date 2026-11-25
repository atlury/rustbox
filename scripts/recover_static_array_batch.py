#!/usr/bin/env python3
"""Retry changed whole archives using only the C strings inside top-level array initializers."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import fcntl
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import digest
from recover_literal_array_modules import recover


def run(link, batch, output, packages, *, check=None):
    original = digest(link)
    report_file = batch / "results.json"
    raw = report_file.read_bytes()
    report = json.loads(raw)
    if report["link_report_sha256"] != original:
        raise ValueError("whole-archive source selection differs from this link")
    keys = [k for k, why in sorted(report["deferred"].items()) if why == "rebuilt archive bytes differ"
            and (not packages or Path(k).parts[2] in packages)]
    if not keys or set(packages) - {Path(k).parts[2] for k in keys}:
        raise ValueError("no changed whole archive for the requested package")
    if check is None:
        output.mkdir(exist_ok=True)
    else:
        saved = check.read_bytes()
    result = dict(link_report_sha256=original, whole_batch_sha256=sha256(raw).hexdigest(),
                  identical={}, changed={}, no_proper_subset=[], errors={})
    for key in keys:
        name = Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12]
        with (nullcontext() if check is not None else (output / (name + ".lock")).open("a")) as lock:
            if lock is not None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                trial = recover(link, batch / name, output / name, include_mixed=True, skip_empty=True,
                                read_only=check is not None, expected_archive=key)
            except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
                if check is not None:
                    raise
                result["errors"][key] = str(error)
                print(f"{name}: archive verification failed: {error}", flush=True)
                continue
        if trial is None:
            result["no_proper_subset"].append(key)
            print(f"{name}: no additional array subset", flush=True)
        else:
            row = trial["candidate"]
            group = "identical" if trial["byte_identical"] else "changed"
            result[group][key] = row
            print(f"{name}: {row['raw_pointer_types_removed']} pointer casts, archive {group}", flush=True)
    if digest(link) != original or report_file.read_bytes() != raw:
        raise ValueError("selected link or whole-archive trials changed during recovery")
    result["verified_raw_pointer_types_removed"] = sum(r["raw_pointer_types_removed"] for r in result["identical"].values())
    if check is not None:
        if json.loads(saved) != result or saved != check.read_bytes():
            raise ValueError("published array batch differs from the independent replay")
        print(f"Verified {len(keys)} archive outcomes and {result['verified_raw_pointer_types_removed']} removed casts.")
        return False
    filename = "results.json" if not packages else "results-" + "-".join(sorted(set(packages))) + ".json"
    with TemporaryDirectory(dir=output) as tmp:
        staged = Path(tmp) / filename
        staged.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        staged.replace(output / filename)
    return bool(result["errors"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("link", "batch", "output"):
        parser.add_argument(argument, type=Path)
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("--check", type=Path, help="verify a saved report and all existing archives without rebuilding archives or rewriting reports")
    args = parser.parse_args()
    raise SystemExit(run(args.link.resolve(), args.batch.resolve(), args.output.resolve(), args.package, check=args.check))
