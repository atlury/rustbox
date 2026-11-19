#!/usr/bin/env python3
"""Generate Rustbox's durable applet inventory from canonical build files."""

from __future__ import annotations

import json
import re
from pathlib import Path


BEGIN = "<!-- BEGIN APPLET INVENTORY -->"
END = "<!-- END APPLET INVENTORY -->"


def coreutils_parity_evidence(root: Path) -> dict[str, int]:
    """Return applet repair scores from completed, committed evidence."""
    result: dict[str, int] = {}
    for path in sorted((root / "evidence").glob("coreutils-9.12-c2rust-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "hybrid canonical parity; Rustbox-native integration pending":
            continue
        batch = record.get("batch")
        if isinstance(batch, dict):
            applets = batch.get("applets", [])
        elif path.name == "coreutils-9.12-c2rust-true-false.json":
            applets = ["false", "true"]
        else:
            raise RuntimeError(f"parity evidence lacks an applet list: {path}")
        score = record["stable_integration"]["repair_score"]
        for applet in applets:
            if applet in result:
                raise RuntimeError(f"duplicate Coreutils parity evidence: {applet}")
            result[applet] = score
    return result


def coreutils(root: Path) -> list[str]:
    build = (root / "src/cu-progs.mk").read_text(encoding="utf-8")
    programs = set(
        re.findall(
            r"^(?:no_install|build_if_possible|build_if_appropriate|default)__progs "
            r"\+= src/([^\s]+)$",
            build,
            flags=re.MULTILINE,
        )
    )
    programs.discard("coreutils")
    programs.discard("libstdbuf.so")
    programs.discard("getlimits")
    if "ginstall" in programs:
        programs.remove("ginstall")
        programs.add("install")
    return sorted(programs)


def meson_call_end(text: str, opening: int) -> int:
    depth = 0
    quote = ""
    escaped = False
    index = opening
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == "#":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError(f"unterminated Meson call at byte {opening}")


def util_linux(root: Path) -> list[str]:
    build = (root / "meson.build").read_text(encoding="utf-8")
    programs: set[str] = set()
    for match in re.finditer(r"\bexecutable\s*\(\s*'([^']+)'", build):
        opening = build.find("(", match.start())
        call = build[match.start() : meson_call_end(build, opening)]
        install = re.search(r"\binstall\s*:\s*([^,\n)]+)", call)
        if install is None or install.group(1).strip() == "false":
            continue
        name = match.group(1)
        if not name.endswith(".static"):
            programs.add(name)

    # Installed aliases are separate public applet names even when they share
    # an executable body with their target.
    for match in re.finditer(
        r"meson_make_symlink\s*,\s*'[^']+'\s*,\s*[^\n,]+/\s*'([^']+)'",
        build,
    ):
        name = match.group(1)
        if "/" not in name:
            programs.add(name)

    setarch_start = build.index("setarch_links =")
    setarch_end = build.index("foreach link: setarch_links", setarch_start)
    setarch_section = build[setarch_start:setarch_end]
    for bracket in re.findall(r"\[([^]]*)\]", setarch_section, flags=re.DOTALL):
        programs.update(re.findall(r"'([^']+)'", bracket))
    return sorted(programs)


def markdown_group(title: str, programs: dict[str, dict[str, object]]) -> str:
    lines = [f"### {title} ({len(programs)})", ""]
    for program, record in programs.items():
        stage = record["stage"]
        checked = "x" if stage == "canonical-parity" else " "
        repair = record["repair_score"]
        suffix = "" if repair is None else f"; repair score {repair}"
        shown_stage = "hybrid canonical parity" if stage == "canonical-parity" else stage
        lines.append(f"- [{checked}] `{program}` — {shown_stage}{suffix}")
    return "\n".join(lines)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    source_root = root / "work/upstream"
    core = coreutils(source_root / "coreutils-9.12")
    util = util_linux(source_root / "util-linux-2.42.4")
    inventory_path = root / "upstream/applets.json"
    if inventory_path.exists():
        previous = json.loads(inventory_path.read_text(encoding="utf-8"))
    else:
        previous = {"upstreams": {}}

    def records(upstream: str, names: list[str]) -> dict[str, dict[str, object]]:
        old = previous.get("upstreams", {}).get(upstream, {})
        return {
            name: old.get(name, {"stage": "inventory", "repair_score": None})
            for name in names
        }

    core_records = records("coreutils", core)
    util_records = records("util-linux", util)
    for name, score in coreutils_parity_evidence(root).items():
        if name not in core_records:
            raise RuntimeError(f"evidence names an unknown Coreutils applet: {name}")
        core_records[name] = {"stage": "canonical-parity", "repair_score": score}
    inventory = {
        "schema": 1,
        "stages": [
            "inventory",
            "normalized",
            "translated",
            "integrated",
            "canonical-parity",
        ],
        "upstreams": {
            "coreutils": core_records,
            "util-linux": util_records,
        },
    }
    inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    before, separator, remainder = readme.partition(BEGIN)
    if not separator:
        raise RuntimeError(f"{readme_path} lacks {BEGIN}")
    _, separator, after = remainder.partition(END)
    if not separator:
        raise RuntimeError(f"{readme_path} lacks {END}")
    generated = (
        f"{BEGIN}\n\n"
        f"{markdown_group('GNU Coreutils 9.12', core_records)}\n\n"
        f"{markdown_group('util-linux 2.42.4', util_records)}\n\n"
        f"**Total: {len(core) + len(util)} applet names.**\n\n"
        f"{END}"
    )
    readme_path.write_text(before + generated + after, encoding="utf-8")
    print(f"coreutils={len(core)} util-linux={len(util)} total={len(core) + len(util)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
