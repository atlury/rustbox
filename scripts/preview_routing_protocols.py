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


def dsfield_commands(elf, stage, checked=None):
    from test_dsfield_names import PROFILES, QUERIES, capture, configure
    if checked is None:
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


def group_commands(elf, stage, *, checked=None):
    from test_group_names import PROFILES, QUERIES, capture, configure
    if checked is None:
        checked = commands(elf, stage)
    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(path) and not any(path.iterdir()) for path in (local, vendor)):
        raise ValueError("device group comparisons require empty private configuration mounts")
    baseline = json.loads((ROOT / "evidence/iproute2-group-names-pilot.json").read_bytes())
    profiles = []
    if list(PROFILES) != [row["profile"] for row in baseline["profiles"]]:
        raise ValueError("device group configuration profiles differ from the ip archive tests")
    for compiler, report in checked["canonical"].items():
        if report["canonical_sha256"]["ip"] != baseline["public_oracle_sha256"][compiler]:
            raise ValueError(f"canonical {compiler} ip differs from the device group pilot")
    for profile, expected_profile in zip(PROFILES, baseline["profiles"]):
        configure(profile, local / "group", vendor / "group")
        statuses = []
        for name in QUERIES:
            argv = ["ip", "link", "show", "group", name]
            expected = capture(argv, executable="/rustbox-iproute2/programs-gcc/ip")
            if (capture(argv, executable="/rustbox-iproute2/programs-clang-18/ip") != expected
                    or capture(argv, executable=stage / "applets/ip") != expected or capture([elf, *argv]) != expected):
                raise ValueError((profile, name, "device group filter differs from canonical ip"))
            statuses.append(expected[0])
        if statuses != expected_profile["public_statuses"]:
            raise ValueError("device group filter coverage differs from the translated ip archive")
        profiles.append(dict(profile=profile, statuses=statuses))
    return dict(checked, group_profiles=profiles, group_public_comparisons=4 * len(PROFILES) * len(QUERIES))


def qualified_engines(release, selected, wanted_names, resolve):
    """Map exactly the named engine replacements into both complete link commands."""
    package_inputs = {key: value for key, value in release["source_library_sha256"].items()
                      if Path(key).parts[2] == "iproute2-7.3.0"}
    inputs = {Path(key).name: (key, value) for key, value in package_inputs.items()}
    names = {f"lib{name}_audit.a" for name in IPROUTE2_PROGRAMS}
    if inputs.keys() != names or len(package_inputs) != len(names):
        raise ValueError("unexpected IPRoute2 engine archives")
    if set(selected) != {inputs[f"lib{name}_audit.a"][0] for name in wanted_names}:
        raise ValueError("incomplete selection of verified engines")

    def prepare(which, stage):
        archives, hashes = {}, {}
        for name in IPROUTE2_PROGRAMS:
            key, expected = inputs[f"lib{name}_audit.a"]
            archive = ROOT / key
            if key in selected:
                candidate, candidate_sha = resolve(name, key, expected)
                if which == "candidate":
                    archive, expected = candidate, candidate_sha
            if digest(archive) != expected:
                raise ValueError(f"wrong {name} {which} archive")
            archives[name], hashes[name] = archive, expected
        mapped, symbols = namespace_iproute2_programs(archives, stage)
        if symbols != release["iproute2_namespaced_symbols"]:
            raise ValueError("IPRoute2 public symbol isolation differs from the selected release")
        changed = {mapped[name] for name, archive in archives.items() if inputs[archive.name][0] in selected}
        return list(mapped.values()), changed, {"engine_archive_sha256": hashes}
    return prepare


