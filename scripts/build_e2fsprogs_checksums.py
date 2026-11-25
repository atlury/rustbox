#!/usr/bin/env python3
"""Build the E2fsprogs archives that call Rustbox's shared checksum and bitmap implementations."""
# SPDX-License-Identifier: GPL-2.0-only

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
CONSUMERS = ("badblocks", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck", "e2image",
             "e2initrd_helper", "e2undo", "e4defrag", "fuse2fs", "mke2fs", "resize2fs",
             "tune2fs")
CRC_SYMBOLS = {"ext2fs_crc16": "rustbox_e2fsprogs_crc16",
               "ext2fs_crc32c_le": "rustbox_e2fsprogs_crc32c_le",
               "ext2fs_crc32_be": "rustbox_e2fsprogs_crc32_be"}
CRC32_MODULE_SHA = "80982c29cb09587a5ce5159cc157507e78defcf5b5365e8d6670affbdf0538c7"
MODULE_SHA = "c3e5eff63f35648b28420174e58a0646ab5ec29d93e9d37321c5f557beed45cd"
CALLER_SHA = "df60cd81ca32e4acb08f47c7d9c84b8ce03c5784d9634558dc57987b8623dab4"


BITCOUNT_SYMBOL = "rustbox_e2fsprogs_bitcount"
BITCOUNT_CALLERS = {
    "e2fsck/pass5.rs": "71df0858941f8e7e928eb22801df324ff27e708b906bcd5d5c4d37bc4b29ff03",
    "resize/resize2fs.rs": "8bdd2f7e4ad9f8addc8c4bb5b291e9c2657694408a456e656395002a57dc39da",
}
SHARED_SOURCES = {"crc16.o": "crc16_abi.rs", "crc32.o": "crc32_abi.rs", "bitcount.o": "bitcount.rs"}


def stage_bitcount(module):
    bitops = module.with_name("bitops.rs")
    data = bitops.read_bytes()
    if hashlib.sha256(data).hexdigest() != "0e380796c9a66bdbd6249ae9b6ae5b2f2fbf55495f45d6c5fe665334c9651aca":
        raise ValueError("unexpected E2fsprogs bitmap operations module")
    # The pinned module ends with popcount8, popcount32 and ext2fs_bitcount.
    start = data.index(b'unsafe extern "C" fn popcount8(')
    bitops.write_bytes(data[:start])
    declaration = b"    fn ext2fs_bitcount("
    for relative, expected in BITCOUNT_CALLERS.items():
        source = module.parents[2] / relative
        if source.is_file():
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected or data.count(declaration) != 1:
                raise ValueError(f"unexpected bitmap counter caller: {relative}")
            attribute = f'    #[link_name = "{BITCOUNT_SYMBOL}"]\n'.encode()
            source.write_bytes(data.replace(declaration, attribute + declaration))


def stage(engine, shared=True, share_bitcount=True):
    module, = engine.glob("**/lib/ext2fs/crc16.rs")
    if hashlib.sha256(module.read_bytes()).hexdigest() != MODULE_SHA:
        raise ValueError(f"unexpected checksum module in {engine}")
    module.write_text("// The checksum is supplied by the shared Rustbox object.\n")
    if shared:
        caller = module.with_name("csum.rs")
        contents = caller.read_bytes()
        if hashlib.sha256(contents).hexdigest() != CALLER_SHA:
            raise ValueError(f"unexpected checksum caller in {engine}")
        old = b"    fn ext2fs_crc16("
        if contents.count(old) != 1:
            raise ValueError("expected one checksum declaration")
        caller.write_bytes(contents.replace(old, '    #[link_name = "rustbox_e2fsprogs_crc16"]\n'.encode() + old))

        crc32 = module.with_name("crc32c.rs")
        if hashlib.sha256(crc32.read_bytes()).hexdigest() != CRC32_MODULE_SHA:
            raise ValueError(f"unexpected CRC32 translation in {engine}")
        crc32.write_text("// Both CRC32 functions are supplied by the shared Rustbox object.\n")
        declarations = re.compile(rb"^( +)((?:pub )?fn (ext2fs_crc32c_le|ext2fs_crc32_be)\()", re.M)
        for source in engine.rglob("*.rs"):
            data = source.read_bytes()
            if b"ext2fs_crc32" not in data:
                continue
            def link_name(match):
                name = CRC_SYMBOLS[match[3].decode()]
                return match[1] + f'#[link_name = "{name}"]\n'.encode() + match[0]
            updated = declarations.sub(link_name, data)
            if updated != data:
                source.write_bytes(updated)
        if share_bitcount:
            stage_bitcount(module)


