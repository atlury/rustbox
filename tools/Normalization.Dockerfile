ARG BASE_IMAGE=rustbox-tools:2026-11-19
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

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

COPY tools/normalization-tool-report.sh /usr/local/bin/rustbox-normalization-tool-report
CMD ["rustbox-normalization-tool-report"]
