"""Identify the Cargo target and previously verified source substitutions for a linked archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path


def cargo_origin(link, key):
    from curl_manual_archive import KEY, candidate_path
    from iproute2_route_name_archives import netlink_path
    selected = Path(key)
    import stage_dsfield_archives as dsfield
    for prior, row in link.get(dsfield.FIELD, {}).items():
        if dsfield.candidate_path(row) == selected:
            selected = Path(prior)
            break
    from stage_routing_protocol_archives import FIELD, candidate_path as routing_path
    for prior, row in link.get(FIELD, {}).items():
        if routing_path(row) == selected:
            selected = Path(prior)
            break
    from tar_timespec_archive import selection as tar
    from bison_length_archive import selection as bison
    from lz4_dictionary_archive import selection as lz4
    for layer in (tar, bison, lz4):
        if (record := link.get(layer.field)) and layer.candidate_path(record["pilot"]) == selected:
            return Path(layer.key)
    if record := link.get("curl_manual"):
        if candidate_path(record["pilot"]) == selected:
            return Path(KEY)
    for original, row in link.get("iproute2_netlink_protocols", {}).items():
        if netlink_path(row) == selected:
            return Path(original)
    from e2fsprogs_dirhash_archives import candidate_path as array_path
    for original, row in link.get("e2fsprogs_dirhash_arrays", {}).items():
        if array_path(Path(original), row["candidate_sha256"]) == selected:
            return Path(original)
    return selected


def archives_by_origin(parent):
    by_origin = {}
    for key in parent["source_library_sha256"]:
        if not key.endswith(".a"):
            continue
        origin = str(cargo_origin(parent, key))
        if origin in by_origin:
            raise ValueError("ambiguous linked origin " + origin)
        by_origin[origin] = key
    return by_origin


def row_origin(row):
    return row.get("rustc_archive", row.get("cargo_archive", row["archive"]))


def direct_crate(archive):
    from build_e2fsprogs_checksums import CONSUMERS
    from e2fsprogs_foreign_declarations import is_bridge
    if is_bridge(archive):
        return archive.parents[1] / "bridge/bridge-final"
    name = archive.parent.name
    if (len(archive.parts) == 7 and archive.parts[:2] == ("work", "analysis")
            and archive.parts[2].startswith("e2fsprogs-") and archive.parts[3:5] == ("program-translations", "rustbox-e2fsprogs-shared")
            and name in CONSUMERS and archive.name == f"lib{name}_audit.a"):
        return archive.parents[2] / name / f"{name}-final"
    return None


def pinned_parent(key, row):
    """Reconstruct exactly the preceding link fields needed for a standalone cold rebuild."""
    original = row_origin(row)
    if Path(key).parent.parent.name == "dsfield-names":
        import stage_dsfield_archives as dsfield
        link = dsfield.select(dsfield.parent_build_link())
        if str(cargo_origin(link, key)) != original or link["source_library_sha256"].get(key) != row["control_sha256"]:
            raise ValueError("staged DS field archive differs from its qualified parent")
        return link
    if Path(key).parent.parent.name == "routing-protocols":
        from stage_routing_protocol_archives import parent_build_link, select
        link = select(parent_build_link())
        if (str(cargo_origin(link, key)) != original
                or link["source_library_sha256"].get(key) != row["control_sha256"]):
            raise ValueError("staged routing archive differs from its qualified parent")
        return link
    if original == key:
        return {"source_library_sha256": {key: row["control_sha256"]}}
    from curl_manual_archive import KEY, candidate_path, pinned
    import iproute2_route_name_archives as routes
    from tar_timespec_archive import selection as tar
    from bison_length_archive import selection as bison
    from lz4_dictionary_archive import selection as lz4
    layers = {layer.key: layer for layer in (tar, bison, lz4)}
    if original in layers:
        layer = layers[original]
        previous = layer.pinned()
        prior = previous["pilot"]
        link = {layer.field: previous, "source_library_sha256": {str(layer.candidate_path(prior)): prior["candidate_sha256"]}}
        for field, receipt in previous["parent_receipts"].items():
            link[field] = {original: receipt}
    elif original == KEY:
        previous = pinned()
        prior = previous["pilot"]
        link = {"curl_manual": previous, "source_library_sha256": {str(candidate_path(prior)): prior["candidate_sha256"]}}
    elif Path(original).parent.parent.name == "rustbox-e2fsprogs-shared":
        import json
        from check_cargo_private_inlines import ROOT
        from e2fsprogs_dirhash_archives import candidate_path as array_path
        prior = json.loads((ROOT / "batches/e2fsprogs-trie-arrays.json").read_bytes())[original]
        link = {"source_library_sha256": {str(array_path(Path(original), prior["candidate_sha256"])): prior["candidate_sha256"]},
                "e2fsprogs_dirhash_arrays": {original: prior}}
        for field, item in (("linked_private_inline_proofs", "inlines"), ("linked_second_inline_proofs", "second_inlines"),
                            ("linked_foreign_declaration_proofs", "declarations")):
            if prior[item]:
                link[field] = {original: prior[item]}
    else:
        rows = routes.manifest(netlink=True)
        if original not in rows:
            raise ValueError("unrecognized staged Cargo source path")
        prior = rows[original]
        link = routes.parent_build_link(netlink=True)
        link.update(iproute2_netlink_protocols=rows,
                    source_library_sha256={str(routes.netlink_path(r)): r["candidate_sha256"] for r in rows.values()})
    if (str(cargo_origin(link, key)) != original or link["source_library_sha256"].get(key) != row["control_sha256"]
            or prior["candidate_sha256"] != row["control_sha256"]):
        raise ValueError("staged archive differs from its canonical parent")
    return link