def build_archive(name, translations, archive, shared=True):
    import tomllib

    deps = translations / "cargo-target" / name / "release/deps"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory(dir=archive.parent) as tmp:
        engine = Path(scratch) / name
        shutil.copytree(translations / name / f"{name}-final", engine,
                        ignore=shutil.ignore_patterns("target"))
        stage(engine, shared)
        crate = tomllib.loads((engine / "Cargo.toml").read_text())
        staged = Path(tmp) / archive.name
        depfile = Path(tmp) / "compiler.d"
        args = ["rustc", "+nightly-2023-04-15", "--edition=2021", "--crate-type=staticlib",
                "--crate-name", crate["lib"]["name"], "-C", "opt-level=3", "--cap-lints=allow",
                "--remap-path-prefix", f"{scratch}=/rustbox-e2fsprogs", "-L", f"dependency={deps}"]
        libraries = {}
        for dependency in crate["dependencies"]:
            rust_name = dependency.replace("-", "_")
            library, = deps.glob(f"lib{rust_name}-*.rlib")
            args.extend(["--extern", f"{rust_name}={library}"])
            libraries[rust_name] = hashlib.sha256(library.read_bytes()).hexdigest()
        # Reuse only the same staged source tree, compiler, build recipe and dependency archives.
        identity = {
            "compiler": subprocess.check_output(["rustc", "+nightly-2023-04-15", "-vV"], text=True),
            "builder": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "dependencies": libraries,
            "crate": hashlib.sha256((engine / "Cargo.toml").read_bytes()).hexdigest(),
            "inputs": {str(p.relative_to(engine)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in engine.rglob("*.rs")},
        }
        build_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        saved = archive.with_suffix(".sources.json")
        if saved.is_file() and archive.is_file():
            previous = json.loads(saved.read_text())
            if (previous.get("build_key") == build_key and
                    previous["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()):
                return archive
        subprocess.run([*args, f"--emit=link,dep-info={depfile}", "lib.rs", "-o", staged],
                       cwd=engine, check=True)
        rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
        inputs = {n for n in shlex.split(rule) if n.endswith(".rs")}
        manifest = {"build_key": build_key, "archive_sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
                    "sources": {n: hashlib.sha256((engine / n).read_bytes()).hexdigest()
                                for n in sorted(inputs)}}
        sidecar = staged.with_suffix(".sources.json")
        sidecar.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        sidecar.replace(archive.with_suffix(".sources.json"))
        staged.replace(archive)
    return archive


def build_shared(translations, output):
    actual = sorted(p.parent.name for p in translations.glob("*/*-final")
                    if any(p.glob("**/lib/ext2fs/crc16.rs")))
    if tuple(actual) != CONSUMERS:
        raise ValueError(f"unexpected set of CRC16 consumers: {actual}")
    output.mkdir(parents=True, exist_ok=True)
    objects = []
    for name, source in SHARED_SOURCES.items():
        obj = output / name
        objects.append(obj)
        with tempfile.TemporaryDirectory(dir=output) as tmp:
            staged = Path(tmp) / obj.name
            depfile = Path(tmp) / "compiler.d"
            subprocess.run(["rustc", "--edition=2021", "--crate-type=lib",
                            f"--emit=obj,dep-info={depfile}", "--cfg", "rustbox_multicall",
                            "-C", "opt-level=s", "-C", "panic=abort",
                            f"compat/e2fsprogs/{source}", "-o", staged], cwd=REPO, check=True)
            rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
            sources = sorted({n for n in shlex.split(rule) if n.endswith(".rs")})
            manifest = {"archive_sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
                        "sources": {n: hashlib.sha256((REPO / n).read_bytes()).hexdigest() for n in sources}}
            sidecar = staged.with_suffix(".sources.json")
            sidecar.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            sidecar.replace(obj.with_suffix(".sources.json"))
            staged.replace(obj)
    archives = {n: output / n / f"lib{n}_audit.a" for n in CONSUMERS}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(build_archive, n, translations, path) for n, path in archives.items()]
        for result in futures:
            print(f"Built shared-checksum consumer {result.result().parent.name}", flush=True)
    return archives, objects


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("translations", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_shared(args.translations.resolve(), args.output.resolve())
