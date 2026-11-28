"""Set up isolated upstream oracle trees for installed multicall packages."""
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest

PACKAGES = {"findutils", "kmod", "ncurses", "shadow", "tar"}


def snapshot_terminfo(source, archive):
    """Pack the installed database deterministically for a single transfer into the Linux VM."""
    with TemporaryDirectory(dir=archive.parent) as tmp:
        staged = Path(tmp) / "database.tar"
        with tarfile.open(staged, "w") as tar:
            for path in sorted(source.rglob("*")):
                info = tarfile.TarInfo(path.relative_to(source).as_posix())
                if path.is_symlink():
                    if not path.resolve().is_relative_to(source.resolve()):
                        raise ValueError("terminfo symlink leaves the installed database")
                    info.type, info.linkname = tarfile.SYMTYPE, os.readlink(path)
                elif path.is_dir():
                    info.type, info.mode = tarfile.DIRTYPE, 0o755
                elif path.is_file():
                    info.size = path.stat().st_size
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
                    continue
                else:
                    raise ValueError("unexpected terminfo file type")
                tar.addfile(info)
        staged.replace(archive)


def staged_ncurses_oracle(source, cc, stage, baseline):
    packed = source.parent / (cc + "-terminfo.tar")
    if not packed.exists():
        return source
    pins = json.loads((ROOT / "evidence/ncurses-terminfo-snapshots.json").read_bytes())
    if digest(packed) != pins[cc]:
        raise ValueError("packed terminal database differs from its canonical source")
    local = stage / "upstream"
    bindir = local / "usr/bin"
    bindir.mkdir(parents=True)
    (local / "usr/lib").symlink_to(source / "usr/lib")
    for name in [*baseline["inventory"]["native_public_names"], baseline["inventory"]["config_helper"]]:
        shutil.copy2(source / "usr/bin" / name, bindir / name)
    with tarfile.open(packed) as tar:
        tar.extractall(local / "usr/share/terminfo", filter="data")
    return local


def prepare(name, cc, elf, stage, baseline, directory):
    pins = {}
    dispatch = stage / "programs"
    dispatch.mkdir()

    def pin(path, sha):
        if digest(path) != sha:
            raise ValueError(f"canonical {name} {cc} input changed: {path.name}")
        pins[path.name] = sha

    def entry(relative, target=elf):
        path = dispatch / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)

    if name == "findutils":
        source = Path("/rustbox-findutils") / ("oracle-" + cc)
        installed = directory / (cc + "-root")
        build_names = ("find/find", "xargs/xargs", "locate/locate", "locate/frcode", "locate/updatedb")
        fingerprints = json.loads((ROOT / "evidence/findutils-oracle-build-binaries.json").read_bytes())[cc]
        for rel in build_names:
            tool = Path(rel).name
            file = installed / ("usr/libexec" if tool == "frcode" else "usr/bin") / tool
            # The installed updatedb script has install-time substitutions. Compare its
            # build-tree copy with the recorded build-tree hash instead.
            pin(source / rel, fingerprints[tool])
            if cc == "gcc" and tool in baseline["binaries"] and digest(file) != baseline["binaries"][tool]["sha256"]:
                raise ValueError(f"installed GNU Findutils {tool} differs from the original oracle")
            entry(rel, source / rel if tool == "frcode" else elf)
        return ["--gcc-build", source, "--clang-build", dispatch], pins, baseline["differential"]["cases"]
    if name == "shadow":
        compiler = "clang-18" if cc == "clang" else "gcc"
        source = Path("/rustbox-shadow") / ("programs-" + compiler)
        for tool, info in baseline["binaries"][cc].items():
            pin(source / tool, info["sha256"])
        args = ["--gcc-root", source, "--clang-root", dispatch, "--clang-multicall", elf]
        return args, pins, baseline["differential"]["cases"]
    if name == "kmod":
        source = Path("/rustbox-kmod") / ("oracle-" + cc)
        for tool in baseline["applets"]:
            pin(source / tool, baseline["binaries"][cc]["sha256"])
            entry(tool)
        return ["--gcc-root", source, "--clang-root", dispatch], pins, baseline["differential"]["cases"]
    source = directory / (cc + "-root")
    if name == "ncurses":
        source = staged_ncurses_oracle(source, cc, stage, baseline)
        tools = baseline["inventory"]["native_public_names"]
        # Both programs read the same installed database. The suite writes new
        # entries to distinct temporary tic output directories.
        entry("usr/share/terminfo", source / "usr/share/terminfo")
        helper = baseline["inventory"]["config_helper"]
        helper_path = source / "usr/bin" / helper
        pin(helper_path, "bbe999377085acabb5ee26a5be039df6065275aca7db1615d4dc250a8e8323f3")
        entry("usr/bin/" + helper)
        paths = ["usr/bin/" + tool for tool in tools]
    elif name == "tar":
        paths = ["usr/bin/tar", "usr/libexec/rmt"]
    else:
        raise ValueError(f"no installed oracle for {name}")
    for rel in paths:
        pin(source / rel, baseline["binaries"][cc + "-" + Path(rel).name]["sha256"])
        entry(rel)
    return ["--gcc-root", source, "--clang-root", dispatch], pins, baseline["behavior"]["differential"]["cases"]

if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(description="Pack the pinned ncurses databases for faster offline Linux tests")
    parser.parse_args()
    directory = ROOT / "work/analysis/ncurses-6.6/oracle"
    for compiler in ("gcc", "clang"):
        archive = directory / (compiler + "-terminfo.tar")
        snapshot_terminfo(directory / (compiler + "-root/usr/share/terminfo"), archive)
        print(compiler, digest(archive))
