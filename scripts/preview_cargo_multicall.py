"""Relink one qualified Cargo archive in isolation against the saved complete Linux link command."""
# SPDX-License-Identifier: GPL-3.0-or-later
from hashlib import sha256
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest

COMMAND_SHA = "411fb9679311197f0273b170625142d2fa40e9016b74ba6255e2c4fe02f7183e"


def qualified_inputs(release, pilot, qualified, namespace):
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = Path(row["archive"])
    if (any(qualified.get(k) != value for k, value in row.items())
            or release["source_library_sha256"].get(str(key)) != row["control_sha256"]):
        raise ValueError("expected a qualified archive for the selected parent")
    residue_dir = Path(*key.parts[:3]) / "hybrid-artifacts/c-residue"
    inputs = release["source_library_sha256"]
    residues = sorted(ROOT / name for name in inputs if Path(name).parent == residue_dir and Path(name).suffix == ".o")
    if set(residues) != set((ROOT / residue_dir).glob("*.o")) or any(
        inputs[str(p.relative_to(ROOT))] != digest(p) for p in residues
    ):
        raise ValueError("package C linkage inputs differ from the specified parent")

    def prepare(name, stage):
        is_parent = name == "parent"
        path = ROOT / key if is_parent else pilot / key.name
        expected = row["control_sha256" if is_parent else "candidate_sha256"]
        if digest(path) != expected:
            raise ValueError(f"unexpected {name} archive")
        archive, objs = namespace(path, residues, release, stage)
        return [archive, *objs], {archive}, {"archive_sha256": expected}

    return prepare


def preview(parent, log, pilot, output, qualified, namespace, exercise):
    parent_bytes = parent.read_bytes()
    prepare = qualified_inputs(json.loads(parent_bytes), pilot, qualified, namespace)
    preview_link(parent, parent_bytes, log, output, prepare, exercise)


def preview_link(parent, parent_bytes, log, output, prepare, exercise, *, direct_archives=()):
    """Replay the full linker command with explicitly selected inputs and compare the complete control ELF."""
    release = json.loads(parent_bytes)
    if output.exists():
        raise ValueError("expected a new multicall comparison directory")
    raw = [shlex.split(s) for s in log.read_text().splitlines() if s.startswith("clang-18 -DSINGLE_BINARY")]
    if len(raw) != 1 or sha256(json.dumps(raw[0], separators=(",", ":")).encode()).hexdigest() != COMMAND_SHA:
        raise ValueError("unrecognized final Linux link command")
    build = Path("/rustbox-coreutils/canonical-clang-no-security-compdb")
    if digest(build / "src/rustbox") != release["binary"]["sha256"]:
        raise ValueError("installed ELF differs from the specified parent")
    checks = {}
    with TemporaryDirectory() as scratch, TemporaryDirectory(dir=output.parent) as workspace:
        result = Path(workspace) / "result"
        result.mkdir()
        for name in ("parent", "candidate"):
            stage = Path(scratch) / name
            objects, changed, metadata = prepare(name, stage)
            if not changed or not changed <= set(objects) or len(objects) != len(set(objects)):
                raise ValueError("expected distinct linker inputs and candidate archives")
            cmd = [str(build / "lib/.rustbox-libcoreutils.a") if x == "lib/libcoreutils.a" else x for x in raw[0]]
            for obj in objects:
                relative = obj.relative_to(stage)
                old = (ROOT if relative in direct_archives else build) / relative
                if cmd.count(str(old)) != 1 or ((name == "parent" or obj not in changed) and digest(obj) != digest(old)):
                    raise ValueError(f"unexpected previous linker input {obj.name}")
                cmd[cmd.index(str(old))] = str(obj)
            elf = stage / "rustbox"
            cmd[cmd.index("-o") + 1] = str(elf)
            cmd[cmd.index("-Wl,-Map=src/rustbox.map")] = "-Wl,-Map=" + str(stage / "link.map")
            subprocess.run(cmd, cwd=build, check=True)
            if name == "parent" and digest(elf) != release["binary"]["sha256"]:
                raise ValueError("isolated control did not reproduce the entire linked executable")
            stripped = stage / "stripped"
            subprocess.run(["strip", "--strip-all", "-o", stripped, elf], check=True)
            checks[name] = dict(bytes=elf.stat().st_size, sha256=digest(elf), stripped_bytes=stripped.stat().st_size,
                                stripped_sha256=digest(stripped), **metadata)
            if name == "candidate":
                checks.update(exercise(elf, stage))
                shutil.copy2(elf, result / "rustbox")
        if parent.read_bytes() != parent_bytes:
            raise ValueError("source release changed during the comparison")
        checks.update(parent_link_report_sha256=sha256(parent_bytes).hexdigest(), linker_command_sha256=COMMAND_SHA)
        (result / "comparison.json").write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
        result.rename(output)
