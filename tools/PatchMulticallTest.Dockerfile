FROM rustbox-patch:2026-11-20 AS patch_oracle
FROM rustbox-e2fsprogs:2026-11-24
# The canonical ed-style test needs GNU ed at the configured absolute path.
COPY --from=patch_oracle /usr/bin/ed /usr/bin/ed
RUN /usr/bin/ed --version
