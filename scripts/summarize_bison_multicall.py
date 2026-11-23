#!/usr/bin/env python3
"""Summarize and pin GNU Bison's embedded multicall verification."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/bison-3.8.2"
MULTICALL = ANALYSIS / "multicall"
EXCLUDED_LANGUAGE_GROUPS = {
    47, 53, 58, 63, 213, 465, 466, 467, 468,
    *range(571, 604),
    651,
    *range(692, 705),
}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "evidence/bison-3.8.2-multicall.json",
    )
    args = parser.parse_args()

    differential = load(MULTICALL / "differential.json")
    yacc = load(MULTICALL / "yacc-frontend.json")
    size = load(MULTICALL / "size.json")
    resources = load(ANALYSIS / "embedded/manifest.json")
    link = load(ROOT / "work/analysis/rustbox-multicall-link.json")
    full_log = (MULTICALL / "upstream-tests.log").read_text(errors="replace")
    targeted_log = (MULTICALL / "upstream-tests-targeted.log").read_text(
        errors="replace"
    )
    valgrind = (MULTICALL / "valgrind-help.log").read_text(errors="replace")
    datadir = (MULTICALL / "print-datadir.txt").read_text().strip()

    if (
        differential.get("cases") != 12
        or differential.get("passed") != 12
        or differential.get("compiled_parsers") != 5
        or differential.get("right_embedded") is not True
        or differential.get("resource_directories_leaked") != 0
    ):
        raise RuntimeError("embedded Bison differential evidence changed")
    if (
        yacc.get("passed") is not True
        or yacc.get("hybrid_embedded") is not True
        or yacc.get("resource_directories_leaked") != 0
        or yacc.get("compile_status") != 0
        or yacc.get("runtime_status") != 0
    ):
        raise RuntimeError("embedded yacc evidence changed")
    if resources.get("resources_count") != 22 or resources.get("resources_bytes") != 679009:
        raise RuntimeError("embedded Bison resource closure changed")
    resource_names = {item["name"] for item in resources["resources"]}
    required_reports = {
        "bison-default.css", "xslt/bison.xsl", "xslt/xml2dot.xsl",
        "xslt/xml2text.xsl", "xslt/xml2xhtml.xsl",
    }
    if not required_reports <= resource_names:
        raise RuntimeError("embedded Bison report resources are incomplete")
    if (
        link.get("bison_public_names") != 2
        or link.get("total_dispatch_names") != 358
        or len(link.get("bison_namespaced_symbols", [])) != 1063
    ):
        raise RuntimeError("Bison multicall link surface changed")
    if datadir.find(str(resources["persistent_resource_tag"])) < 0:
        raise RuntimeError("Bison print-datadir is not content addressed")
    if not datadir.startswith("/tmp/rustbox-bison-3.8.2-"):
        raise RuntimeError("Bison print-datadir location changed")

    failed = {
        int(match.group(1))
        for match in re.finditer(r"^\s*(\d+): .*FAILED", full_log, re.MULTILINE)
    }
    if failed != EXCLUDED_LANGUAGE_GROUPS | {2}:
        raise RuntimeError(f"Bison full-suite failure inventory changed: {sorted(failed)}")
    for marker in (
        "ERROR: 763 tests were run", "57 failed unexpectedly",
        "13 tests were skipped",
    ):
        if marker not in full_log:
            raise RuntimeError(f"Bison full-suite marker is missing: {marker}")
    if (
        "2: Invalid number of arguments" not in targeted_log
        or "1 test was successful" not in targeted_log
        or "FAILED" in targeted_log
    ):
        raise RuntimeError("Bison targeted diagnostic recheck did not pass")
    for marker in (
        "ERROR SUMMARY: 0 errors",
        "definitely lost: 0 bytes in 0 blocks",
        "indirectly lost: 0 bytes in 0 blocks",
        "possibly lost: 0 bytes in 0 blocks",
    ):
        if marker not in valgrind:
            raise RuntimeError(f"Bison Valgrind marker is missing: {marker}")

    evidence = {
        "schema": 1,
        "release": "3.8.2",
        "recorded_at": "2026-11-23",
        "scope": {
            "public_names": ["bison", "yacc"],
            "languages": ["C", "C++"],
            "excluded_languages": ["D", "Java"],
            "optional_html_reporter": "external xsltproc is not bundled",
        },
        "multicall": {
            "total_public_names": link["total_dispatch_names"],
            "bison_public_names": link["bison_public_names"],
            "bison_namespaced_symbols": len(link["bison_namespaced_symbols"]),
            "binary": link["binary"],
            "stripped_binary": size,
        },
        "resources": {
            "count": resources["resources_count"],
            "bytes": resources["resources_bytes"],
            "persistent_resource_tag": resources["persistent_resource_tag"],
            "m4_route": resources["m4_route"],
            "external_datadir_required": False,
            "temporary_directories_leaked": 0,
        },
        "differential": {
            "cases": differential["cases"],
            "passed": differential["passed"],
            "compiled_parsers": differential["compiled_parsers"],
        },
        "yacc": {
            "passed": yacc["passed"],
            "compile_status": yacc["compile_status"],
            "runtime_status": yacc["runtime_status"],
        },
        "upstream_suite": {
            "total_groups": 776,
            "full_sweep_passed_before_targeted_fix": 706,
            "environmental_skips": 13,
            "excluded_language_groups": sorted(EXCLUDED_LANGUAGE_GROUPS),
            "excluded_language_groups_count": len(EXCLUDED_LANGUAGE_GROUPS),
            "initial_in_scope_failure": 2,
            "targeted_final_recheck_passed": True,
            "final_in_scope_passed": 707,
            "final_in_scope_skipped": 13,
        },
        "valgrind": {
            "paths": ["help"],
            "errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": evidence["differential"]["passed"],
        "in_scope_upstream": evidence["upstream_suite"]["final_in_scope_passed"],
        "public_names": evidence["multicall"]["bison_public_names"],
        "stripped_bytes": evidence["multicall"]["stripped_binary"]["bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