def check_table_replay(ranking, qualified, release, link_sha):
    if ranking["link_report_sha256"] != link_sha or ranking["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("name-table source replay belongs to a different release")
    rows = qualified["verified"]
    if set(ranking["engines"]) != set(rows) or len(rows) != len(IPROUTE2_PROGRAMS):
        raise ValueError("name-table source replay must cover every qualified engine")
    fields = ("candidate_module_sha256", "candidate_sources_sha256", "canonical_sha256",
              "compiler_selected_sources", "control_module_sha256", "helper_sha256", "module",
              "parent_sources_sha256", "raw_pointer_types_removed")
    total = 0
    for key, ranked in ranking["engines"].items():
        row = rows[key]
        if (row["archive"] != key or row["control_binary_sha256"] != qualified["binary_sha256"]
                or ranked["control_archive_sha256"] != row["control_sha256"]
                or release["source_library_sha256"].get(key) != row["control_sha256"]
                or any(ranked[field] != row[field] for field in fields)):
            raise ValueError(f"current name-table compiler inputs differ for {key}")
        total += ranked["raw_pointer_types_removed"]
    if total != ranking["candidate_pointer_types"] or total != qualified["raw_pointer_types_removed"]:
        raise ValueError("name-table pointer reduction differs from the per-engine receipts")
    return total


def check_dsfield_replay(ranking, qualified, release, link_sha):
    return check_table_replay(ranking, qualified, release, link_sha)


def preview(parent, log, batch, output, single, *, dsfield=False, group_names=False, source_replay=None):
    parent_bytes = parent.read_bytes()
    release = json.loads(parent_bytes)
    path = batch / ("ip-results.json" if single else "results.json")
    qualified = json.loads(path.read_bytes())
    if group_names:
        baseline_name = "iproute2-group-names-pilot.json"
        fields = ("driver_sha256", "canonical_sha256", "helper_sha256", "memcheck_runs", "oracle_compilers")
    elif dsfield:
        baseline_name = "iproute2-dsfield-pilot.json"
        fields = ("driver_sha256", "canonical_inputs", "memcheck_runs", "oracle_compilers")
    else:
        baseline_name = "iproute2-routing-protocol-pilot.json"
        fields = ("lookup_driver_sha256", "canonical_source_sha256", "memcheck_runs", "oracle_compilers")
    baseline = json.loads((ROOT / "evidence" / baseline_name).read_bytes())
    reuse = {}
    if source_replay is not None:
        if single or not (dsfield or group_names):
            raise ValueError("source replay requires a complete qualified name-table batch")
        historic = ROOT / "evidence" / ("iproute2-group-names-archives.json" if group_names else "iproute2-dsfield-archives.json")
        if qualified != json.loads(historic.read_bytes()):
            raise ValueError("original qualification differs from the published engine comparisons")
        source_bytes = source_replay.read_bytes()
        total = check_table_replay(json.loads(source_bytes), qualified, release, sha256(parent_bytes).hexdigest())
        reuse = dict(source_replay_sha256=sha256(source_bytes).hexdigest(), qualified_batch_sha256=digest(historic),
                     archive_qualification_link_sha256=qualified["link_report_sha256"], raw_pointer_types_removed=total)
    elif qualified["link_report_sha256"] != digest(parent) or qualified["binary_sha256"] != release["binary"]["sha256"]:
        raise ValueError("routing protocol comparisons belong to a different parent")
    selected = qualified["verified"]

    def resolve(name, key, expected):
        row = selected[key]
        directory = batch / Path(key).stem
        compared = json.loads((directory / "comparison.json").read_bytes())
        if (compared != row or row["archive"] != key or row["control_sha256"] != expected
                or row["control_binary_sha256"] != qualified["binary_sha256"]
                or any(row[field] != baseline[field] for field in fields)
                or row["profiles"] != expected_profiles(baseline, name == "ip", dsfield=dsfield, group_names=group_names)):
            raise ValueError(f"incomplete archive qualification for {name}")
        return directory / Path(key).name, row["candidate_sha256"]

    prepare = qualified_engines(release, selected, ["ip"] if single else IPROUTE2_PROGRAMS, resolve)
    def exercise(elf, stage):
        if group_names:
            observations = group_commands(elf, stage)
        else:
            observations = dsfield_commands(elf, stage) if dsfield else commands(elf, stage)
        return {**observations, **reuse}
    preview_link(parent, parent_bytes, log, output, prepare, exercise)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent", "log", "batch", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--ip-only", action="store_true")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--group-names", action="store_true", help="compare canonical device group filters in the complete executable")
    choice.add_argument("--dsfield", action="store_true", help="qualify DS field readers on the routing protocol parent")
    parser.add_argument("--source-replay", type=Path, help="current name-table compiler inputs for a previously qualified batch")
    args = parser.parse_args()
    preview(args.parent, args.log, args.batch, args.output, args.ip_only, dsfield=args.dsfield, group_names=args.group_names, source_replay=args.source_replay)
