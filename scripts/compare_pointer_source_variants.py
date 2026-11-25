#!/usr/bin/env python3
"""Explain changes in the raw-pointer inventory when identical compiler inputs are counted once."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from audit_linked_pointers import METRICS, measure


def snapshot(path, tokens):
    raw = path.read_bytes()
    sources = {}
    def collect(archive, module, checksum, data):
        key = str(archive), str(module)
        if key in sources:
            raise ValueError("duplicate Cargo compiler input")
        sources[key] = checksum
        if checksum not in tokens:
            tokens[checksum] = len(METRICS["raw_pointer_type_tokens"].findall(data))
    inventory = measure(json.loads(raw), inspect_module=collect)
    if path.read_bytes() != raw:
        raise ValueError("link changed during source audit")
    return sources, inventory, sha256(raw).hexdigest()


def compare(parent, selected):
    tokens = {}
    old, before, parent_sha = snapshot(parent, tokens)
    new, after, link_sha = snapshot(selected, tokens)
    if old.keys() != new.keys():
        raise ValueError("this comparison requires the same archive and module paths")
    changes = {k for k in old if old[k] != new[k]}
    originals, candidates = set(old.values()), set(new.values())
    added, retired = candidates - originals, originals - candidates
    net_distinct = sum(tokens[h] for h in added) - sum(tokens[h] for h in retired)
    net_all = sum(tokens[new[k]] - tokens[old[k]] for k in changes)
    metric = "raw_pointer_type_tokens"
    if (net_distinct != after["counting_identical_files_once"][metric] - before["counting_identical_files_once"][metric]
            or net_all != after["all"][metric] - before["all"][metric]
            or len(added) - len(retired) != after["unique_files"] - before["unique_files"]):
        raise ValueError("computed change does not reproduce the complete inventory")
    variants = defaultdict(set)
    for key in old:
        variants[old[key]].add(new[key])
    split = {h: targets for h, targets in variants.items() if len(targets) > 1}
    by_package = Counter(Path(archive).name for archive, module in changes)
    return dict(parent_link_sha256=parent_sha, selected_link_sha256=link_sha, changed_compiler_inputs=len(changes),
                changed_archives=len(by_package), raw_pointer_type_difference=net_all,
                distinct_pointer_type_difference=net_distinct, distinct_files_before=before["unique_files"],
                distinct_files_after=after["unique_files"], added_distinct_files=len(added), retired_distinct_files=len(retired),
                pointer_types_in_added_files=sum(tokens[h] for h in added), pointer_types_in_retired_files=sum(tokens[h] for h in retired),
                originals_with_multiple_resulting_versions=len(split), splits_retaining_original=sum(h in targets for h, targets in split.items()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("selected", type=Path)
    a = p.parse_args()
    print(json.dumps(compare(a.parent, a.selected), sort_keys=True, indent=2))
