#!/usr/bin/env python3
"""Create deterministic multicall-entrypoint normalization for Procps-ng."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ENTRYPOINTS = {
    "src/free.c": ("int main(int argc, char **argv)", "rustbox_procps_free_main"),
    "src/hugetop.c": ("int main(int argc, char **argv)", "rustbox_procps_hugetop_main"),
    "src/kill.c": ("int main(int argc, char **argv)", "rustbox_procps_kill_main"),
    "src/pgrep.c": ("int main (int argc, char **argv)", "rustbox_procps_pgrep_main"),
    "src/pidof.c": ("int main (int argc, char **argv)", "rustbox_procps_pidof_main"),
    "src/pmap.c": ("int main(int argc, char **argv)", "rustbox_procps_pmap_main"),
    "src/ps/display.c": ("int main(int argc, char *argv[])", "rustbox_procps_ps_main"),
    "src/pwdx.c": ("int main(int argc, char *argv[])", "rustbox_procps_pwdx_main"),
    "src/skill.c": ("int main(int argc, char ** argv)", "rustbox_procps_skill_main"),
    "src/slabtop.c": ("int main(int argc, char *argv[])", "rustbox_procps_slabtop_main"),
    "src/sysctl.c": ("int main(int argc, char *argv[])", "rustbox_procps_sysctl_main"),
    "src/tload.c": ("int main(int argc, char **argv)", "rustbox_procps_tload_main"),
    "src/top/top.c": ("int main (int argc, char *argv[]) {", "rustbox_procps_top_main"),
    "src/uptime.c": ("int main(int argc, char **argv)", "rustbox_procps_uptime_main"),
    "src/vmstat.c": ("int main(int argc, char *argv[])", "rustbox_procps_vmstat_main"),
    "src/w.c": ("int main(int argc, char **argv)", "rustbox_procps_w_main"),
    "src/watch.c": ("int main(int argc, char *argv[])", "rustbox_procps_watch_main"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.repository.resolve()
    canonical = root / "work/upstream/procps-ng-4.0.7"
    state = json.loads((root / "work/upstream/.state/procps-ng.json").read_text())
    release = json.loads((root / "upstream/releases.json").read_text())["releases"]["procps-ng"]
    if not state.get("signature_verified") or state.get("sha256") != release["sha256"]:
        raise RuntimeError("canonical Procps source is not signature-verified")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(canonical, output, symlinks=True)

    transformations = []
    for relative, (signature, exported) in ENTRYPOINTS.items():
        source = output / relative
        text = source.read_text()
        if text.count(signature) != 1 or exported in text:
            raise RuntimeError(f"Procps entrypoint signature changed: {relative}")
        replacement = signature.replace("main", exported, 1)
        wrapper = (
            "\n#ifndef RUSTBOX_MULTICALL\n"
            f"int main(int argc, char **argv)\n{{\n\treturn {exported}(argc, argv);\n}}\n"
            "#endif\n"
        )
        before = sha256(source)
        source.write_text(text.replace(signature, replacement, 1) + wrapper)
        transformations.append({
            "path": relative,
            "entrypoint": exported,
            "before_sha256": before,
            "after_sha256": sha256(source),
            "kind": "export entrypoint and retain standalone wrapper",
        })

    manifest = {
        "schema": 1,
        "release": "4.0.7",
        "canonical_sha256": release["sha256"],
        "entrypoint_engines": len(ENTRYPOINTS),
        "public_programs": 20,
        "shared_dispatch": {
            "rustbox_procps_pgrep_main": ["pgrep", "pkill", "pidwait"],
            "rustbox_procps_skill_main": ["skill", "snice"],
        },
        "transformations": transformations,
    }
    manifest_path = output / "rustbox-normalization.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"entrypoints": len(ENTRYPOINTS), "programs": 20}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
