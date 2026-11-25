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


def preview(parent, log, pilot, output, qualified, namespace, exercise):
    release = json.loads(parent.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = Path(row["archive"])
    if (any(qualified.get(k) != value for k, value in row.items())
            or release["source_library_sha256"].get(str(key)) != row["control_sha256"]
            or output.exists()):
        raise ValueError("expected a fresh destination and qualified archive for the selected parent")
    raw = [shlex.split(s) for s in log.read_text().splitlines() if s.startswith("clang-18 -DSINGLE_BINARY")]
    if len(raw) != 1 or sha256(json.dumps(raw[0], separators=(",", ":")).encode()).hexdigest() != COMMAND_SHA:
        raise ValueError("unrecognized final Linux link command")
    build = Path("/rustbox-coreutils/canonical-clang-no-security-compdb")
    if digest(build / "src/rustbox") != release["binary"]["sha256"]:
        raise ValueError("installed ELF differs from the specified parent")
    residues = sorted((ROOT.joinpath(*key.parts[:3]) / "hybrid-artifacts/c-residue").glob("*.o"))
    if len(residues) != 4 or any(release["source_library_sha256"][str(p.relative_to(ROOT))] != digest(p) for p in residues):
        raise ValueError("package C linkage inputs differ from the specified parent")
    checks = {}
    with TemporaryDirectory() as scratch, TemporaryDirectory(dir=output.parent) as workspace:
        result = Path(workspace) / "result"
        result.mkdir()
        for name, path in (("parent", ROOT / key), ("candidate", pilot / key.name)):
            expected = row["control_sha256" if name == "parent" else "candidate_sha256"]
            if digest(path) != expected:
                raise ValueError(f"unexpected {name} archive")
            stage = Path(scratch) / name
            archive, objs = namespace(path, residues, release, stage)
            cmd = [str(build / "lib/.rustbox-libcoreutils.a") if x == "lib/libcoreutils.a" else x for x in raw[0]]
            for obj in [archive, *objs]:
                old = build / obj.relative_to(stage)
                if cmd.count(str(old)) != 1 or ((name == "parent" or obj != archive) and digest(obj) != digest(old)):
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
                                stripped_sha256=digest(stripped), archive_sha256=expected)
            if name == "candidate":
                checks.update(exercise(elf, stage))
                shutil.copy2(elf, result / "rustbox")
        checks.update(parent_link_report_sha256=digest(parent), linker_command_sha256=COMMAND_SHA)
        (result / "comparison.json").write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
        result.rename(output)
