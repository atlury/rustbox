"""Check address-protocol C interfaces and build the canonical comparison driver for every candidate archive."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from check_cargo_private_inlines import IPROUTE2_CARGO_ENGINES, digest
from iproute2_address_protocol_archive import BRIDGE, RECEIPTS, candidate_path, comparison_inputs, control_view

release = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
link = control_view(release)
batch = None if sys.argv[1] == "--linked" else Path(sys.argv[1])
records = (release["iproute2_address_protocol_copies"] if batch is None else json.loads((batch / "archives.json").read_bytes()))
engines = (set(IPROUTE2_CARGO_ENGINES) | {"bridge"}) - {"ip"}
if len(records) != len(engines):
    raise ValueError("address-protocol batch must cover every remaining identical module")


def exports(archive):
    rows = subprocess.check_output(["nm", "-g", "--defined-only", archive], stderr=subprocess.DEVNULL, text=True)
    return {fields[-1] for line in rows.splitlines() if len(fields := line.split()) >= 3
            and not fields[-1].startswith(("_ZN", "_R")) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", fields[-1])}


variants = []
for name in sorted(engines):
    key = f"work/analysis/iproute2-7.3.0/program-translations/cargo-target/{name}/release/lib{name}_audit.a"
    if name == "bridge":
        key = str(BRIDGE)
    record = records[key]
    candidate = Path("/work") / candidate_path(record) if batch is None else batch / name / Path(key).name
    parent = Path("/work") / key
    expected_receipts = {key_type: link[key_type][key] for key_type in RECEIPTS if key in link.get(key_type, {})}
    if (record["archive"] != key or record["parent_receipts"] != expected_receipts
            or record["control_sha256"] != link["source_library_sha256"][key]
            or record["control_sha256"] != digest(parent) or digest(candidate) != record["candidate_sha256"]
            or exports(parent) != exports(candidate)):
        raise ValueError(f"unexpected {name} archive provenance or C exports")
    for label, archive in ((name + "-parent", parent), (name + "-candidate", candidate)):
        subprocess.run(["gcc", "-Wl,--gc-sections", "compare.o", archive, "-ltirpc", "-lbpf", "-lelf",
                        "-lmnl", "-lcap", "-ldb", "-lxtables", "-lz", "-ldl", "-lm", "-lpthread", "-o", label], check=True)
        variants.append(label)
    variants.append(name + "-candidate-memcheck")
Path("/tmp/addrprot-batch.json").write_text(json.dumps({
    "archive_sha256": {k: r["candidate_sha256"] for k, r in records.items()},
    "control_sha256": {k: r["control_sha256"] for k, r in records.items()},
    "test_input_sha256": comparison_inputs(), "image_id": os.environ["RUSTBOX_ADDRPROT_IMAGE"],
}))
print(" ".join(variants))
