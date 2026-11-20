ARG BASE_IMAGE=rustbox-sed:2026-11-20
FROM ${BASE_IMAGE}

# GNU Diffutils 3.12 has no package-specific build or runtime dependency.
# Keep a named layer so every oracle and translation command uses one frozen
# environment that can evolve independently of the earlier utility slices.
