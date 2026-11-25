#!/usr/bin/env python3
"""Compare qualified IPRoute2 archive substitutions in both dispatch modes of the complete Linux executable."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import sys

from build_routing_protocol_batch import expected_profiles
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import IPROUTE2_PROGRAMS, namespace_iproute2_programs
from preview_cargo_multicall import preview_link


def commands(elf, stage):
    driver = ROOT / "tests/iproute2-multicall-differential.py"
    suite = runpy.run_path(str(driver))
    aliases = suite["ALIASES"]
    invoke = suite["invoke"]
    routel = ROOT / "work/upstream/iproute2-7.3.0/ip/routel"
    directory = stage / "applets"
    directory.mkdir()
    names = [*IPROUTE2_PROGRAMS, *aliases, "routel"]
    for name in names:
        (directory / name).symlink_to(elf)
    cases = [(name, (flag,)) for name in names if name != "routel" for flag in suite["OPTIONS"]]
    cases.extend(("routel", args) for _, args in suite["ROUTEL_CASES"])
    filters = ["kernel", "static", "bgp", "255", "256", "unknown"]
    cases.extend(("ip", ("-4", "route", "show", "protocol", value)) for value in filters)
    reports = {}
    for cc in ("gcc", "clang-18"):
        canonical = Path("/rustbox-iproute2/programs-" + cc)
        env = dict(os.environ, TZ="UTC", PATH=str(canonical) + os.pathsep + os.environ["PATH"])
        observations = []
        for name, args in cases:
            locale = "C.UTF-8" if name == "routel" else "C"
            env.update(LANG=locale, LC_ALL=locale)
            expected = (invoke([sys.executable, str(routel), *args], env) if name == "routel"
                        else invoke([name, *args], env, canonical / aliases.get(name, name)))
            candidate_env = dict(env, PATH=str(directory))
            for mode, result in (("symlink", invoke([name, *args], candidate_env, directory / name)),
                                 ("subcommand", invoke([str(elf), name, *args], candidate_env))):
                if result != expected:
                    raise ValueError((cc, mode, name, args, expected, result))
            observations.append([name, args, suite["summarized"](expected)])
        route_status = [row[2]["status"] for row in observations[-len(filters):]]
        if not 0 < route_status.count(0) < len(filters):
            raise ValueError("expected successful and rejected numeric and named route filters")
        reports[cc] = dict(cases_per_mode=len(observations), modes=["symlink", "subcommand"],
                           canonical_observations_sha256=sha256(json.dumps(observations).encode()).hexdigest(),
                           filter_status=route_status,
                           canonical_sha256={name: digest(canonical / name) for name in IPROUTE2_PROGRAMS})
    return dict(public_names=names, canonical=reports, differential_driver_sha256=digest(driver),
                routel_source_sha256=digest(routel))


def dsfield_commands(elf, stage):
    from test_dsfield_names import PROFILES, QUERIES, capture, configure
    checked = commands(elf, stage)
    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not any(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected empty temporary configuration mounts")
    baseline = json.loads((ROOT / "evidence/iproute2-dsfield-pilot.json").read_bytes())
    profiles = []
    for profile in PROFILES:
        configure(profile, local, vendor)
        statuses = []
        for query in QUERIES:
            argv = ["ip", "-4", "route", "show", "tos", query]
            expected = capture(argv, executable="/rustbox-iproute2/programs-gcc/ip")
            clang = capture(argv, executable="/rustbox-iproute2/programs-clang-18/ip")
            alias = capture(argv, executable=stage / "applets/ip")
            explicit = capture([elf, *argv])
            if not expected == clang == alias == explicit:
                raise ValueError(("DS field public route filter differs", profile, query))
            statuses.append(expected[0])
        profiles.append(dict(profile=profile, statuses=statuses))
    if profiles != [dict(profile=p["profile"], statuses=p["public_filter_status"]) for p in baseline["profiles"]]:
        raise ValueError("canonical route filters differ from the qualified ip archive")
    if any(checked["canonical"][cc]["canonical_sha256"]["ip"] != sha for cc, sha in baseline["public_oracle_sha256"].items()):
        raise ValueError("canonical ip binaries differ from the archived DS field pilot")
    return dict(checked, dsfield_profiles=profiles, dsfield_public_comparisons=len(PROFILES) * len(QUERIES) * 4)


def preview(parent, log, batch, output, single, *, dsfield=False):
    parent_bytes = parent.read_bytes()
    release = json.loads(parent_bytes)
    path = batch / ("ip-results.json" if single else "results.json")
    qualified = json.loads(path.read_bytes())
    if dsfield:
        baseline_name = "iproute2-dsfield-pilot.json"
        fields = ("driver_sha256", "canonical_inputs", "memcheck_runs", "oracle_compilers")
    else:
        baseline_name = "iproute2-routing-protocol-pilot.json"
        fields = ("lookup_driver_sha256", "canonical_source_sha256", "memcheck_runs", "oracle_compilers")
    baseline = json.loads((ROOT / "evidence" / baseline_name).read_bytes())
    if qualified["link_report_sha256"] != digest(parent) or qualified["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("routing protocol comparisons belong to a different parent")
    package_inputs = {key: value for key, value in release["source_library_sha256"].items()
                      if Path(key).parts[2] == "iproute2-7.3.0"}
    inputs = {Path(key).name: (key, value) for key, value in package_inputs.items()}
    names = {f"lib{name}_audit.a" for name in IPROUTE2_PROGRAMS}
    if inputs.keys() != names or len(package_inputs) != len(names):
        raise ValueError("unexpected IPRoute2 engine archives")
    selected = qualified["verified"]
    wanted = {inputs["libip_audit.a"][0]} if single else {key for key, _ in inputs.values()}
    if set(selected) != wanted:
        raise ValueError("incomplete selection of verified engines")

    def prepare(which, stage):
        archives, hashes = {}, {}
        for name in IPROUTE2_PROGRAMS:
            key, expected = inputs[f"lib{name}_audit.a"]
            archive = ROOT / key
            if key in selected:
                row = selected[key]
                directory = batch / archive.stem
                compared = json.loads((directory / "comparison.json").read_bytes())
                if (compared != row or row["archive"] != key or row["control_sha256"] != expected
                        or row["control_binary_sha256"] != release["binary"]["sha256"]
                        or any(row[field] != baseline[field] for field in fields)
                        or row["profiles"] != expected_profiles(baseline, name == "ip", dsfield=dsfield)):
                    raise ValueError(f"incomplete archive qualification for {name}")
                if which == "candidate":
                    archive = directory / archive.name
                    expected = row["candidate_sha256"]
            if digest(archive) != expected:
                raise ValueError(f"wrong {name} {which} archive")
            archives[name], hashes[name] = archive, expected
        mapped, symbols = namespace_iproute2_programs(archives, stage)
        if symbols != release["iproute2_namespaced_symbols"]:
            raise ValueError("IPRoute2 public symbol isolation differs from the selected release")
        changed = {mapped[name] for name, archive in archives.items() if inputs[archive.name][0] in selected}
        return list(mapped.values()), changed, {"engine_archive_sha256": hashes}
    preview_link(parent, parent_bytes, log, output, prepare, dsfield_commands if dsfield else commands)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "batch", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--ip-only", action="store_true")
    parser.add_argument("--dsfield", action="store_true", help="qualify DS field readers on the routing protocol parent")
    args = parser.parse_args()
    preview(args.parent, args.log, args.batch, args.output, args.ip_only, dsfield=args.dsfield)
