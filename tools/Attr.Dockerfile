ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# attr has no package-specific build dependency beyond the shared
# normalization image.  Keep a named layer so its toolchain remains pinned
# independently as later packages evolve.
