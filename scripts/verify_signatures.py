#!/usr/bin/env python3
"""Verify pinned upstream signatures with pinned OpenPGP key material."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def checked(path: Path, expected: str, label: str) -> None:
    actual = digest(path)
    if actual != expected:
        raise RuntimeError(f"{label}: SHA-256 {actual}, expected {expected}")


def record_verification(root: Path, name: str, release: dict[str, str]) -> None:
    state_path = root / "work/upstream/.state" / f"{name}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if release.get("source_kind") == "signed-git-tag":
        expected = {
            "version": release["version"],
            "source_kind": "signed-git-tag",
            "tag": release["tag"],
            "commit": release["commit"],
            "tree": release["tree"],
            "key_sha256": release["key_sha256"],
            "signer_fingerprint": release["signer_fingerprint"],
        }
    else:
        expected = {
            "version": release["version"],
            "sha256": release["sha256"],
            "signature_sha256": release["signature_sha256"],
            "key_sha256": release["key_sha256"],
            "signer_fingerprint": release["signer_fingerprint"],
        }
    for field, value in expected.items():
        if state.get(field) != value:
            raise RuntimeError(
                f"{name} state {field}={state.get(field)!r}, expected {value!r}"
            )
    state["signature_verified"] = True
    temporary = state_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, state_path)


def verify(
    home: Path, signature: Path, archive: Path, mode: str, expected_fingerprint: str
) -> None:
    command = [
        "gpg",
        "--batch",
        "--homedir",
        str(home),
        "--status-fd=1",
        "--verify",
        str(signature),
    ]
    decompressor = None
    if mode == "archive":
        command.append(str(archive))
        result = subprocess.run(command, check=False, text=True, capture_output=True)
    elif mode == "uncompressed-tar":
        command.append("-")
        decompressor = subprocess.Popen(["xz", "-dc", str(archive)], stdout=subprocess.PIPE)
        assert decompressor.stdout is not None
        result = subprocess.run(
            command,
            stdin=decompressor.stdout,
            check=False,
            text=True,
            capture_output=True,
        )
        decompressor.stdout.close()
        decompressor_status = decompressor.wait()
        if decompressor_status != 0:
            raise RuntimeError(f"xz failed with status {decompressor_status}")
    else:
        raise RuntimeError(f"unknown signature mode {mode!r}")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    fingerprints = re.findall(r"^\[GNUPG:\] VALIDSIG ([0-9A-F]{40})\b", result.stdout, re.MULTILINE)
    if fingerprints != [expected_fingerprint]:
        raise RuntimeError(
            f"valid signature fingerprints {fingerprints}, expected {[expected_fingerprint]}"
        )


def verify_signed_git(root: Path, name: str, release: dict[str, str], key: Path) -> None:
    source = root / "work/upstream" / release["source_directory"]
    keys = [line for line in key.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not keys:
        raise RuntimeError(f"{name}: signing-key file is empty")
    with tempfile.TemporaryDirectory(prefix="rustbox-allowed-signers-") as directory:
        allowed = Path(directory) / "allowed_signers"
        allowed.write_text(
            "".join(f"{release['signer_principal']} {line}\n" for line in keys),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "git", "-c", f"safe.directory={source}",
                "-c", f"gpg.ssh.allowedSignersFile={allowed}", "-C", str(source),
                "verify-tag", "--raw", release["tag"],
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    diagnostic = result.stdout + result.stderr
    if result.returncode != 0 or release["signer_fingerprint"] not in diagnostic:
        raise RuntimeError(diagnostic.strip() or f"{name}: signed tag verification failed")
    commit = subprocess.run(
        ["git", "-c", f"safe.directory={source}", "-C", str(source), "rev-parse", release["tag"] + "^{}"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-c", f"safe.directory={source}", "-C", str(source), "rev-parse", release["tag"] + "^{tree}"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    if commit != release["commit"] or tree != release["tree"]:
        raise RuntimeError(f"{name}: verified tag resolves outside the immutable pin")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="*")
    args = parser.parse_args()
    releases = json.loads((root / "upstream/releases.json").read_text(encoding="utf-8"))[
        "releases"
    ]
    selected = args.packages or list(releases)
    unknown = sorted(set(selected) - set(releases))
    if unknown:
        parser.error("unknown packages: " + ", ".join(unknown))

    cache = root / ".cache/downloads"
    for name in selected:
        release = releases[name]
        if release.get("source_kind") == "signed-git-tag":
            key = cache / release["key"]
            checked(key, release["key_sha256"], f"{name} key")
            verify_signed_git(root, name, release, key)
            record_verification(root, name, release)
            print(f"{name} {release['version']}: valid signature {release['signer_fingerprint']}")
            continue
        archive = cache / release["archive"]
        signature = cache / (release["archive"] + ".signature")
        key = cache / release["key"]
        checked(archive, release["sha256"], f"{name} archive")
        checked(signature, release["signature_sha256"], f"{name} signature")
        checked(key, release["key_sha256"], f"{name} key")
        with tempfile.TemporaryDirectory(prefix="rustbox-gnupg-") as directory:
            home = Path(directory)
            os.chmod(home, 0o700)
            subprocess.run(
                ["gpg", "--batch", "--homedir", str(home), "--import", str(key)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            verify(
                home,
                signature,
                archive,
                release["signature_mode"],
                release["signer_fingerprint"],
            )
        record_verification(root, name, release)
        print(f"{name} {release['version']}: valid signature {release['signer_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
