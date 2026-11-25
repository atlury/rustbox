#!/usr/bin/env python3
"""The candidate queue and release build share only intended archives and never mix package indexes."""
# SPDX-License-Identifier: 0BSD
import argparse
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import batch_cargo_private_inlines as batch
from test_inline_release import changed_packages

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    release = {"source_library_sha256": {}, "linked_private_inline_proofs": {}}
    def fixture(pkg, name, calls):
        crate = Path(f"work/analysis/{pkg}/translations/compiler/{name}")
        archive = crate / f"target/release/lib{name}.a"
        output = root / archive
        output.parent.mkdir(parents=True)
        output.write_bytes(name.encode())
        source = crate / "lib.rs"
        (root / source).write_text("#[inline]\nunsafe fn example() {}\n" + calls)
        output.with_suffix(".d").write_text(f"lib: /work/{source}\n")
        release["source_library_sha256"][str(archive)] = batch.digest(output)
        return archive

    old = fixture("example-1.0", "old", "")
    current = fixture("example-2.0", "current", "")
    singular = fixture("procps-ng-1.0", "one", "fn live() { example() }")
    release["linked_private_inline_proofs"][str(old)] = {}
    updated = dict(release, linked_private_inline_proofs=dict(
        release["linked_private_inline_proofs"], **{str(current): {"file": "new"}, str(singular): {"file": "new"}}))
    assert changed_packages(release, updated) == ["example", "procps-ng"]
    assert changed_packages(updated, updated) == []
    try:
        changed_packages(release, dict(updated, binary={"sha256": "different"}))
    except ValueError as error:
        assert "binary" in str(error)
    else:
        raise AssertionError("regression runner accepted a changed release executable")
    args = root / "args"
    line = f"--procps-rust-library=/work/{singular}\n"
    args.write_text(line)
    assert batch.release_archives(args) == {"procps": ("procps-ng", singular)}
    parser = argparse.ArgumentParser(fromfile_prefix_chars="@")
    parser.add_argument("--procps-rust-library", type=Path)
    assert parser.parse_args([f"@{args}"]).procps_rust_library == Path("/work") / singular
    for invalid in (line + line, line.replace("--procps-", "--shadow-"), line.replace("/target/", "/../target/"), ""):
        args.write_text(invalid)
        try:
            batch.release_archives(args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted malformed release selection {invalid!r}")

    with patch.object(batch, "ROOT", root):
        first, second = batch.scan(release)
        assert first["archive"] == str(current) and first["archives_in_package"] == 2
        assert first["estimated_helpers"] == 1
        assert second["archive"] == str(singular) and second["estimated_helpers"] == 0
        (root / singular).write_bytes(b"different")
        with patch.object(batch.subprocess, "run") as run:
            try:
                batch.prepare(second, root)
            except ValueError as error:
                assert "differs from the selected release" in str(error)
            else:
                raise AssertionError("the queue accepted a stale archive")
            run.assert_not_called()

    report = root / "link.json"
    report.write_text(json.dumps(release))
    good = dict(second, package="good", estimated_helpers=1)
    bad = dict(second, package="bad", estimated_helpers=1)
    def run_package(row, logs):
        if row["package"] == "bad":
            raise ValueError("control build differed")
        return {"private_helpers": 3, "receipt": {"sha256": "verified"}}
    with patch.object(batch, "ROOT", root), patch.object(batch, "scan", return_value=[bad, first, good]), \
         patch.object(batch, "prepare", side_effect=run_package), \
         patch.object(sys, "argv", ["batch", str(report), "--prepare", "--jobs", "2"]):
        assert batch.main() == 1
        result_file, = (root / "work/analysis").glob("cargo-inline-batch-*/results.json")
        statuses = json.loads(result_file.read_bytes())["packages"]
        assert set(statuses) == {"good", "bad"}
        assert statuses["good"]["private_helpers"] == 3 and statuses["good"]["status"] == "verified"
        assert statuses["bad"]["status"] == "failed"
print("Ranking, package isolation, release argument parsing and stale-input rejection passed.")
