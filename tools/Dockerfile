FROM ubuntu@sha256:73b999393d07f2bf65a40373778a44dc9a6d54ad7718d29247d8ff9413c4d6a8

ARG DEBIAN_FRONTEND=noninteractive
ARG RUST_VERSION=1.99.0
ARG RUSTUP_SHA256=b1c8cb14e30889e7e2999e6b69e62d9e9b9ffc0f4df8180564d306d9680e6c55
ARG C2RUST_VERSION=0.22.1
ARG COCCINELLE_TAG=1.3.3
ARG COCCINELLE_COMMIT=11b93adb6516a358a6687051e5762136666626e0
ARG CODECHECKER_VERSION=6.29.3

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      afl++ autoconf automake autopoint bear bison build-essential \
      ca-certificates clang-18 clang-tidy-18 clang-tools-18 cmake cppcheck \
      curl file flawfinder gdb gettext git gperf help2man jq lcov ltrace \
      llvm-18-dev libclang-18-dev libacl1-dev libattr1-dev libaudit-dev \
      libcap-dev libcrypt-dev libeconf-dev libgmp-dev libmagic-dev \
      libncurses-dev libpam0g-dev libpcre3-dev libpython3-dev \
      libreadline-dev libselinux1-dev libssl-dev libudev-dev libzstd-dev \
      meson ninja-build ocaml ocaml-findlib menhir pkg-config python3 \
      python3-pip python3-venv sparse splint strace texinfo valgrind xz-utils \
 && rm -rf /var/lib/apt/lists/*

RUN curl --fail --location --retry 3 \
      --output /tmp/rustup-init \
      https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu/rustup-init \
 && echo "${RUSTUP_SHA256}  /tmp/rustup-init" | sha256sum --check --strict \
 && chmod +x /tmp/rustup-init \
 && /tmp/rustup-init -y --profile minimal --default-toolchain "${RUST_VERSION}" \
 && rm /tmp/rustup-init

ENV PATH=/root/.cargo/bin:/opt/codechecker/bin:/usr/lib/llvm-18/bin:${PATH}
ENV LLVM_CONFIG_PATH=/usr/bin/llvm-config-18
ENV LIBCLANG_PATH=/usr/lib/llvm-18/lib

RUN cargo install --locked --version "${C2RUST_VERSION}" c2rust \
 && rm -rf /root/.cargo/registry /root/.cargo/git

ENV RUSTUP_TOOLCHAIN=1.99.0

COPY tools/codechecker-requirements.lock /tmp/codechecker-requirements.lock
RUN grep -qx "codechecker==${CODECHECKER_VERSION}" /tmp/codechecker-requirements.lock \
 && python3 -m venv /opt/codechecker \
 && /opt/codechecker/bin/pip install --no-cache-dir \
      --requirement /tmp/codechecker-requirements.lock \
 && /opt/codechecker/bin/pip check \
 && rm /tmp/codechecker-requirements.lock

RUN git clone --depth 1 --branch "${COCCINELLE_TAG}" \
      https://github.com/coccinelle/coccinelle.git /tmp/coccinelle \
 && test "$(git -C /tmp/coccinelle rev-parse HEAD)" = "${COCCINELLE_COMMIT}" \
 && cd /tmp/coccinelle \
 && ./autogen \
 && ./configure --prefix=/usr/local --disable-python \
 && make -j"$(nproc)" \
 && make install \
 && rm -rf /tmp/coccinelle

# Runtime fixtures needed to exercise the canonical GNU test suites rather
# than silently skipping ACL, capability, terminal, and locale cases.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      acl attr gnupg libcap2-bin libexpect-perl locales \
      python-is-python3 python3-inotify python3-pyinotify \
 && localedef -i en_US -f UTF-8 en_US.UTF-8 \
 && localedef -i fr_FR -f ISO-8859-1 fr_FR \
 && localedef -i fr_FR -f UTF-8 fr_FR.UTF-8 \
 && localedef -i tr_TR -f UTF-8 tr_TR.UTF-8 \
 && localedef -i ja_JP -f EUC-JP ja_JP.EUC-JP \
 && localedef -i zh_CN -f GB18030 zh_CN.GB18030 \
 && localedef -i sv_SE -f UTF-8 sv_SE.UTF-8 \
 && localedef -i sv_SE -f ISO-8859-1 sv_SE \
 && localedef -i fi_FI -f UTF-8 fi_FI.UTF-8 \
 && localedef -i ga_IE -f UTF-8 ga_IE.UTF-8 \
 && localedef -i gv_GB -f UTF-8 gv_GB.UTF-8 \
 && localedef -i ar_SY -f UTF-8 ar_SY.UTF-8 \
 && localedef -i am_ET -f UTF-8 am_ET.UTF-8 \
 && localedef -i fa_IR -f UTF-8 fa_IR.UTF-8 \
 && localedef -i th_TH -f UTF-8 th_TH.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

# Canonical util-linux coverage: setpriv and lastlog2 are optional only when
# their development libraries are unavailable.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libcap-ng-dev libsqlite3-dev \
 && rm -rf /var/lib/apt/lists/*

# Keep CodeChecker callable without letting its private Python shadow the
# system interpreter used by canonical upstream test harnesses.
ENV PATH=/root/.cargo/bin:/usr/lib/llvm-18/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/codechecker/bin

COPY tools/tool-report.sh /usr/local/bin/rustbox-tool-report

WORKDIR /work
CMD ["rustbox-tool-report"]

