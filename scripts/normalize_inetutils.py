#!/usr/bin/env python3
"""Stage GNU Inetutils with deterministic multicall entrypoint wrappers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


ENTRYPOINTS = {
    "ftp/main.c": ("ftp", 2), "ftpd/ftpd.c": ("ftpd", 3),
    "ifconfig/ifconfig.c": ("ifconfig", 2),
    "ping/ping.c": ("ping", 2), "ping/ping6.c": ("ping6", 2),
    "src/dnsdomainname.c": ("dnsdomainname", 2),
    "src/hostname.c": ("hostname", 2), "src/inetd.c": ("inetd", 3),
    "src/logger.c": ("logger", 2), "src/rcp.c": ("rcp", 2),
    "src/rexec.c": ("rexec", 2), "src/rexecd.c": ("rexecd", 2),
    "src/rlogin.c": ("rlogin", 2), "src/rlogind.c": ("rlogind", 2),
    "src/rsh.c": ("rsh", 2), "src/rshd.c": ("rshd", 2),
    "src/syslogd.c": ("syslogd", 2), "src/tftp.c": ("tftp", 2),
    "src/tftpd.c": ("tftpd", 2), "src/traceroute.c": ("traceroute", 2),
    "src/uucpd.c": ("uucpd", 2), "talk/talk.c": ("talk", 2),
    "talkd/talkd.c": ("talkd", 2), "telnet/main.c": ("telnet", 2),
    "telnetd/telnetd.c": ("telnetd", 2), "whois/whois.c": ("whois", 2),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            kind, payload = b"L", os.readlink(path).encode()
        elif path.is_file():
            kind, payload = b"F", path.read_bytes()
        elif path.is_dir():
            kind, payload = b"D", b""
        else:
            raise RuntimeError(f"unsupported source entry: {path}")
        digest.update(kind + b"\0" + relative + b"\0" + payload + b"\0")
    return digest.hexdigest()


def export_entrypoint(path: Path, name: str, arity: int) -> None:
    text = path.read_text()
    if text.count("\nmain (") != 1:
        raise RuntimeError(f"Inetutils {name} main precondition failed in {path}")
    public = f"rustbox_inetutils_{name}_main"
    implementation = public if arity == 2 else f"rustbox_inetutils_{name}_program_main"
    text = text.replace("\nmain (", f"\n{implementation} (", 1)
    if arity == 2:
        wrapper_call = f"  return {implementation} (argc, argv);\n"
    else:
        wrapper_call = (
            "  extern char **environ;\n"
            f"  return {implementation} (argc, argv, environ);\n"
        )
    text += (
        "\n"
        + (f"int\n{public} (int argc, char **argv)\n{{\n{wrapper_call}}}\n" if arity == 3 else "")
        + "#ifndef RUSTBOX_MULTICALL\n"
        + "int\nmain (int argc, char **argv)\n{\n"
        + f"  return {public} (argc, argv);\n"
        + "}\n#endif\n"
    )
    path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    canonical = repository / "work/upstream/inetutils-2.8"
    release = json.loads((repository / "upstream/releases.json").read_text())["releases"]["inetutils"]
    state = json.loads((repository / "work/upstream/.state/inetutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Inetutils source state changed at {key}")
    if state.get("signature_verified") is not True:
        raise RuntimeError("canonical Inetutils signature state is incomplete")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    staged = temporary / output.name
    try:
        shutil.copytree(canonical, staged, symlinks=True)
        for relative, (name, arity) in ENTRYPOINTS.items():
            export_entrypoint(staged / relative, name, arity)
        canonical_files = {
            path.relative_to(canonical).as_posix()
            for path in canonical.rglob("*") if path.is_file()
        }
        staged_files = {
            path.relative_to(staged).as_posix()
            for path in staged.rglob("*") if path.is_file()
        }
        if canonical_files != staged_files:
            raise RuntimeError("normalization changed the Inetutils file set")
        changed = sorted(
            name for name in canonical_files
            if sha256(canonical / name) != sha256(staged / name)
        )
        if changed != sorted(ENTRYPOINTS):
            raise RuntimeError(f"unexpected normalized Inetutils sources: {changed}")
        manifest = {
            "schema": 1,
            "release": "2.8",
            "canonical_archive_sha256": release["sha256"],
            "canonical_tree_sha256": tree_digest(canonical),
            "normalized_tree_sha256": tree_digest(staged),
            "changed_sources": changed,
            "entrypoints": {
                name: f"rustbox_inetutils_{name}_main"
                for name, _arity in ENTRYPOINTS.values()
            },
            "conditional": "RUSTBOX_MULTICALL",
            "engine": "exact deterministic source rewrite",
            "transformations": [
                {
                    "source": relative,
                    "canonical_sha256": sha256(canonical / relative),
                    "normalized_sha256": sha256(staged / relative),
                    "operation": (
                        f"export rustbox_inetutils_{name}_main and retain a "
                        "conditional standalone main wrapper"
                    ),
                    "program_main_arity": arity,
                }
                for relative, (name, arity) in sorted(ENTRYPOINTS.items())
            ],
        }
        if output.exists():
            shutil.rmtree(output)
        staged.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_sources": len(changed), "entrypoints": 26}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
