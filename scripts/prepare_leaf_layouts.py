#!/usr/bin/env python3
"""Replay and enroll identical C-layout definitions shared within one compiled archive."""
# SPDX-License-Identifier: 0BSD
from build_leaf_layout_pilot import substitute
from cargo_source_parent import cargo_origin, direct_crate


def selection(row):
    return {name: {field: spec[field] for field in ("copies", "fingerprint", "pointer_fields")}
            for name, spec in row["leaf_layouts"].items()}


def replay_layer(parent, read_parent, row, tool):
    from build_scalar_ffi import replay_layer as replay_sources
    return replay_sources(parent, read_parent, row, tool,
                          transform=lambda crate, sources, scan: substitute(crate, sources, selection(row), scanner=scan))


def rebuild(link_path, link, key, output, row, mounted_direct):
    layouts = selection(row)
    if direct_crate(cargo_origin(link, key)) is None:
        if mounted_direct:
            raise ValueError("expected a direct-rustc leaf layout archive")
        from build_leaf_layout_pilot import build
        build(link_path, key, layouts, output)
    elif mounted_direct:
        from build_staged_c_strings import compile_archive
        output.mkdir()
        compile_archive(link_path, output, key, leaf_layouts=layouts)
    else:
        from build_staged_c_strings import build
        build(link_path, output, key, leaf_layouts=layouts)


if __name__ == "__main__":
    from prepare_identical_archives import main
    main("shared_leaf_layouts")
