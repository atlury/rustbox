"""Identify the Cargo target and previously verified source substitutions for a linked archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path


def cargo_origin(link, key):
    from curl_manual_archive import KEY, candidate_path
    from iproute2_route_name_archives import netlink_path
    selected = Path(key)
    if record := link.get("curl_manual"):
        if candidate_path(record["pilot"]) == selected:
            return Path(KEY)
    for original, row in link.get("iproute2_netlink_protocols", {}).items():
        if netlink_path(row) == selected:
            return Path(original)
    return selected


def pinned_parent(key, row):
    """Reconstruct exactly the preceding link fields needed for a standalone cold rebuild."""
    original = row.get("cargo_archive", key)
    if original == key:
        return {"source_library_sha256": {key: row["control_sha256"]}}
    from curl_manual_archive import KEY, candidate_path, pinned
    import iproute2_route_name_archives as routes
    if original == KEY:
        previous = pinned()
        prior = previous["pilot"]
        link = {"curl_manual": previous, "source_library_sha256": {str(candidate_path(prior)): prior["candidate_sha256"]}}
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
