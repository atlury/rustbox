ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# acl carries its libacl and filesystem-walk support in the signed source
# release.  A named image keeps its otherwise shared toolchain immutable.
