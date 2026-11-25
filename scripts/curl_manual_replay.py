"""Bind a completed curl multicall comparison to its ELF, oracle binaries, Docker image and driver."""
# SPDX-License-Identifier: curl
import json

from check_cargo_private_inlines import ROOT, digest
from curl_manual_archive import KEY, candidate_path, parent_view, pinned


def identity(release, image_id):
    record = pinned()
    parent_view(release)
    row = record["pilot"]
    base = "work/analysis/curl-8.23.0"
    candidate = str(candidate_path(row))
    paths = ["scripts/test_curl_manual_pilot.py", "scripts/check_cargo_private_inlines.py",
             "scripts/curl_manual_archive.py", "bridges/curl_main.c", "batches/curl-manual.json",
             "evidence/curl-manual-pilot.json", "evidence/curl-8.23.0-oracle.json",
             f"{base}/hybrid-artifacts/c-residue/mprintf.o", f"{base}/oracle/curl-gcc", f"{base}/oracle/curl-clang",
             KEY, candidate]
    hashes = {name: digest(ROOT / name) for name in paths}
    oracles = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
    if (hashes[candidate] != row["candidate_sha256"] or hashes[KEY] != row["control_sha256"]
            or any(hashes[f"{base}/oracle/curl-{cc}"] != oracles[cc]["sha256"] for cc in ("gcc", "clang"))):
        raise ValueError("curl archives or canonical executables changed")
    return dict(binary_sha256=release["binary"]["sha256"], docker_image=image_id, network="none",
                environment={"LC_ALL": "C", "TZ": "UTC"}, inputs=hashes)


def lookup(release, image_id, path):
    if not path.is_file():
        return None
    receipt = json.loads(path.read_bytes())
    if receipt["identity"]["binary_sha256"] != release["binary"]["sha256"] or receipt["identity"] != identity(release, image_id):
        return None
    pilot = json.loads((ROOT / "evidence/curl-manual-pilot.json").read_bytes())
    if receipt["comparison"] != dict(pilot, multicall_sha256=release["binary"]["sha256"]):
        raise ValueError("saved curl comparison differs from the qualified cases")
    return receipt["comparison"]
