ARG BASE_IMAGE=rustbox-patch:2026-11-20
FROM ${BASE_IMAGE}

# GNU sed 4.10 needs no package-specific runtime dependency.  This layer is
# intentionally separate so its build environment remains reproducible.

