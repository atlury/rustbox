#!/usr/bin/env python3
"""Create deterministic multicall-entrypoint normalization for Procps-ng."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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

STATUS_ACTIONS = (
    "VmHWM", "Threads", "VmRSS", "VmSwap", "Tgid", "VmStk", "VmSize",
    "Gid", "VmPTE", "VmPeak", "ShdPnd", "Pid", "PPid", "VmLib",
    "SigPnd", "VmLck", "SigCgt", "State", "CapPrm", "Uid", "SigIgn",
    "SigQ", "RssShmem", "Name", "CapInh", "VmData", "FDSize", "SigBlk",
    "CapEff", "CapBnd", "VmExe", "Groups", "RssAnon", "RssFile",
)

STATUS_TABLE_ORIGINAL = """typedef struct status_table_struct {
    unsigned char name[8];        // /proc/*/status field name
    unsigned char len;            // name length
#ifdef LABEL_OFFSET
    long offset;                  // jump address offset
#else
    void *addr;
#endif
} status_table_struct;

#ifdef LABEL_OFFSET
#define F(x) {#x, sizeof(#x)-1, (long)(&&case_##x-&&base)},
#else
#define F(x) {#x, sizeof(#x)-1, &&case_##x},
#endif
#define NUL  {"", 0, 0},
"""

STATUS_DISPATCH_ORIGINAL = """#ifdef LABEL_OFFSET
        goto *(&&base + entry.offset);
#else
        goto *entry.addr;
#endif
"""


def normalize_status_dispatch(source: Path) -> dict[str, object]:
    """Replace GNU labels-as-values with an equivalent portable dispatch."""
    text = source.read_text()
    if text.count(STATUS_TABLE_ORIGINAL) != 1:
        raise RuntimeError("Procps status dispatch table changed")
    if text.count(STATUS_DISPATCH_ORIGINAL) != 1:
        raise RuntimeError("Procps computed-goto dispatch changed")
    table_entries = tuple(dict.fromkeys(re.findall(r"\bF\(([A-Za-z0-9_]+)\)", text)))
    if table_entries[:1] == ("x",):
        table_entries = table_entries[1:]
    if table_entries != STATUS_ACTIONS:
        raise RuntimeError(f"Procps status action order changed: {table_entries}")

    enum_lines = "\n".join(f"    STATUS_{name}," for name in STATUS_ACTIONS)
    portable_table = f"""typedef enum status_action {{
    STATUS_NONE = 0,
{enum_lines}
}} status_action;

typedef struct status_table_struct {{
    unsigned char name[8];        // /proc/*/status field name
    unsigned char len;            // name length
    status_action action;         // portable parser dispatch value
}} status_table_struct;

#define F(x) {{#x, sizeof(#x)-1, STATUS_##x}},
#define NUL  {{"", 0, STATUS_NONE}},
"""
    cases = "\n".join(
        f"        case STATUS_{name}: goto case_{name};" for name in STATUS_ACTIONS
    )
    portable_dispatch = f"""        switch (entry.action) {{
{cases}
        case STATUS_NONE: continue;
        }}
"""
    before = sha256(source)
    text = text.replace(STATUS_TABLE_ORIGINAL, portable_table, 1)
    text = text.replace(STATUS_DISPATCH_ORIGINAL, portable_dispatch, 1)
    source.write_text(text)
    return {
        "path": "library/readproc.c",
        "before_sha256": before,
        "after_sha256": sha256(source),
        "kind": "replace GNU computed goto with enum and switch dispatch",
        "dispatch_actions": len(STATUS_ACTIONS),
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

    transformations.append(normalize_status_dispatch(output / "library/readproc.c"))

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
    print(json.dumps({
        "entrypoints": len(ENTRYPOINTS),
        "portable_status_actions": len(STATUS_ACTIONS),
        "programs": 20,
        "transformations": len(transformations),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
