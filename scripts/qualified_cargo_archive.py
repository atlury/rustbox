"""Check and materialize a pinned Cargo archive that changes the linked executable."""
# SPDX-License-Identifier: curl
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest

PROOFS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")


@dataclass(frozen=True)
class QualifiedArchive:
    key: str
    field: str
    directory: str
    manifest: Path
    evidence: Path

    def candidate_path(self, row):
        if row["archive"] != self.key or not re.fullmatch(r"[a-f0-9]{64}", row["candidate_sha256"]):
            raise ValueError(f"unexpected {self.field} archive")
        path = Path(self.key)
        return path.parents[1] / self.directory / row["candidate_sha256"] / path.name

    def receipts(self, link):
        return {name: link[name][self.key] for name in PROOFS if self.key in link.get(name, {})}

    def pinned(self):
        record = json.loads(self.manifest.read_bytes())
        tested = json.loads(self.evidence.read_bytes())
        row = record["pilot"]
        self.candidate_path(row)
        if any(tested[k] != v for k, v in row.items()):
            raise ValueError(f"{self.field} manifest differs from the qualified pilot")
        return record

    def validate_parent(self, link, record):
        if (link["source_library_sha256"].get(self.key) != record["pilot"]["control_sha256"]
                or self.receipts(link) != record["parent_receipts"]):
            raise ValueError(f"{self.field} archive or compiler proof differs from its qualified parent")

    def parent_view(self, link):
        if self.field not in link:
            return link
        record = link[self.field]
        if record != self.pinned():
            raise ValueError(f"unrecognized {self.field} substitution")
        row = record["pilot"]
        hashes = link["source_library_sha256"].copy()
        if self.key in hashes or hashes.pop(str(self.candidate_path(row)), None) != row["candidate_sha256"]:
            raise ValueError(f"ambiguous or stale {self.field} archive")
        hashes[self.key] = row["control_sha256"]
        parent = dict(link, source_library_sha256=hashes)
        del parent[self.field]
        self.validate_parent(parent, record)
        return parent

    def prepare(self, record, build, built=None):
        row = record["pilot"]
        destination = ROOT / self.candidate_path(row)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=destination.parent) as tmp:
                scratch = Path(tmp)
                if built is None:
                    link = {"binary": {"sha256": row["control_binary_sha256"]},
                            "source_library_sha256": {self.key: row["control_sha256"]},
                            **{name: {self.key: proof} for name, proof in record["parent_receipts"].items()}}
                    source = scratch / "parent.json"
                    source.write_text(json.dumps(link))
                    build(source, scratch / "pilot")
                    if json.loads((scratch / "pilot/pilot.json").read_bytes()) != row:
                        raise ValueError(f"cold {self.field} build differs from the qualified pilot")
                    built = scratch / "pilot" / destination.name
                if digest(built) != row["candidate_sha256"]:
                    raise ValueError(f"unexpected {self.field} archive bytes")
                staged = scratch / destination.name
                shutil.copyfile(built, staged)
                staged.replace(destination)
        if digest(destination) != row["candidate_sha256"]:
            raise ValueError(f"cached {self.field} archive differs from manifest")
