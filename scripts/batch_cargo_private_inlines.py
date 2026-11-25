#!/usr/bin/env python3
"""Rank and independently verify private-inline candidates from a specific Linux release."""
# SPDX-License-Identifier: 0BSD
import argparse
import hashlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from check_cargo_private_inlines import ROOT, digest, layout, prepare_archives, rust_inputs

# This estimate orders builds. Only rustc and recompilation can authorize a removal.
INLINE = re.compile(rb'#\[inline[^\n]*\n\s*(?:unsafe )?(?:extern "C" )?fn (\w+)')
IDENTIFIER = re.compile(rb"\b[A-Za-z_][A-Za-z0-9_]*\b")


def scan(release):
    groups = defaultdict(list)
    for name, sha in release["source_library_sha256"].items():
        path = Path(name)
        if (path.parts[:2] == ("work", "analysis") and len(path.parts) > 4
                and path.parts[3] == "translations" and path.parts[-3:-1] == ("target", "release")
                and path.suffix == ".a"):
            package = re.sub(r"-[0-9].*$", "", path.parts[2])
            groups[package].append((path, sha))
    ranked = []
    for package, archives in groups.items():
        for archive, sha in archives:
            if str(archive) in release["linked_private_inline_proofs"]:
                continue
            crate, _ = layout(archive)
            estimate = 0
            for source in rust_inputs(ROOT / archive):
                source.relative_to(crate)
                data = (ROOT / source).read_bytes()
                counts = Counter(IDENTIFIER.findall(data))
                estimate += sum(counts[name] == 1 for name in INLINE.findall(data))
            ranked.append({"package": package, "archive": str(archive), "sha256": sha,
                           "estimated_helpers": estimate, "archives_in_package": len(archives)})
    return sorted(ranked, key=lambda row: (-row["estimated_helpers"], row["archive"]))


def prepare(row, logs):
    package, archive = row["package"], Path(row["archive"])
    if digest(ROOT / archive) != row["sha256"]:
        raise ValueError("archive differs from the selected release")
    log = logs / f"{package}.log"
    with log.open("wb") as output:
        result = subprocess.run([sys.executable, "-B", ROOT / "scripts/check_cargo_private_inlines.py",
                                 "--prepare-archive", package, archive], cwd=ROOT,
                                stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f"verifier exited {result.returncode}, see {log}")
    index = json.loads((ROOT / f"work/analysis/{package}-cargo-inline-proofs.json").read_bytes())
    if set(index) != {str(archive)}:
        raise ValueError("index does not match the selected package archive")
    receipt = index[str(archive)]
    path = (ROOT / archive).with_name(receipt["file"])
    if digest(path) != receipt["sha256"] or digest(ROOT / archive) != row["sha256"]:
        raise ValueError("published receipt or archive hash differs")
    proof = json.loads(path.read_bytes())
    if proof["archive_sha256"] != row["sha256"]:
        raise ValueError("receipt does not bind the selected release archive")
    return {"private_helpers": sum(map(len, proof["ranges"].values())), "receipt": receipt}


def release_archives(path):
    """Read the same argparse response file consumed by the Linux linker."""
    archives = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"--([a-z0-9-]+)-rust-library=/work/(work/analysis/[^\s]+)", line)
        if not match:
            raise ValueError(f"invalid release archive argument: {line}")
        option, relative = match.groups()
        archive = Path(relative)
        package = re.sub(r"-[0-9].*$", "", archive.parts[2])
        expected = "procps" if package == "procps-ng" else package
        layout(archive)
        if (option != expected or option in archives or archive.parts[3] != "translations"
                or archive.parents[1].name != "target"):
            raise ValueError(f"inconsistent release archive argument: {line}")
        archives[option] = (package, archive)
    if not archives:
        raise ValueError("empty release archive selection")
    return archives


def prepare_release(entry):
    package, archive = entry
    directory = Path("src/programs") if package == "zstd" else None
    prepare_archives(package, [archive], directory)


def fetch_dependencies(archives):
    crates = [str(layout(path)[0]) for path in archives]
    if crates:
        subprocess.run(["docker", "run", "--rm", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry",
                        "--workdir", "/work", "rustbox-e2fsprogs:2026-11-24", "python3", "-c", """
import subprocess
import sys
import tomllib
from pathlib import Path
for name in sys.argv[1:]:
    crate = Path(name)
    channel = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    subprocess.run(["cargo", "+" + channel, "fetch", "--locked"], cwd=crate, check=True)
""", *crates], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("link_report", type=Path, nargs="?")
    inputs.add_argument("--release-args", type=Path, help="prepare the archives in the linker response file")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--fetch", action="store_true", help="populate the cache from each crate's pinned lockfile")
    action.add_argument("--prepare", action="store_true", help="verify unlinked single-crate candidates")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--package", action="append", help="restrict to the named package (repeatable)")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.release_args:
        if args.prepare or args.package:
            parser.error("release preparation always uses the complete response file")
        entries = release_archives(args.release_args).values()
        if args.fetch:
            fetch_dependencies(archive for _, archive in entries)
        else:
            with ThreadPoolExecutor(max_workers=args.jobs) as workers:
                list(workers.map(prepare_release, entries))
        return 0
    report_bytes = args.link_report.read_bytes()
    ranked = scan(json.loads(report_bytes))
    if args.package:
        unknown = set(args.package) - {row["package"] for row in ranked}
        if unknown:
            parser.error(f"no unlinked translation archive for {sorted(unknown)}")
        ranked = [row for row in ranked if row["package"] in args.package]
    if not args.prepare and not args.fetch:
        print(json.dumps(ranked, indent=2))
        return 0
    # Multi-crate package indexes must be published together by their package verifier.
    candidates = [row for row in ranked if row["archives_in_package"] == 1 and row["estimated_helpers"]]
    if not candidates:
        print("No single-crate archives with estimated candidates in this selection.")
        return 0
    if args.fetch:
        fetch_dependencies(Path(row["archive"]) for row in candidates)
        return 0
    logs = Path(tempfile.mkdtemp(prefix="cargo-inline-batch-", dir=ROOT / "work/analysis"))
    print(f"{len(candidates)} independent archive checks, logs in {logs}", flush=True)
    results = {"link_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
               "packages": {row["package"]: {"archive": row["archive"], "sha256": row["sha256"],
                                              "status": "pending"} for row in candidates}}
    pending = logs / "results.tmp"
    def save():
        pending.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        pending.replace(logs / "results.json")
    save()
    failed = False
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        tasks = {workers.submit(prepare, row, logs): row for row in candidates}
        for task in as_completed(tasks):
            row = tasks[task]
            result = results["packages"][row["package"]]
            try:
                receipt = task.result()
            except (OSError, ValueError, KeyError) as error:
                print(f"{row['package']} failed: {error}", flush=True)
                result.update(status="failed", error=str(error))
                failed = True
            else:
                result.update(status="verified", **receipt)
                print(f"{row['package']} verified: {receipt['private_helpers']} private helpers", flush=True)
            save()
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
