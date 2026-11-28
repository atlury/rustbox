"""Replay function substitutions on every selected copy of an E2fsprogs module."""
# SPDX-License-Identifier: LGPL-2.0-only
from hashlib import sha256
import json


def selected_module(crate, sources, suffix, transform):
    module, = [m for m in sources if m.endswith(suffix)]
    data = (crate / module).read_bytes()
    if sha256(data).hexdigest() != sources[module]:
        raise ValueError("E2fsprogs module differs from its compiler input")
    new, facts = transform(data)
    return {module: new}, dict(facts, module=module)


def inventory(link, suffix, transform):
    from audit_linked_pointers import measure

    raw = link.read_bytes()
    release = json.loads(raw)
    archives = {}
    def inspect(archive, module, checksum, source):
        if not str(module).endswith(suffix):
            return
        key = str(archive)
        if key in archives or sha256(source).digest() != checksum:
            raise ValueError("duplicate selected module or stale compiler input")
        _, facts = transform(source)
        archives[key] = dict(facts, module=str(module), archive_sha256=release["source_library_sha256"][key])
    measure(release, inspect_module=inspect)
    if not archives or raw != link.read_bytes():
        raise ValueError("empty source inventory or changed release")
    return dict(archives=archives, link_sha256=sha256(raw).hexdigest(), binary_sha256=release["binary"]["sha256"],
                source_pointer_types_removed=sum(row["raw_pointer_types_removed"] for row in archives.values()))

