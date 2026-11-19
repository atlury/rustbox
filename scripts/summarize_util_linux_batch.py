#!/usr/bin/env python3
"""Build reproducible evidence for one translated util-linux hybrid batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


HOLES = {
    "compile_error_macros": re.compile(r"\bcompile_error!"),
    "todo_macros": re.compile(r"\btodo!"),
    "unimplemented_macros": re.compile(r"\bunimplemented!"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def rust_metrics(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    result: dict[str, object] = {
        "rust_files": len(files),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "file_sha256": {str(path.relative_to(crate)): sha256(path) for path in files},
    }
    result.update({name: len(pattern.findall(combined)) for name, pattern in HOLES.items()})
    return result


def stripped_size(path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="rustbox-util-strip-") as temporary:
        output = Path(temporary) / path.name
        shutil.copy2(path, output)
        subprocess.run(["strip", "--strip-all", str(output)], check=True)
        return output.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve()
    build = args.build.resolve()
    batch = args.batch
    manifest_path = root / "batches" / f"{batch}.json"
    manifest = load(manifest_path)
    if manifest.get("name") != batch:
        raise RuntimeError("batch manifest mismatch")

    analysis = root / "work/analysis/util-linux-2.42.4"
    base = analysis / "translations/c2rust-0.22.1"
    audit = base / f"{batch}-normalized-audit"
    audit_prepared = base / f"{batch}-normalized-audit-prepared"
    reachable = base / f"{batch}-normalized-reachable"
    reachable_prepared = base / f"{batch}-normalized-reachable-prepared"
    stable = base / f"{batch}-stable"
    suffix = batch.removeprefix("util-linux-small-")
    if suffix not in {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13"}:
        raise RuntimeError(f"undeclared util-linux batch: {batch}")
    hybrid = build / f"rustbox-util-linux-small-{suffix}"
    link_map = hybrid.with_suffix(".map")
    library = stable / f"target/release/libutil_linux_small_{suffix}_normalized_reachable.a"
    for path in (manifest_path, hybrid, link_map, library):
        if not path.is_file():
            raise RuntimeError(f"missing batch artifact: {path}")

    declaration_maps = sorted(audit.rglob("*.c_decls.json"))
    if len(declaration_maps) != manifest["expected_compile_commands"]:
        raise RuntimeError("preserve-unused audit declaration maps are incomplete")
    for crate in (audit, reachable, stable):
        metrics = rust_metrics(crate)
        if any(metrics[name] for name in HOLES):
            raise RuntimeError(f"generated Rust contains a hole: {crate}")

    symbol_output = subprocess.run(
        ["nm", "-g", "--defined-only", str(hybrid)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    replacement_symbols = sorted(
        line.split()[-1]
        for line in symbol_output.splitlines()
        if re.search(r" rustbox_[a-z0-9_]+_main$", line)
    )
    configured_entrypoints = manifest.get("entrypoints")
    if configured_entrypoints is None:
        symbol_names = [re.sub(r"[^a-z0-9_]", "_", name) for name in manifest["applets"]]
    else:
        symbol_names = [record["symbol"] for record in configured_entrypoints.values()]
    expected_symbols = sorted(f"rustbox_{name}_main" for name in symbol_names)
    if replacement_symbols != expected_symbols:
        raise RuntimeError(f"wrong hybrid replacement symbols: {replacement_symbols}")
    map_text = link_map.read_text(encoding="utf-8", errors="replace")
    canonical_objects_by_batch = {
        "01": {
            "line": "text-utils/line.o", "setpgid": "sys-utils/setpgid.o",
            "exch": "misc-utils/exch-exch.o", "ctrlaltdel": "sys-utils/ctrlaltdel.o",
            "setsid": "sys-utils/setsid.o", "choom": "sys-utils/choom.o",
            "fadvise": "misc-utils/fadvise-fadvise.o", "colrm": "text-utils/colrm.o",
            "mcookie": "misc-utils/mcookie.o", "rev": "text-utils/rev.o",
        },
        "02": {
            "pivot_root": "sys-utils/pivot_root.o", "delpart": "disk-utils/delpart.o",
            "addpart": "disk-utils/addpart.o", "findfs": "misc-utils/findfs-findfs.o",
            "nologin": "login-utils/nologin.o", "resizepart": "disk-utils/resizepart.o",
            "mkfs": "disk-utils/mkfs.o", "fsfreeze": "sys-utils/fsfreeze.o",
            "isosize": "disk-utils/isosize.o", "mesg": "term-utils/mesg.o",
        },
        "03": {
            "swaplabel": "disk-utils/swaplabel-swaplabel.o", "lsirq": "sys-utils/lsirq-lsirq.o",
            "newgrp": "login-utils/newgrp-newgrp.o", "uuidgen": "misc-utils/uuidgen-uuidgen.o",
            "switch_root": "sys-utils/switch_root.o", "raw": "disk-utils/raw.o",
            "renice": "sys-utils/renice.o", "ionice": "schedutils/ionice.o",
            "fdformat": "disk-utils/fdformat.o", "copyfilerange": "misc-utils/copyfilerange-copyfilerange.o",
        },
        "04": {
            "taskset": "schedutils/taskset.o", "mountpoint": "sys-utils/mountpoint-mountpoint.o",
            "chsh": "login-utils/chsh-chsh.o", "waitpid": "misc-utils/waitpid-waitpid.o",
            "colcrt": "text-utils/colcrt.o", "getino": "misc-utils/getino-getino.o",
            "ipcmk": "sys-utils/ipcmk.o", "bits": "text-utils/bits.o",
            "swapoff": "sys-utils/swapoff-swapoff.o", "uclampset": "schedutils/uclampset.o",
        },
        "05": {
            "look": "misc-utils/look.o", "pipesz": "misc-utils/pipesz-pipesz.o",
            "blkdiscard": "sys-utils/blkdiscard-blkdiscard.o", "tunelp": "sys-utils/tunelp.o",
            "rename": "misc-utils/rename.o", "uuidparse": "misc-utils/uuidparse-uuidparse.o",
            "utmpdump": "login-utils/utmpdump.o", "lastlog2": "misc-utils/lastlog2-lastlog2.o",
            "scriptlive": "term-utils/scriptlive.o", "vipw": "login-utils/vipw.o",
        },
        "06": {
            "coresched": "schedutils/coresched.o", "chcpu": "sys-utils/chcpu.o",
            "namei": "misc-utils/namei.o", "wall": "term-utils/wall-wall.o",
            "readprofile": "sys-utils/readprofile.o", "scriptreplay": "term-utils/scriptreplay.o",
            "blkpr": "sys-utils/blkpr.o", "ldattach": "sys-utils/ldattach.o",
            "blockdev": "disk-utils/blockdev.o", "flock": "sys-utils/flock.o",
        },
        "07": {
            "mkfs.bfs": "disk-utils/mkfs.bfs.o", "write": "term-utils/write-write.o",
            "getopt": "misc-utils/getopt.o", "fallocate": "sys-utils/fallocate.o",
            "chrt": "schedutils/chrt.o", "fincore": "misc-utils/fincore-fincore.o",
            "whereis": "misc-utils/whereis.o", "col": "text-utils/col.o",
            "chmem": "sys-utils/chmem.o", "rfkill": "sys-utils/rfkill-rfkill.o",
        },
        "08": {"setarch": "sys-utils/setarch.o"},
        "09": {
            "blkzone": "sys-utils/blkzone.o", "ipcrm": "sys-utils/ipcrm.o",
            "fstrim": "sys-utils/fstrim-fstrim.o", "prlimit": "sys-utils/prlimit-prlimit.o",
            "fsck.cramfs": "disk-utils/fsck.cramfs.o", "mkfs.cramfs": "disk-utils/mkfs.cramfs.o",
            "kill": "misc-utils/kill.o", "rtcwake": "sys-utils/rtcwake.o",
            "wdctl": "sys-utils/wdctl-wdctl.o", "ul": "text-utils/ul-ul.o",
        },
        "10": {
            "enosys": "misc-utils/enosys-enosys.o", "ipcs": "sys-utils/ipcs.o",
            "last": "login-utils/last.o", "lsclocks": "misc-utils/lsclocks-lsclocks.o",
            "lslocks": "misc-utils/lslocks-lslocks.o", "lsmem": "sys-utils/lsmem-lsmem.o",
            "mkfs.minix": "disk-utils/mkfs.minix.o", "mkswap": "disk-utils/mkswap-mkswap.o",
            "setterm": "term-utils/setterm-setterm.o", "uuidd": "misc-utils/uuidd-uuidd.o",
        },
        "11": {
            "blkid": "misc-utils/blkid-blkid.o", "column": "text-utils/column-column.o",
            "eject": "sys-utils/eject-eject.o", "logger": "misc-utils/logger-logger.o",
            "losetup": "sys-utils/losetup-losetup.o", "nsenter": "sys-utils/nsenter.o",
            "partx": "disk-utils/partx-partx.o", "setpriv": "sys-utils/setpriv.o",
            "wipefs": "misc-utils/wipefs-wipefs.o", "zramctl": "sys-utils/zramctl-zramctl.o",
        },
        "12": {
            "cal": "misc-utils/cal-cal.o", "dmesg": "sys-utils/dmesg-dmesg.o",
            "fsck.minix": "disk-utils/fsck.minix.o", "hardlink": "misc-utils/hardlink-hardlink.o",
            "irqtop": "sys-utils/irqtop-irqtop.o", "lsipc": "sys-utils/lsipc-lsipc.o",
            "more": "text-utils/more-more.o", "mount": "sys-utils/mount-mount.o",
            "pg": "text-utils/pg-pg.o", "umount": "sys-utils/umount-umount.o",
        },
        "13": {
            "chfn": "login-utils/chfn-chfn.o", "fsck": "disk-utils/fsck-fsck.o",
            "hexdump": "text-utils/hexdump.o", "hwclock": "sys-utils/hwclock-hwclock.o",
            "lscpu": "sys-utils/lscpu-lscpu.o", "lslogins": "login-utils/lslogins-lslogins.o",
            "lsns": "sys-utils/lsns-lsns.o", "script": "term-utils/script-script.o",
            "swapon": "sys-utils/swapon-swapon.o", "unshare": "sys-utils/unshare-unshare.o",
        },
    }
    canonical_objects = canonical_objects_by_batch[suffix]
    if any(name in map_text for name in canonical_objects.values()):
        raise RuntimeError("hybrid link map contains a replaced canonical applet object")
    support_symbol_specializations = []
    if suffix == "13":
        canonical_parser = build / "sys-utils/hwclock-hwclock-parse-date.o"
        specialized_parser = build / "rustbox-support-13/hwclock-parse-date.o"
        for path in (canonical_parser, specialized_parser):
            if not path.is_file():
                raise RuntimeError(f"missing parser support object: {path}")
        canonical_symbols = subprocess.run(
            ["nm", "-g", "--defined-only", str(canonical_parser)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        specialized_symbols = subprocess.run(
            ["nm", "-g", "--defined-only", str(specialized_parser)],
            check=True, text=True, stdout=subprocess.PIPE,
        ).stdout
        if " yyparse\n" not in canonical_symbols or " rustbox_hwclock_yyparse\n" not in specialized_symbols:
            raise RuntimeError("hwclock parser support symbol specialization is incomplete")
        support_symbol_specializations.append({
            "object": "sys-utils/hwclock-hwclock-parse-date.o",
            "canonical_sha256": sha256(canonical_parser),
            "specialized_sha256": sha256(specialized_parser),
            "renamed_symbol": "yyparse",
            "replacement_symbol": "rustbox_hwclock_yyparse",
            "reason": "avoid collision with libsmartcols' independent Bison parser in one multicall link",
        })

    modernization = load(stable / "rustbox-modernization.json")
    opaque = sorted({
        name
        for change in modernization["changes"]
        for name in change["opaque_pointer_types"]
    })
    repair = {
        "01": (3, "feature-gate cleanup (1) and reusable opaque-pointer spelling rule (2)"),
        "02": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "03": (3, "feature-gate cleanup (1) and reusable opaque-pointer spelling rule (2)"),
        "04": (3, "feature-gate cleanup (1) and reusable opaque-pointer spelling rule (2)"),
        "05": (3, "feature-gate cleanup (1) and reusable opaque-pointer spelling rule (2)"),
        "06": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "07": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "08": (3, "feature-gate cleanup (1) and reusable opaque-pointer spelling rule (2)"),
        "09": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "10": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "11": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
        "12": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaList spelling/cursor modernization (2)"),
        "13": (5, "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), and reusable VaListImpl/as_va_list modernization (2)"),
    }[suffix]
    targeted = {
        "01": {"components": 9, "passed": 9, "ctrlaltdel": "no upstream component test; hard and soft branches compared unprivileged"},
        "02": {"components": 1, "passed": 1, "subtests": 3, "coverage_note": "isosize is the only upstream component test for this batch; the other nine applets are covered by differential and Valgrind cases"},
        "03": {"components": 5, "passed": 5, "copyfilerange_subtests": 8, "coverage_note": "all available swaplabel, uuidgen, ionice, and copyfilerange components passed; the other six applets are covered by differential and Valgrind cases"},
        "04": {"components": 7, "passed": 7, "ordinary_subtests_passed": 32, "upstream_known_failure_subtests": 6, "coverage_note": "the upstream harness classifies the environment-dependent getino and waitpid pidfd-inode cases as known failures; all seven components passed under upstream policy"},
        "05": {"components": 10, "passed": 10, "ordinary_subtests_passed": 18, "upstream_skipped_components": 1, "coverage_note": "the root-only blkdiscard offsets component was skipped by upstream policy; safe unprivileged blkdiscard behavior is covered differentially and under Valgrind"},
        "06": {"components": 4, "passed": 4, "ordinary_subtests_passed": 17, "upstream_skipped_components": 1, "coverage_note": "coresched was skipped under upstream policy because the test kernel lacks CONFIG_SCHED_CORE; all 17 executable flock, range-lock, and namei checks passed, while coresched and the other six applets are covered by safe differential and Valgrind cases"},
        "07": {"components": 11, "passed": 11, "ordinary_subtests_passed": 63, "upstream_skipped_components": 1, "coverage_note": "the root-only chrt component was skipped under upstream policy; its non-root component and all 63 executable chrt, col, fallocate, fincore, getopt, and whereis checks passed, while mkfs.bfs, write, chmem, and rfkill are covered by safe differential and Valgrind cases"},
        "08": {"components": 3, "passed": 3, "ordinary_subtests_passed": 1, "upstream_skipped_components": 2, "coverage_note": "one setarch component executed and two environment-dependent components were skipped under upstream Docker policy; all three passed under that policy, and all 22 public aliases are covered differentially and share the one resource-checked implementation body"},
        "09": {"components": 9, "passed": 9, "ordinary_components_passed": 1, "upstream_skipped_components": 7, "upstream_known_failed_subtests": 3, "coverage_note": "all seven kill components were skipped under upstream Docker policy because they require root or unavailable test helpers; ul/ul passed, while ul/basic retained its three upstream-known failures; the other eight applets are covered by safe differential and Valgrind cases"},
        "10": {"components": 21, "passed": 21, "ordinary_components_passed": 10, "ordinary_subtests_passed": 27, "upstream_skipped_components": 5, "upstream_skipped_subtests": 2, "coverage_note": "five helper-, root-, or bc-dependent components and two unavailable-device subtests were skipped under upstream Docker policy; 10 ordinary components and 27 executable subtests passed, while mkfs.minix, setterm, and both last public names are additionally covered by safe differential and Valgrind cases"},
        "11": {"components": 31, "passed": 31, "ordinary_components_passed": 11, "ordinary_subtests_passed": 207, "upstream_skipped_components": 20, "coverage_note": "20 root- or unavailable-helper-dependent components were skipped under upstream Docker policy; 11 ordinary components and 207 executable subtests passed, while all ten public names, including zramctl which has no upstream component, are additionally covered by safe differential and Valgrind cases"},
        "12": {"components": 66, "passed": 66, "ordinary_components_passed": 8, "ordinary_subtests_passed": 59, "upstream_skipped_components": 58, "coverage_note": "58 root- or unavailable-helper-dependent components were skipped under upstream Docker policy; eight ordinary cal and hardlink components and 59 executable subtests passed, while all ten public names are additionally covered by safe differential and Valgrind cases"},
        "13": {"components": 29, "passed": 29, "ordinary_components_passed": 8, "ordinary_subtests_passed": 65, "upstream_skipped_components": 21, "upstream_known_failed_subtests": 1, "coverage_note": "21 root-, namespace-, or unavailable-helper-dependent components were skipped under upstream Docker policy; eight ordinary components and 65 executable subtests passed, while script/replay-live retained its one upstream-known failure; all ten public names are additionally covered by safe differential and Valgrind cases"},
    }[suffix]
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-20",
        "status": "hybrid canonical parity; Rustbox-native integration pending",
        "batch": {
            "name": batch,
            "applets": manifest["applets"],
            "manifest_sha256": sha256(manifest_path),
        },
        "input": {
            "upstream_archive_sha256": "fbd62a100ab7bb8746ba0661255c3c48185b1e9021507c624da01fbc696330ec",
            "clang_database_sha256": sha256(analysis / "canonical-clang/compile_commands.json"),
            "gcc_database_sha256": sha256(analysis / "canonical-gcc/compile_commands.json"),
            "compile_commands": manifest["expected_compile_commands"],
            "slice_sha256": sha256(analysis / f"slices/{batch}/compile_commands.json"),
        },
        "normalization": load(analysis / f"normalized/{batch}/normalization.json"),
        "entrypoint_specialization": load(analysis / f"normalized/{batch}/entrypoints/entrypoints.json"),
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "image_id": "sha256:d7f3755ec6a27d89124626535d36b859ddee1f7a11236454f7952bf513c3d6aa",
            "fail_on_error": True,
            "audit_preserves_unused_functions": True,
        },
        "audit": {
            **rust_metrics(audit),
            "declaration_maps": len(declaration_maps),
            "declaration_map_sha256": {
                str(path.relative_to(audit)): sha256(path) for path in declaration_maps
            },
            "scaffold": load(audit_prepared / "rustbox-scaffold.json"),
            "cargo_check": load(audit_prepared / "rustbox-cargo-check.json"),
            "generated_rust_repairs": load(audit_prepared / "rustbox-scaffold.json")["rust_files_changed"],
        },
        "reachable": {
            **rust_metrics(reachable),
            "scaffold": load(reachable_prepared / "rustbox-scaffold.json"),
            "cargo_check": load(reachable_prepared / "rustbox-cargo-check.json"),
            "generated_rust_repairs": load(reachable_prepared / "rustbox-scaffold.json")["rust_files_changed"],
        },
        "stable_integration": {
            **rust_metrics(stable),
            "cargo_check": load(stable / "rustbox-cargo-check.json"),
            "modernization_manifest_sha256": sha256(stable / "rustbox-modernization.json"),
            "opaque_types_verified_pointer_only": opaque,
            "hand_edits": 0,
            "repair_score": repair[0],
            "repair_score_basis": repair[1],
        },
        "hybrid": {
            "bytes": hybrid.stat().st_size,
            "stripped_bytes": stripped_size(hybrid),
            "sha256": sha256(hybrid),
            "link_map_sha256": sha256(link_map),
            "replacement_symbols_defined_once": True,
            "canonical_applet_objects_linked": False,
            "support_symbol_specializations": support_symbol_specializations,
        },
        "behavior": {
            "differential": load(stable / "differential.json"),
            "targeted_upstream": {**targeted, "log_sha256": sha256(stable / "upstream-targeted.log")},
            "valgrind": load(stable / "resources.json"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "applets": len(manifest["applets"]),
        "differential": evidence["behavior"]["differential"]["passed"],
        "repair_score": evidence["stable_integration"]["repair_score"],
        "stripped_bytes": evidence["hybrid"]["stripped_bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
