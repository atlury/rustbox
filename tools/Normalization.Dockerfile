ARG BASE_IMAGE=rustbox-tools:2026-11-19
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG C2RUST_RUST_TOOLCHAIN=nightly-2023-04-15

# Tools with distinct jobs in the normalization gate: ABI comparison, DWARF
# layout inspection, and automatic reduction of translator/analyzer failures
# to minimal reproducible inputs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      abigail-tools=2.4-3build1 \
      abi-compliance-checker=2.3-2 \
      abi-dumper=1.2-3 \
      creduce=2.11.0~20240312-1build1 \
      cvise=2.10.0-1ubuntu1 \
      dwarves=1.25-0ubuntu3 \
 && rm -rf /var/lib/apt/lists/*

# C2Rust 0.22.1 emits the historical core::ffi VaList API and declares this
# exact nightly in generated rust-toolchain.toml.  Keep it beside, not instead
# of, Rustbox's current stable toolchain so raw-output compilation is measured
# without repair.
RUN rustup toolchain install "${C2RUST_RUST_TOOLCHAIN}" --profile minimal

COPY tools/normalization-tool-report.sh /usr/local/bin/rustbox-normalization-tool-report
CMD ["rustbox-normalization-tool-report"]
