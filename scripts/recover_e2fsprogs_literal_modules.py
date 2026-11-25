#!/usr/bin/env python3
"""Cold-build E2fsprogs module subsets shared with already byte-identical engines."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path

from build_c_string_literal_pilot import build
from check_cargo_private_inlines import ROOT, digest
from verify_c_string_sources import verify
from recover_shared_stdio import search

PACKAGE = "e2fsprogs-1.47.4"


def canonical_source(module):
    parts = Path(module).with_suffix(".c").parts
    upstream = ROOT / "work/upstream" / PACKAGE
    for offset in range(len(parts) - 1):
        relative = Path(*parts[offset:])
        if (upstream / relative).is_file():
            return str(relative)
    return None


def recover(link, batch, output, engine, *, complement=False, trials=0, seed=None):
    report = json.loads((batch / "results.json").read_bytes())
    if digest(link) != report["link_report_sha256"]:
        raise ValueError("batch and parent link differ")
    # Source names are hints across separately generated crates. Whole-archive
    # equality and the compiler-input replay decide which subset qualifies.
    known = set()
    peers = report["verified"].items()
    if seed is not None:
        verify(link, seed)
        row = json.loads((seed / "pilot.json").read_bytes())
        key = row["archive"]
        if (Path(key).parts[2] != PACKAGE or row["control_sha256"] != row["candidate_sha256"]
                or digest(seed / Path(key).name) != row["candidate_sha256"]):
            raise ValueError("expected a verified byte-identical E2fsprogs seed")
        peers = [(key, row)]
    for key, row in peers:
        if Path(key).parts[2] != PACKAGE:
            continue
        if row["control_sha256"] != row["candidate_sha256"] or digest(ROOT / key) != row["control_sha256"]:
            raise ValueError("peer archive differs from its byte-identity receipt")
        known.update((name, count) for module, count in row["modules"].items() if (name := canonical_source(module)))
    key, = [key for key, reason in report["deferred"].items() if Path(key).parts[2] == PACKAGE
            and Path(key).stem == "lib" + engine + "_audit" and reason == "rebuilt archive bytes differ"]
    folder = batch / (Path(key).stem + "-" + sha256(key.encode()).hexdigest()[:12])
    whole = json.loads((folder / "pilot.json").read_bytes())
    verify(link, folder)
    modules = {m: c for m, c in whole["modules"].items() if (canonical_source(m), c) in known}
    if complement:
        modules = {m: c for m, c in whole["modules"].items() if m not in modules}
    if not modules or len(modules) == len(whole["modules"]):
        raise ValueError("expected a proper nonempty subset with independently tested peers")
    if not output.exists():
        build(link, output, Path(key), modules=sorted(modules))
    row = json.loads((output / "pilot.json").read_bytes())
    if (row["modules"] != modules or any(row[k] != whole[k] for k in
            ("archive", "control_sha256", "control_binary_sha256", "parent_sources_sha256"))):
        raise ValueError("rebuilt subset differs from the requested compiler inputs")
    verify(link, output)
    result = dict(archive=key, whole_candidate_sha256=whole["candidate_sha256"], peer_batch_sha256=digest(batch / "results.json"),
                  selection="complement" if complement else "shared", candidate=row, byte_identical=row["candidate_sha256"] == row["control_sha256"])
    if seed is not None:
        result["seed_receipt_sha256"] = digest(seed / "pilot.json")
    (output / "comparison.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{engine}: {len(modules)} modules, {row['c_string_literals']} literals, byte-identical={result['byte_identical']}",
          flush=True)
    if trials and not result["byte_identical"]:
        def compare(index, chosen):
            trial = output / f"subset-{index:02d}"
            if not trial.exists():
                build(link, trial, Path(key), modules=chosen)
            tested = json.loads((trial / "pilot.json").read_bytes())
            if (tested["modules"] != {m: modules[m] for m in chosen} or any(tested[k] != row[k] for k in
                    ("archive", "control_sha256", "control_binary_sha256", "parent_sources_sha256"))
                    or digest(trial / Path(key).name) != tested["candidate_sha256"]):
                raise ValueError(f"invalid subset build for {trial}")
            equal = tested["control_sha256"] == tested["candidate_sha256"]
            if equal:
                verify(link, trial)
            print(f"{trial.name}: {tested['c_string_literals']} checked literals, byte-identical={equal}", flush=True)
            return equal, tested["candidate_sha256"]
        accepted, trace = search(modules, trials, compare)
        winner = next((f"subset-{i:02d}" for i, t in enumerate(trace, 1)
                       if t["identical"] and t["modules"] == accepted), None)
        report = dict(archive=key, verified_directory=winner, trials=trace, accepted_modules=accepted,
                      raw_pointer_types_removed=2 * sum(modules[m] for m in accepted))
        (output / "subset-results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("link", "batch", "output"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("engine")
    parser.add_argument("--seed", type=Path, help="use the selected modules of one independently verified peer")
    parser.add_argument("--complement", action="store_true", help="test the modules outside the peer selection")
    parser.add_argument("--trials", type=int, default=0, help="maximum extra cold builds if the initial group differs")
    args = parser.parse_args()
    if args.trials < 0:
        parser.error("--trials must be nonnegative")
    recover(args.link, args.batch, args.output.resolve(), args.engine, complement=args.complement, trials=args.trials, seed=args.seed)
