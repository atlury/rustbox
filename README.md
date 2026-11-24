# Rustbox

Rustbox is a single Rust multicall binary built by mechanically normalizing,
translating, and differentially verifying canonical Linux utility sources.
It is a new project; no applet is considered complete merely because it
compiles.

The initial authoritative source releases are:

- GNU Coreutils 9.12, released September 14, 2026;
- util-linux 2.42.4, released September 21, 2026;
- GNU sed 4.10, released November 13, 2025.

Their release archives, signatures, and SHA-256 digests are pinned in
`upstream/releases.json`.  Downloaded source remains outside Git and serves as
an immutable oracle.

## Multicall interface

The final product is one `rustbox` executable.  It supports both forms:

```text
rustbox APPLET [ARGUMENT]...
APPLET [ARGUMENT]...       # through a rustbox symlink
```

Shared parsing, diagnostics, locale, filesystem, process, and output machinery
is linked once.  Separate binaries may be produced temporarily only as test or
translation fixtures.

## Bootstrap

```sh
python3 scripts/fetch_upstreams.py
python3 scripts/verify_signatures.py
cargo test
cargo build --profile size
```

See `docs/WORKFLOW.md` for the normalization, translator selection, repair
scoring, and correctness gates.

## Current progress

| Upstream | Inventory | Pinned source oracle | Hybrid canonical parity | Integrated Rust applets |
|---|---:|---:|---:|---:|
| GNU Coreutils 9.12 | 108 | 108 | 106 | 106 |
| util-linux 2.42.4 | 155 | 155 | 155 | 155 |
| GNU M4 1.4.21 | 1 | 1 | 1 | 1 |
| pkgconf 3.0.11 | 5 | 5 | 5 | 5 |
| File 5.48 | 1 | 1 | 1 | 1 |
| GNU patch 2.8 | 1 | 1 | 1 | 1 |
| GNU sed 4.10 | 1 | 1 | 1 | 1 |
| GNU Diffutils 3.12 | 4 | 4 | 4 | 4 |
| GNU Grep 3.12 | 3 | 3 | 3 | 3 |
| GNU bc 1.08.2 / dc 1.5.2 | 2 | 2 | 2 | 2 |
| attr 2.6.0 | 3 | 3 | 3 | 3 |
| acl 2.4.0 | 3 | 3 | 3 | 3 |
| LZ4 1.11.1 | 4 | 4 | 4 | 4 |
| GNU Gzip 1.14 | 14 | 14 | 14 | 14 |
| Less 710 | 2 | 2 | 2 | 2 |
| XZ Utils 5.8.4 | 23 | 23 | 23 | 23 |
| zstd 1.5.7 | 6 | 6 | 6 | 6 |
| GNU tar 1.35 | 2 | 2 | 2 | 2 |
| Ncurses 6.6 | 11 | 11 | 11 | 11 |
| GNU Findutils 4.10.0 | 4 | 4 | 4 | 4 |
| GNU Gawk 5.4.0 | 3 | 3 | 3 | 3 |
| Flex 2.6.4 | 3 | 3 | 3 | 3 |
| Bison 3.8.2 | 2 | 2 | 2 | 2 |
| curl 8.23.0 | 2 | 2 | 2 | 2 |
| GNU Inetutils 2.8 | 26 | 26 | 26 | 26 |
| Kmod 34.3 | 7 | 7 | 7 | 7 |
| Procps-ng 4.0.7 | 20 | 20 | 20 | 20 |
| Shadow 4.20.4 | 32 | 32 | 32 | 32 |
| IPRoute2 7.3.0 | 21 | 21 | 21 | 21 |
| E2fsprogs 1.47.4 | 32 | 32 | 32 | 32 |

The Coreutils oracle and its local test evidence are recorded in
`evidence/coreutils-9.12-oracle.json`.  The complete canonical static-analysis
baseline is in `evidence/coreutils-9.12-static-analysis.json`; translation and
hybrid evidence for the verified batches is in
`evidence/coreutils-9.12-c2rust-small-01.json`,
`evidence/coreutils-9.12-c2rust-small-02.json`,
`evidence/coreutils-9.12-c2rust-small-03.json`,
`evidence/coreutils-9.12-c2rust-small-04.json`,
`evidence/coreutils-9.12-c2rust-small-05.json`,
`evidence/coreutils-9.12-c2rust-small-06.json`,
`evidence/coreutils-9.12-c2rust-small-07.json`,
`evidence/coreutils-9.12-c2rust-small-08.json`,
`evidence/coreutils-9.12-c2rust-small-09.json`,
`evidence/coreutils-9.12-c2rust-small-10.json`,
`evidence/coreutils-9.12-c2rust-small-11.json`,
`evidence/coreutils-9.12-c2rust-small-12.json`,
`evidence/coreutils-9.12-c2rust-small-13.json`,
`evidence/coreutils-9.12-c2rust-small-14.json`,
`evidence/coreutils-9.12-c2rust-small-15.json`,
`evidence/coreutils-9.12-c2rust-small-16.json`,
`evidence/coreutils-9.12-c2rust-small-17.json`,
`evidence/coreutils-9.12-c2rust-small-18.json`,
`evidence/coreutils-9.12-c2rust-small-19.json`,
`evidence/coreutils-9.12-c2rust-small-20.json`,
`evidence/coreutils-9.12-c2rust-small-21.json`,
`evidence/coreutils-9.12-c2rust-small-22.json`, and
`evidence/coreutils-9.12-c2rust-small-23.json`.  All 106 applets in scope under
the no-SELinux policy have reached hybrid canonical parity and are integrated.
Both `chcon` and `runcon` are excluded because their purpose is SELinux policy
management.  An oracle-built applet is not marked complete in the inventory
below; completion is reserved for translated Rust that has reached canonical
behavioral parity through the multicall interface.

The signed util-linux oracle is recorded in
`evidence/util-linux-2.42.4-oracle.json`.  Its 155 public names comprise 132
canonical executables and 23 upstream aliases.  The build explicitly excludes
SELinux, systemd, audit, udev, Python bindings, and PAM lastlog integration;
it retains the ordinary non-SELinux implementations, including `mkfifo`-like
filesystem functionality elsewhere in Rustbox.  `setpriv`, `lastlog2`, and the
legacy `raw` utility are deliberately enabled rather than silently omitted.
The paired Clang/GCC command inventory is recorded in
`evidence/util-linux-2.42.4-compdb.json`.  Translation, normalization,
hybrid-link, differential, upstream-test, and Valgrind evidence for all
fourteen batches is in `evidence/util-linux-2.42.4-c2rust-small-01.json`,
`evidence/util-linux-2.42.4-c2rust-small-02.json`,
`evidence/util-linux-2.42.4-c2rust-small-03.json`,
`evidence/util-linux-2.42.4-c2rust-small-04.json`,
`evidence/util-linux-2.42.4-c2rust-small-05.json`,
`evidence/util-linux-2.42.4-c2rust-small-06.json`,
`evidence/util-linux-2.42.4-c2rust-small-07.json`,
`evidence/util-linux-2.42.4-c2rust-small-08.json`,
`evidence/util-linux-2.42.4-c2rust-small-09.json`,
`evidence/util-linux-2.42.4-c2rust-small-10.json`,
`evidence/util-linux-2.42.4-c2rust-small-11.json`,
`evidence/util-linux-2.42.4-c2rust-small-12.json`,
`evidence/util-linux-2.42.4-c2rust-small-13.json`, and
`evidence/util-linux-2.42.4-c2rust-small-14.json`.  All 155 in-scope
util-linux applets have reached hybrid canonical parity and are integrated.

The single combined executable and its collision-isolation manifest are
recorded in `evidence/rustbox-multicall.json`.  One binary dispatches all 499
distinct public names (106 Coreutils, 155 util-linux applets, GNU M4, five
pkgconf names, File, GNU patch, GNU sed, four GNU Diffutils applets, and GNU
Grep's three public names, GNU bc and dc, attr's three tools, plus chacl,
getfacl, and setfacl, plus LZ4's four public names, Less and lessecho, and all
fourteen GNU Gzip interfaces, all 23 XZ Utils names, zstd's six public names,
GNU `tar` and `rmt`, eleven Ncurses names including native
`ncursesw6-config`, GNU Findutils' `find`, `xargs`,
`locate`, and `updatedb`; `kill` is shared and `util-linux-kill` remains
available explicitly, GNU Gawk's `gawk`, `awk`, and native `gawkbug`, and
Flex's `flex`, `flex++`, and native `lex` compatibility frontend, and GNU
Bison's `bison` and native `yacc` compatibility frontend, curl and its
native `curl-config` frontend, plus all 26 GNU Inetutils programs; Inetutils
`hostname` and `logger` use the explicit `inetutils-hostname` and
`inetutils-logger` names to preserve existing dispatcher precedence, plus all
seven Kmod frontends: `kmod`, `depmod`, `insmod`, `lsmod`, `modinfo`,
`modprobe`, and `rmmod`, plus all 20 Procps-ng programs; `kill` and `uptime`
retain GNU Coreutils precedence while `procps-kill` and `procps-uptime` expose
the Procps-ng implementations explicitly, plus all 32 Shadow names; the eight
names already owned by util-linux are available as `shadow-chfn`,
`shadow-chsh`, `shadow-login`, `shadow-newgrp`, `shadow-nologin`, `shadow-su`,
`shadow-vigr`, and `shadow-vipw`), plus all 21 IPRoute2 public names: 18
translated engines, the `ctstat` and `rtstat` aliases, and native in-process
`routel`, plus all 32 E2fsprogs names: 20 translated engines, eight canonical
aliases, and four native generator/scrub frontends).  It passes all 884
help/version oracle comparisons, all 14,022 cases in the 38 original batch
differential harnesses, and M4's full 242-check language suite, stack-overflow
check, 108-case differential suite, and Valgrind.  Pkgconf also passes all 429
CLI fixture checks, 55 exact differential comparisons, and Valgrind through
the unified dispatcher.  Sed passes its complete 362-case upstream replay,
30 exact differential comparisons, and Valgrind through the same dispatcher.
Diffutils passes its complete 377-case upstream replay, 48 exact differential
comparisons, and resource checks through the same dispatcher.  Grep passes
its complete 443-case upstream replay, 36 exact differential comparisons, and
the canonical allocation lifecycle through the same dispatcher.  GNU bc and
dc pass all 18 shipped arbitrary-precision workloads, 46 exact differential
comparisons, and canonical allocation lifecycles through the same dispatcher.
Attr's three tools retain their upstream result, 22 exact differential cases,
and canonical allocation lifecycles through the same dispatcher.  ACL's three
tools retain 13 upstream passes and two canonical NFS expected failures, all
30 state-aware differential cases, and leak-free translated allocation
lifecycles through the same dispatcher.  LZ4 passes all 27 byte-and-filesystem
differential cases, its complete upstream essentials suite, and leak-free
resource checks through the same dispatcher.  GNU Gzip's translated native
engine and thirteen native frontend names pass all 108 relevant byte,
filesystem, failure, help, and version
comparisons and emit byte-identical compressed streams.  The Gzip engine and
comparison frontends have zero lost bytes; `zgrep` matches GNU Grep's canonical
allocation lifecycle exactly, while `zmore` frees every allocation in its
internal Gzip-to-`more` pipeline and `zless` does the same through the
integrated Less engine; `znew` also frees every allocation while
recompressing.  `gzexe` emits the exact canonical 932-byte launcher, executes
and decompresses its result, and frees all allocations.  XZ Utils adds all 23
physical, compatibility, comparison, search, and pager names without installing
its shell scripts.  Its native frontends pipe the translated XZ engine into the
already integrated Diffutils, Grep, Less, and util-linux `more` implementations.
All 70 public comparisons pass, `.xz` compression is byte-identical,
decompression matches, and Valgrind reports zero errors and no lost bytes.  The
GNU Gawk's three integrated names pass all 26 engine behavioral comparisons,
including CSV, MPFR, NUL input, redirection, and translated extension loading,
plus six stateful `gawkbug` editor, mail, and recovery workflows.
The zstd native engine and native `zstdgrep`/`zstdless` frontends pass all 17
public comparisons, emit byte-identical frames, and free every allocation in
both Valgrind directions.  GNU tar and rmt add all 18 archive, extraction,
compression-personality, and remote-protocol comparisons plus four zero-error,
zero-loss Valgrind paths.  Their ACL calls resolve to Rustbox's translated ACL
archive, including Coreutils' existing ACL consumers, and `libacl.so` is absent
from the ELF dependency set.  Flex adds all three public names with all 114
upstream tests, 14 generator/scanner comparisons, three frontend comparisons,
and four leak-free resource paths.  GNU Inetutils adds all 26 clients and
daemons with 133/133 exact behavioral comparisons and 26 clean Valgrind paths.
Kmod adds all seven frontends from a complete 26-source stable translation with
no canonical C residue; all 25 command and module-fixture comparisons pass and
all seven multicall Valgrind paths are clean.
Procps-ng adds all 20 programs from a complete 49-source translation with no
canonical C residue; all 51 canonical comparisons pass and all 20 resource
paths match their canonical baselines.  Shadow adds all 32 public names from a
complete 196-source strict translation with no canonical C residue; all 79
canonical comparisons and all 32 resource paths pass through the combined
binary.  IPRoute2 passes all 66 global canonical comparisons, including six
real-kernel `routel` cases, and all 21 Valgrind paths; exact integration
evidence is in `evidence/iproute2-7.3.0-multicall.json`.  The resulting
E2fsprogs integration passes 112/112 canonical comparisons and all 32
Valgrind paths; its 20 private namespaces rename 8,979 symbols after removing
3,966 byte-identical Rust runtime members already provided by Procps-ng.
Exact evidence is in `evidence/e2fsprogs-1.47.4-multicall.json`.  The resulting
499-name executable is 43,189,360 bytes unstripped and 25,216,304 bytes
stripped. Sharing the Coreutils runtime with Gzip saved 289,264 stripped
bytes. The linker compares 328 archive members byte-for-byte before sharing
them. The exact hashes and
section/link evidence are recorded in `evidence/rustbox-multicall.json`.
`chcon` and `runcon`
remain absent, and the linked binary has no SELinux or systemd dependency.

The final Rustbox executable is required to be self-contained: utility
implementations and any required support code must be linked into the one
multicall artifact, with no runtime dependency on package shared libraries.
The release gate will require a fully static ELF with no `DT_NEEDED` entries;
dynamic canonical builds remain permitted only as independent test oracles.
After utility coverage and static parity are complete, hardening proceeds in
separate behavior-preserving phases: eliminate raw pointers and `unsafe`, then
replace `std` with Rustbox-owned `no_std` runtime facilities.  Pointer and
`unsafe` inventories are recorded now, but they do not block the current
utility-completion tranche.

### Post-applet hardening queue

All 499 public names have reached multicall integration. The current Linux
build still has 34 dynamic dependencies.

On the pinned x86-64 Linux build, GNU ld packed relative relocations (DT_RELR)
reduce the stripped ELF from 25,216,304 to 23,836,024 bytes and preserve PIE.
This optional build requires a loader providing `GLIBC_ABI_DT_RELR`. The
experiment replays the link map and checks that a control link reproduces
the stripped default binary's SHA-256. The packed binary reproduced SHA-256
`08e4f880c1c1d2188d9dc868b83bed252b0e945be300edf8d4edecced6175bbf`
on two links and passed 884 dispatcher comparisons, 112 E2fsprogs
comparisons, and 32 E2fsprogs Valgrind checks. Run it from the repository root with
a fresh output directory.

```sh
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 scripts/run_tool.sh \
  python3 /work/scripts/measure_packed_relocations.py \
  /rustbox-coreutils/canonical-clang-no-security-compdb /work/work/analysis/packed
scripts/test_rustbox_multicall.sh /work/work/analysis/packed/rustbox /work/work/analysis/packed/dispatch.json
scripts/test_e2fsprogs_multicall.sh /work/work/analysis/packed/rustbox
```

1. Eliminate all remaining package shared-library dependencies and require a
   fully static multicall ELF with zero `DT_NEEDED` entries.
2. Measure archive, section, symbol, relocation, and reachable-code costs;
   consolidate duplicate runtimes and apply release LTO, section GC, and
   symbol-visibility controls before setting the final size budget.
3. Remove translated raw pointers and `unsafe` incrementally behind the same
   canonical behavior gates used during translation.
4. Replace `std` with Rustbox-owned `no_std` facilities without changing the
   applet ABI or observable behavior.
5. Re-run every upstream suite, differential case, sanitizer, analyzer,
   Valgrind, static-link, and stripped-size gate on the hardened artifact.

#### Pointer safety pilot

The first substitution covers E2fsprogs 1.47.4 `ext2fs_crc16`. The same
generated module occurs in 13 finalized engine crates, and the baseline link
map retains 12 copies of its lookup table. The pilot builds one candidate
`e2fsck` with the generated definition removed before optimization. It links
the safe slice implementation in `compat/e2fsprogs/crc16.rs` through one
C ABI adapter. Only the adapter constructs a slice from a raw pointer.
A zero-length call accepts null and returns all 32 bits of the seed.

Run `scripts/test_e2fsprogs_crc16.sh` after building the E2fsprogs oracle and
program translations. It runs offline and uses read-only build inputs. The
test compares the candidate with the pinned C function across 16,977,457
cases, traces a real checksum call during a read-only filesystem check, and
compares both passes of the upstream `f_uninit_checksum_bad` fixture and the
repaired image bytes. The default multicall still uses the baseline translation.
The rollout gate is to rebuild all affected engines against the shared
implementation, inspect the linked symbols and run the multicall regressions.

The isolated zlib 1.4 library checkpoint uses its signed release, independent GCC
and Clang builds, 18-case upstream CTest suite, sanitizer and Valgrind gates,
111-symbol ABI comparison, and reviewed static-analysis findings are recorded
in `evidence/zlib-1.4-oracle.json`.  Zlib then passes a narrow Coccinelle
normalization with independent GCC, Clang,
sanitizer, Valgrind, upstream-test, symbol, and Libabigail gates in
`evidence/zlib-1.4-normalization.json`.  The full
15-file C2Rust preserve-unused audit has no translation holes and compiles
without generated Rust repairs; its hashes and unsafe/raw-pointer inventory
are in `evidence/zlib-1.4-c2rust-audit.json`.  The isolated stable Rust library
passes 98 canonical differential comparisons, cross-decompression, upstream
`example` and exhaustive `infcover`, malformed streams, and Valgrind; final
shared/static multicall linkage is deliberately deferred.  Stable evidence is
in `evidence/zlib-1.4-c2rust.json`.

GNU M4 1.4.21 is pinned from its signed canonical release.  Independent GCC
and Clang builds each pass all 382 bundled gnulib cases and the 242 numbered
language checks plus stack-overflow check; ASan/UBSan and Valgrind gates are
recorded in `evidence/m4-1.4.21-oracle.json`.  Its exact linked production
slice is 192 C sources, including 11 M4 application sources.  Cppcheck, GCC
`-fanalyzer`, Clang analyzer/tidy, and Flawfinder results and their review are
recorded in `evidence/m4-1.4.21-static-analysis.json`.  Deterministic C
normalization changes only `src/m4.c`, exporting `rustbox_m4_main` while
retaining the standalone `main` wrapper.  Both compiler suites and Valgrind
remain clean in `evidence/m4-1.4.21-normalization.json`.  C2Rust translation is
complete for all 11 application sources: both the untouched audit output and
the mechanically modernized Rust 1.99 crate compile without translation holes,
and export `rustbox_m4_main` exactly once.  Its hashes and current
raw-pointer/`unsafe` inventory are recorded in
`evidence/m4-1.4.21-c2rust.json`; normalized gnulib linkage and canonical
differential parity are complete in `evidence/m4-1.4.21-hybrid.json`.  The
hybrid passes all 242 numbered language checks, the stack-overflow check, 108
additional exact differential comparisons, and Valgrind.  Its linked stripped
artifact is 531,000 bytes with 375,330 bytes of `.text`; the 23.7 MB Rust
static archive is intermediate linker inventory, not the release footprint.
M4 is integrated into the single Rustbox binary with 436 configured gnulib
support symbols privately namespaced.  It increases the stripped multicall by
193,504 bytes, from 5,094,096 to 5,287,600 bytes, and passes its entire parity
suite through multicall dispatch.

Pkgconf 3.0.11 is pinned to its canonical verified signed tag.  Independent
static GCC and Clang builds each pass all 32 upstream tests without skips;
the shared ASan/UBSan build passes 33, including the extra allocation-failure
case, and the complete 32-test static suite passes under Valgrind.  Its four
installed executables, `pkg-config` compatibility alias, exact 35-source
production closure, and 176-symbol static-library ABI are recorded in
`evidence/pkgconf-3.0.11-oracle.json`.  Cppcheck, GCC `-fanalyzer`, Clang
analyzer/tidy, Flawfinder, and Sparse cover that exact production closure;
their complete results and reviewed non-blocking findings are recorded in
`evidence/pkgconf-3.0.11-static-analysis.json`.  Deterministic normalization
exports four conditional multicall entrypoints and makes two equivalent
boolean disjunctions explicit for static-analysis and C2Rust compatibility.
Both compiler suites, ASan/UBSan, all 32
Valgrind tests, public help/version bytes, and the 176-symbol library ABI
remain at canonical parity in `evidence/pkgconf-3.0.11-normalization.json`.
C2Rust translation covers the exact 35-source production closure with unused
functions preserved.  The untouched audit output and mechanically modernized
stable crate compile without translation holes or generated-Rust repairs and
export all four multicall entrypoints exactly once; hashes and the deferred
raw-pointer/unsafe inventory are in `evidence/pkgconf-3.0.11-c2rust.json`.
The complete Rust archive then passes all 32 upstream suites: 429 CLI fixture
checks, 223 API checks relinked unchanged against Rust, and both allocation-
failure fuzz replays.  Fifty-five additional exact differential comparisons
and six Valgrind smokes pass.  The four-tool hybrid is 521,560 bytes stripped
(509 KiB), versus 490,848 bytes for the four separate canonical executables;
full parity and size evidence are in `evidence/pkgconf-3.0.11-hybrid.json`.
Pkgconf is integrated into Rustbox under five public names.  It increases the
stripped multicall by 201,024 bytes, from 5,287,600 to 5,488,624 bytes.  The
resulting 267-name executable passes all 534 dispatcher comparisons, the full
14,022-case Coreutils/util-linux replay, the complete M4 replay, and pkgconf's
429 CLI fixture checks, 55 exact differential comparisons, and Valgrind.

File 5.48 is pinned to its canonical signed release.  Independent GCC and
Clang builds enable builtin ELF/core handling, zlib, bzip2, xz, zstd, lzip,
seccomp, and Landlock; lrzip is the only unavailable optional backend.  Each
compiler build and the ASan/UBSan build passes all 83 upstream fixtures.  The
two canonical executables agree exactly across 174 additional CLI cases, their
compiled magic databases are byte-identical, their 126 defined libmagic global
symbols match, and Valgrind is clean.  The exact 25-source production closure
and all hashes are recorded in `evidence/file-5.48-oracle.json`.  Compression
and sandbox shared libraries are oracle-only dependencies: Rustbox must
replace or statically integrate them before the no-external-library release
gate.
The exact production closure has also been checked with Cppcheck, GCC
`-fanalyzer`, Clang analyzer/tidy, Flawfinder, and Sparse.  One actionable
hardening site initializes an otherwise parser-constrained operation result;
the remaining findings are reviewed union/endian idioms, generic Annex K
advice, modernization warnings, null spellings, or lexical-risk inventory.
The complete logs, counts, and review are pinned in
`evidence/file-5.48-static-analysis.json`.
Deterministic normalization changes only `src/apprentice.c`, `src/file.c`,
and `src/softmagic.c`: an exact rewrite exports `rustbox_file_main`, a
Coccinelle semantic patch gives invalid operation encodings a deterministic
identity fallback, and exact compatibility rewrites spell IEEE comparisons
portably and prevent C2Rust from lifting function-local names into collisions.
GCC, Clang, and ASan/UBSan each pass all 83 fixtures;
both compiler variants remain exact against their canonical binaries across
174 cases each, libmagic's 126-symbol surface and both compiled magic
databases are unchanged, and Valgrind is clean.  The complete transformation
and parity evidence is in `evidence/file-5.48-normalization.json`.
C2Rust covers the exact 25-source production closure with unused functions
preserved.  The untouched audit output and mechanically modernized stable
crate compile without translation holes or generated-Rust repairs, and the
archive exports `rustbox_file_main` exactly once.  Source hashes and the
deferred raw-pointer/unsafe inventory are in
`evidence/file-5.48-c2rust.json`.  The translated archive passes all 83
upstream libmagic fixtures, 174 exact CLI differential cases, and Valgrind.
The linked executable is 497 KiB stripped (the 23 MiB static archive is only
pre-link inventory), versus 184 KiB for canonical File; complete parity,
linkage, and size evidence is in `evidence/file-5.48-hybrid.json`.
File is integrated into the unified Rustbox dispatcher with its entire
libmagic/internal C surface privately namespaced, so util-linux `more` keeps
its own canonical libmagic behavior.  Its 268-name integration checkpoint was
5,668,624 bytes stripped, a 180,000-byte increase over the prior build, and
passes all 536 dispatcher comparisons, the full 14,022-case Coreutils and
util-linux replay, the complete M4 and pkgconf replays, File's 174 exact CLI
comparisons, and Valgrind.

GNU patch 2.8 is pinned to its canonical signed release.  The exact production
closure is 67 C translation units: all seven program sources and all 60 gnulib
support sources selected by the configured build.  Independent GCC, Clang,
and ASan/UBSan builds each pass the complete upstream suite (49 tests: 47
passes, two documented XFAILs, and no failures), including the `ed`-style
case.  GCC and Clang agree exactly across 28 additional filesystem-aware CLI
comparisons, and Valgrind reports no errors or definite, indirect, or possible
leaks.  The signed-source pin, closure, hashes, dependencies, and test evidence
are recorded in `evidence/patch-2.8-oracle.json`.  Libattr is an oracle-only
dynamic dependency and must be replaced or statically integrated before the
final no-external-library gate.
The same 67-unit production closure has been checked with Cppcheck, GCC
`-fanalyzer`, Clang analyzer/tidy, Flawfinder, and Sparse.  Reviewed path
reports are ownership-transfer, configured-platform, bitmask-enum, or parser-
invariant false positives; the sanitizer and Valgrind gates reproduce no
defect.  Sparse's limitations around generated gnulib alignment storage and a
function attribute are retained explicitly rather than hidden.  Complete
counts, classifications, and raw-log hashes are recorded in
`evidence/patch-2.8-static-analysis.json`.
Deterministic normalization changes ten production sources: `src/patch.c`
exports `rustbox_patch_main` while retaining a conditional standalone `main`;
the generated date parser has its diagnostic source mapping materialized; and
checked-integer widths, narrowing guards, and eager Boolean accumulation are
made explicit where C2Rust otherwise emits invalid Rust.  The exact 67-unit
closure remains unchanged under all three builds; their 147
upstream test executions pass with only the canonical XFAILs, 56 canonical-
versus-normalized differential comparisons are exact, compiler feature
configurations are byte-identical, both object files export both entrypoints,
and Valgrind remains free of real leaks and errors.  Transformation and parity
evidence is in `evidence/patch-2.8-normalization.json`.  C2Rust 0.22.1 now
translates all 67 units with unused functions preserved; the untouched audit
crate and mechanically modernized stable archive compile with no translation
holes and no generated-Rust repairs.  The stable archive exports
`rustbox_patch_main` exactly once; source hashes, modernization operations,
archive symbols, and the deferred raw-pointer/unsafe inventory are recorded in
`evidence/patch-2.8-c2rust.json`.  The linked translated executable passes the
complete 49-case upstream suite, all 28 filesystem-aware canonical
differentials, and Valgrind.  It is 500 KiB stripped versus 164 KiB for the
canonical C executable; linkage, section, and parity evidence is in
`evidence/patch-2.8-hybrid.json`.  GNU patch is integrated into the unified
Rustbox dispatcher with its configured gnulib/internal C surface privately
namespaced.  The resulting 269-name executable is 5,856,208 bytes stripped—a
187,584-byte increase—and retains exact patch parity while passing all prior
combined regressions; integration evidence is in
`evidence/rustbox-multicall.json`.

GNU sed 4.10 is pinned to its canonical signed release.  Its exact configured
production closure is 85 C translation units: 77 gnulib/support sources and
eight sed sources.  Independent GCC and Clang builds each pass the 75-case sed
suite and 287-case gnulib suite with only canonical platform skips;
ASan/UBSan, Valgrind, and 30 cross-compiler CLI/filesystem comparisons are
clean.  Oracle and five-analyzer evidence is recorded in
`evidence/sed-4.10-oracle.json` and `evidence/sed-4.10-analysis.json`.
Deterministic normalization changes 12 sources to export
`rustbox_sed_main`, make checked integer and Boolean semantics explicit, and
materialize one unreachable non-returning control-flow edge.  GCC, Clang,
ASan/UBSan, Valgrind, and 60 canonical-versus-normalized comparisons remain at
exact parity in `evidence/sed-4.10-normalization.json`.  C2Rust translates all
85 units with unused functions preserved, zero translation holes, and zero
generated-Rust repairs; both the raw nightly crate and mechanically modernized
Rust 1.99 archive compile, with hashes and deferred pointer/unsafe inventory in
`evidence/sed-4.10-c2rust.json`.  The translated executable passes both
upstream suites, 30 exact differentials, and Valgrind.  It is 592,248 bytes
stripped versus 208,264 bytes for canonical C; full linkage and parity evidence
is in `evidence/sed-4.10-hybrid.json`.  Sed's configured gnulib/internal C
surface is privately namespaced in the multicall, with its `wctob` asm-label
alias supplied by an explicit ABI bridge.  At that checkpoint the 270-name
binary was 6,111,456 bytes stripped—255,248 bytes above its predecessor—and passed
all combined regressions in `evidence/rustbox-multicall.json`.

GNU Diffutils 3.12 is pinned to its canonical signed release.  Its normal
Linux production closure is 139 C translation units: 124 configured gnulib
sources, 14 program sources, and generated `version.c`; the sanitizer
configuration activates two additional replacement sources.  GCC and Clang
each pass the 33-case Diffutils suite (30 pass, two platform skips, one
expected failure) and the 344-case gnulib suite (301 pass, 43 platform skips),
while ASan/UBSan passes the same Diffutils totals and all 344 gnulib cases
under its documented 297-pass/47-skip instrumentation policy.  Independent
GCC-versus-Clang behavior comparisons pass 48/48 across `cmp`, `diff`,
`diff3`, and `sdiff`.  Valgrind is clean for `cmp`, `diff`, and `sdiff`'s own
process; canonical `diff3`'s two retained 4096-byte buffers are recorded as a
baseline rather than hidden.  Reproducible details are in
`evidence/diffutils-3.12-oracle.json`.  Cppcheck, GCC `-fanalyzer`, Clang
analyzer/Tidy, Flawfinder, and Sparse then review exactly those 139 production
sources.  Their ownership, nullability, configured-header, and parser reports
have zero blocking findings after review; the complete immutable inventory and
reasoning are in `evidence/diffutils-3.12-analysis.json`.  Deterministic
normalization exports `rustbox_cmp_main`, `rustbox_diff_main`,
`rustbox_diff3_main`, and `rustbox_sdiff_main` behind conditional standalone
wrappers.  It also makes checked-arithmetic operand types, Boolean assignments,
and one unreachable post-`_Noreturn` edge explicit for deterministic C2Rust
translation without changing an algorithm.  GCC, Clang, and ASan/UBSan retain
every canonical upstream test total; Valgrind retains the exact canonical
resource baseline; and all 96
canonical-versus-normalized behavior comparisons are byte-exact.  The exact
139-source production closure, generated configuration, dynamic dependency,
and entrypoint-symbol checks are recorded in
`evidence/diffutils-3.12-normalization.json`.  C2Rust translates all 139
production units with unused functions preserved and zero translation holes
or generated-Rust repairs.  Both the raw pinned-nightly
crate and its mechanically modernized Rust 1.99 archive compile; all four
multicall entrypoints are exported exactly once.  Source, declaration-map,
pointer/unsafe, toolchain, modernization, and archive inventories are recorded
in `evidence/diffutils-3.12-c2rust.json`.  The four translated hybrids then
pass both upstream suites, 48 exact differentials, and Valgrind checks.  Diff3
has the exact canonical allocation lifecycle—20 allocations, six frees, and
8,456 bytes in 14 blocks at exit—while optimized Rust drops the last stack
root sooner and therefore changes Valgrind's reachable/lost classification for
160 of those intentionally retained bytes.  Per-command sizes, hashes,
dependencies, and the full parity record are in
`evidence/diffutils-3.12-hybrid.json`.  Its configured C/gnulib surface is
privately namespaced in the multicall.  `program_name` remains a deliberately
shared process global, and a private ABI bridge preserves libc-compatible
full-path `error(3)` diagnostics rather than binding to another translated
package's error policy.  The resulting 274-name binary is 6,340,800 bytes
stripped—229,344 bytes above the sed checkpoint—and passes all 548 dispatcher
comparisons, all 14,022 prior batch cases, both Diffutils upstream suites, 48
exact Diffutils comparisons, and the resource checks recorded in
`evidence/rustbox-multicall.json`.

GNU Grep 3.12 is pinned to its canonical signed release.  Its configured
Linux production closure is 129 C translation units: six Grep engine files,
122 configured gnulib sources, and the generated POSIX colorize selector.
GCC and Clang each pass the 128-case Grep suite (113 pass, 13
platform/expensive skips, two expected glibc failures) and the 315-case
gnulib suite (277 pass, 38 platform skips).  ASan/UBSan passes all 127
functional Grep cases selected for instrumentation and the complete gnulib
suite; the sole excluded case is a ten-million-record throughput test with
fixed wall-clock deadlines.  Independent GCC-versus-Clang behavior checks
pass 36/36 across byte, locale-neutral regex, fixed-string, PCRE, recursive,
binary, NUL-record, context, error, and option paths.  The canonical
process-exit DFA/PCRE allocation baseline is recorded rather than hidden.
Reproducible details are in `evidence/grep-3.12-oracle.json`; production-only
static analysis and normalization are the next gates.
Cppcheck, GCC `-fanalyzer`, Clang analyzer/Tidy, Flawfinder, and Sparse then
review exactly those 129 production translation units.  Ownership-transfer,
allocation-failure, initialized-color, trie-construction, and DFA state
invariants account for the apparent null/leak reports; the upstream,
sanitizer, differential, and resource gates exercise the corresponding paths.
The reviewed immutable inventory has zero blocking findings and is recorded
in `evidence/grep-3.12-analysis.json`.  The one compiler precedence diagnostic
is retained as an explicit parenthesization task for deterministic
normalization.
Deterministic normalization changes ten source files to export
`rustbox_grep_main`, parenthesize the audited conditional, make checked
integer widths explicit, preserve eager Boolean call order, and make two
unreachable post-`die` returns explicit in forms that C2Rust translates
without fallback panics.  GCC, Clang, and ASan/UBSan retain every
canonical suite total; the canonical process-exit allocation baseline is
unchanged; and all 72 canonical-versus-normalized behavior comparisons are
byte-exact.  The exact source closure, rewrites, symbols, dependencies, and
parity record are in `evidence/grep-3.12-normalization.json`.
The exact 129-unit closure then translates with C2Rust 0.22.1 under
`--fail-on-error` and `--preserve-unused-functions`; all 129 declaration maps
are present.  Both the raw nightly crate and the deterministic Rust 1.99
modernization compile, and the release archive exports exactly one
`rustbox_grep_main`.  The 131 generated Rust files contain 101,710 lines and
no `compile_error!`, `todo!`, `unimplemented!`, or fallback `panic!` holes;
the current 10,249 raw-pointer type occurrences are recorded for later
hardening rather than silently treated as safe.  No generated Rust was
hand-repaired.  Reproducible inventories, hashes, compiler diagnostics, and
the 24,216,926-byte pre-link archive are in
`evidence/grep-3.12-c2rust.json`.
The linked translated hybrid preserves PCRE2 support and passes the complete
128-case Grep and 315-case gnulib suites, all 36 canonical-versus-translated
byte-exact comparisons, and an allocation-for-allocation exact Valgrind
comparison with canonical Grep.  Its only C ABI glue is the entrypoint and
the two gnulib libc aliases for `btowc` and `wctob`.  The standalone hybrid is
560,424 bytes stripped versus 163,240 bytes for canonical Grep; multicall
dead-code sharing is measured only after integration.  Reproducible linkage,
size, dependency, suite, differential, and resource evidence is in
`evidence/grep-3.12-hybrid.json`.
Grep's 421 configured C/gnulib definitions are privately namespaced in the
unified multicall.  Dedicated libc-compatible error and character-conversion
bridges prevent binding to another package's gnulib policy; `egrep` and
`fgrep` reproduce the canonical wrapper warnings and inject `-E` and `-F`
without heap allocation.  The resulting 277-name binary is 6,568,416 bytes
stripped—227,616 bytes above the Diffutils checkpoint—and passes all 554
dispatcher comparisons, all 14,022 prior batch cases, every previously
integrated package gate, both Grep upstream suites, 36 exact Grep comparisons,
four direct `egrep`/`fgrep` wrapper comparisons, and the resource checks
recorded in `evidence/rustbox-multicall.json`.

GNU bc 1.08.2, bundling dc 1.5.2, is pinned to its canonical signed release.
The configured Linux production closure is 21 C translation units and 14,826
lines.  Independent GCC and Clang builds each complete all 18 shipped
arbitrary-precision workloads—including the exhaustive transcendental
`checklib.b` pass—and agree byte-for-byte across a further 46 bc/dc language,
CLI, diagnostic, and error cases.  ASan/UBSan covers the 17 bounded shipped
workloads; only `checklib.b` is omitted from instrumentation because its full
high-precision throughput pass already runs under both canonical compilers.
Valgrind reports no definite, indirect, or possible leak and no errors for
either executable; the process-lifetime storage still reachable at exit is
recorded rather than hidden.  The oracle deliberately disables optional
Readline and libedit, so its sole dynamic dependency is libc.  Reproducible
source, build, suite, differential, binary, and resource evidence is in
`evidence/bc-1.08.2-oracle.json`.
Cppcheck, GCC `-fanalyzer`, Clang analyzer/Tidy, Flawfinder, and Sparse then
review exactly those 21 production units.  Allocation-failure paths terminate
through `out_of_memory`/`dc_memfail`; generated Flex and Bison ownership and
dataflow account for the apparent null, leak, and uninitialized reports; and
the dc byte-output traversal checks its node before each access.  The reviewed
inventory has zero blocking findings and no canonical source changes.  Exact
tool counts, artifact hashes, process-exit resource baselines, and finding
dispositions are in `evidence/bc-1.08.2-analysis.json`; deterministic
normalization exports `rustbox_bc_main` and `rustbox_dc_main` from `bc/main.c`
and `dc/dc.c` while retaining conditional standalone wrappers.  It also
removes the generated scanner's 55 diagnostic-only `#line` controls—there are
no `__LINE__` or `__FILE__` consumers—so C2Rust declaration-map ranges track
monotonic physical `scan.c` offsets.  GCC and Clang reproduce all 18 canonical workload outputs exactly,
ASan/UBSan repeats the bounded 17-workload set, 92 canonical-versus-normalized
comparisons are byte-exact, and both Valgrind allocation summaries match the
canonical baselines.  The exact tree hashes, entrypoint symbols, source
closure, binaries, and parity record are in
`evidence/bc-1.08.2-normalization.json`.
The exact normalized 21-unit closure now translates completely with C2Rust
0.22.1 under `--fail-on-error` and `--preserve-unused-functions`.  Both the
historical nightly output and its deterministic Rust 1.99 modernization
compile without `compile_error!`, `todo!`, `unimplemented!`, or fallback
`panic!` holes, and the release archive exports exactly one each of
`rustbox_bc_main` and `rustbox_dc_main`.  C2Rust's optional declaration-map
export is disabled because its metadata-only foreign-item pass panics after
successfully translating all 21 units; no partial maps are accepted and no
generated Rust is hand-repaired.  The 23 generated Rust files contain 24,740
lines and 3,468 raw-pointer type occurrences, recorded for the later safety
phase.  The 23,726,090-byte pre-link archive, exact source and output hashes,
toolchain checks, linkage deduplication, and complete unsafe inventory are in
`evidence/bc-1.08.2-c2rust.json`.  The linked translated bc and dc pass all 18 shipped
arbitrary-precision workloads, including the exhaustive `checklib.b`, all 46
bc/dc language, CLI, diagnostic, and error comparisons, and exact canonical
Valgrind allocation-lifecycle comparisons with zero errors.  The only C ABI
glue is the entrypoint.  The standalone stripped binaries are 423,592 bytes
for bc and 378,168 bytes for dc, versus canonical C's 93,016 and 55,528 bytes;
multicall dead-code sharing is measured only after integration.  Reproducible
linkage, dependency, size, differential, workload, and resource evidence is
in `evidence/bc-1.08.2-hybrid.json`.  All 248 non-entrypoint C symbols are
private in the unified link.  The resulting two applets add 123,856 stripped
bytes to Rustbox and retain the full hybrid parity gates; integration evidence
is in `evidence/rustbox-multicall.json`.

attr 2.6.0 is pinned to its canonical signed Savannah release.  The configured
static, no-NLS production closure is 21 C units and 3,702 lines across
`attr`, `getfattr`, `setfattr`, libattr, and their filesystem-walk support.
Independent GCC and Clang builds pass both ordinary upstream components and
agree byte-for-byte and state-for-state across 22 CLI, encoding, recursive,
mutation, and error cases; ASan/UBSan repeats the upstream suite.  The one
upstream root-only `trusted.*` symlink component is intentionally skipped
because container root lacks the required kernel capability.  The ordinary
`user.*` coverage runs on a Linux xattr-capable Docker volume, and Valgrind
reports zero errors or lost bytes for mutation and query paths.  Exact source,
compiler, test, binary, dependency, differential, and resource evidence is in
`evidence/attr-2.6.0-oracle.json`.  Cppcheck, GCC `-fanalyzer`, Clang
analyzer/Tidy, Flawfinder, and Sparse then review exactly those 21 production
units.  The reviewed inventory has zero blocking findings and no canonical
source changes; the allocation-exit paths, zero-element qsort call, analyzer
parser limitation, conversion candidates, and public libattr surface are
recorded explicitly in `evidence/attr-2.6.0-analysis.json`.  Deterministic
normalization changes the three public-tool sources plus the compatibility
syscall wrapper: it exports conditional multicall entrypoints, gives the
unsigned attribute length its matching format, guards the configured-libc
zero-element qsort call, retains realloc ownership until allocation succeeds,
and omits ELF symbol-version aliases only in the multicall translation
configuration because C2Rust cannot represent them.  GCC, Clang, and
ASan/UBSan retain the 2-pass/1-capability-skip upstream result; 44 independent
canonical-versus-normalized differential comparisons are exact, and the
Valgrind heap lifecycles remain identical to the canonical builds.  The exact
rewrites, entrypoint symbols, compiler closures, and parity evidence are in
`evidence/attr-2.6.0-normalization.json`.  C2Rust then translates that exact
21-unit closure with unused functions preserved.  The untouched audit output
and mechanically modernized Rust 1.99 crate both compile with no translation
holes and no generated-Rust source repairs; the historical-nightly check
injects only the `c_variadic` crate feature that C2Rust omitted for its emitted
`VaList` declarations.  The 23 Rust files contain 10,952 lines and 2,259
raw-pointer type occurrences for the later safety phase.  All three multicall
entrypoints are unique in the 23,461,086-byte intermediate archive.  Complete
hashes, compile diagnostics, modernization records, and unsafe inventory are
in `evidence/attr-2.6.0-c2rust.json`.  The linked translated tools retain the
2-pass/1-capability-skip upstream result, pass all 22 exact differential
cases, and match canonical output and Valgrind allocation lifecycles exactly.
Their separate stripped executables total 693,152 bytes before multicall
runtime sharing.  Full linkage, behavior, resource, and size evidence is in
`evidence/attr-2.6.0-hybrid.json`.  All 46 non-entrypoint C symbols are private
in the unified link; integration adds only 25,344 stripped bytes and retains
the complete upstream, differential, and resource gates in
`evidence/rustbox-multicall.json`.

acl 2.4.0 is pinned to its canonical signed Savannah release.  The archive,
detached signature, release-key fingerprint, and all 274 archive members are
verified before its `chacl`, `getfacl`, and `setfacl` production closure is
built or translated.  That closure is 72 unique C units: 51 libacl, 14
filesystem/support, and seven tool sources.  Independent GCC and Clang builds
each pass all 13 runnable upstream tests with the two canonical NFS expected
failures; one root permission/device test has a separately pinned Docker
platform failure.  Their standalone oracles embed the release's own libacl
and depend only on libc, agree across 30 CLI and filesystem-state comparisons,
and pass exact Valgrind leak/error gates.  ASan is clean, while UBSan exposes
four instances of the same canonical null-pointer-offset defect at
`__libobj.c:82`; its exact failing test log is retained as a required
normalization target rather than suppressed.  Source, compiler, test,
differential, dependency, sanitizer, and resource evidence is in
`evidence/acl-2.4.0-oracle.json`.  Cppcheck, GCC `-fanalyzer`, Clang
analyzer/Tidy, Flawfinder, and Sparse then audit exactly the same 72-unit
production closure.  Their reviewed baseline has one demonstrated blocker:
the UBSan pointer-before-null-check ordering.  The matching `acl_free`
ordering and realloc ownership repair are mandatory mechanical normalization;
infeasible internal-API paths and hardening inventories remain recorded rather
than silently discarded in `evidence/acl-2.4.0-analysis.json`.  Deterministic
normalization changes seven files: the two object-pointer conversions now
occur after their null checks, `setfacl` retains realloc ownership on failure,
the three tools export conditional multicall entrypoints, and getfacl/setfacl
diagnostic state is placed in explicit per-applet namespaces.  GCC, Clang, and
ASan/UBSan retain the complete runnable upstream result with no undefined-
behavior diagnostic; 60 canonical-versus-normalized comparisons are exact and
Valgrind allocation summaries match the canonical tools.  LeakSanitizer alone
is disabled in the root test because that fixture runs under ptrace; Valgrind
remains the leak gate.  Exact rewrites, source closure, symbols, and parity are
recorded in `evidence/acl-2.4.0-normalization.json`.  C2Rust then translates
all 72 production units with unused functions preserved.  Its initial CFG
panic is eliminated by the verified standard-statement macro rewrite; the
untouched audit output and mechanically modernized Rust 1.99 crate compile
with no translation holes and no generated-Rust source repairs.  The 74 Rust
files contain 38,636 lines and 7,482 raw-pointer type occurrences for the
later safety phase.  All three entrypoints are unique in the 23 MB intermediate
archive.  Complete input hashes, diagnostics, modernization records, and
unsafe inventory are in `evidence/acl-2.4.0-c2rust.json`.  The three linked
translated tools pass all 13 runnable upstream tests, both canonical NFS
expected failures, and all 30 state-aware differential cases.  Valgrind finds
zero errors and frees every allocation; generated temporary aggregate storage
adds two short-lived allocations to setfacl and four to getfacl, recorded
explicitly rather than misreported as an exact allocation lifecycle.  Their
separate stripped executables total 1,069,184 bytes before multicall sharing.
Full behavior, resource, dependency, and size evidence is in
`evidence/acl-2.4.0-hybrid.json`.  All 82 non-entrypoint C symbols are private
in the unified link; integration adds 66,656 stripped bytes and retains the
complete help/version, upstream, differential, platform-baseline, and Valgrind
gates in `evidence/rustbox-multicall.json`.

LZ4 1.11.1 is pinned to its canonical GitHub release asset and the separate
upstream SHA-256 asset.  Upstream publishes no cryptographic release signature
and uses a lightweight tag, so that authentication limitation is explicit
rather than described as a signed release.  Its four installed command names
share one executable built from an exact 12-source, 16,809-line closure with
the release's own liblz4 and xxhash embedded.  Independent GCC and Clang builds
and GCC ASan/UBSan each pass the broad upstream essentials suite; GCC and Clang
also agree across 27 byte-and-filesystem differential cases covering aliases,
frame and legacy compression, decompression, streams, list mode, options, and
errors.  Compression and decompression Valgrind gates report zero errors and
free every allocation, and both oracles depend only on libc.  Source,
compiler, dependency, differential, sanitizer, and resource evidence is in
`evidence/lz4-1.11.1-oracle.json`.  Cppcheck, GCC's path-sensitive analyzer,
Clang Analyzer/Tidy, Flawfinder, and Sparse then audit that exact closure.  The
one demonstrated canonical defect is a signed `int` passed to an unsigned
printf conversion in help output.  The normalization gate also requires
explicit zero-length dictionary-copy guards and replaces an exactly-sized
`strcpy`/`strcat` output-name construction with a bounded copy.  GCC's reported
realloc double free and constructor-local resource leaks are path-model
artifacts; both supported compilers, sanitizers, and Valgrind independently
close those paths.  Exact finding counts and review decisions are pinned in
`evidence/lz4-1.11.1-analysis.json`.
The deterministic normalization changes only `programs/lz4cli.c`,
`programs/lz4io.c`, and `lib/lz4frame.c`, exposes `rustbox_lz4_main`, and
selects upstream's portable `memcpy` memory-access implementation.  Its
human-size formatter uses `double` for the integer-derived two-decimal display,
avoiding C2Rust's non-C-compatible `f128` variadic representation.  GCC,
Clang, and GCC ASan/UBSan each
pass the complete essentials suite after normalization.  Both optimized builds
match their corresponding canonical compiler across all 27 cases (54 exact
comparisons), while Valgrind retains the canonical allocation/free counts for
both compression and decompression.  Exact transformations, source closure,
entrypoints, dependencies, sizes, and parity are recorded in
`evidence/lz4-1.11.1-normalization.json`.
C2Rust translates all 12 multithreaded production units with unused functions
preserved and no holes.  The untouched generated crate compiles on its pinned
historical nightly; the mechanical stable-Rust pass maps its one GCC atomic
exchange to `AtomicI32::swap(Acquire)` and otherwise uses the same shared
opaque-type, variadic, and raw-static transformations as earlier applets.  The
14 stable Rust files contain 36,141 lines and 7,103 raw-pointer type
occurrences for the later safety phase.  No generated semantic repair is
needed, `f128` is absent, and `rustbox_lz4_main` is unique in the release
archive.  Complete inputs, diagnostics, modernization, dependency, and unsafe
inventory are in `evidence/lz4-1.11.1-c2rust.json`.
The linked translated executable passes all 27 byte-and-filesystem cases and
the complete upstream essentials suite, including multithreading, mmap source
mutation, custom block sizes, legacy frames, and list formatting.  Valgrind
finds zero errors and frees every allocation; compression exactly retains the
canonical heap lifecycle, while decompression adds one fully freed 64-byte
Rust startup allocation.  Its stripped standalone size is 586,784 bytes before
multicall sharing.  Full behavior, resource, dependency, and size evidence is
in `evidence/lz4-1.11.1-hybrid.json`.
All four names are integrated into Rustbox.  The unified link keeps all 206
non-entrypoint LZ4, liblz4, and XXH C symbols private, passes 580/580 aggregate
help/version comparisons and all 14,022 prior batch cases, and repeats the full
LZ4 behavior suite.  Compression retains the standalone allocation lifecycle;
subcommand dispatch adds only 32 allocated-and-freed bytes during decompression.
Integration adds 270,336 stripped bytes, substantially less than the 586,784-byte
standalone translated executable.  Unified evidence is in
`evidence/rustbox-multicall.json`.

GNU Gzip 1.14 is pinned to its signed canonical Savannah release.  Its full
installed surface is 14 names: one native `gzip` executable, the hard-linked
`uncompress` alias, and twelve upstream shell interfaces.  Independent GCC,
Clang, and GCC ASan/UBSan builds each pass all 29 runnable upstream tests with
the same one root/platform skip.  GCC and Clang agree across 54 exact command,
byte-stream, and filesystem comparisons; both optimized builds emit identical
compressed bytes.  Compression and decompression Valgrind gates report zero
errors and free every allocation, and the oracle executable depends only on
libc.  The two compilers select the same exact 69-translation-unit production
closure.  Authentication, source, compiler, dependency, differential,
sanitizer, and resource evidence is in `evidence/gzip-1.14-oracle.json`.
Cppcheck, GCC `-fanalyzer`, Clang Analyzer/Tidy, Flawfinder, and Sparse audit
that same closure in `evidence/gzip-1.14-analysis.json`.  The demonstrated
normalization blocker is gnulib `vasnprintf` forming or passing a null pointer
for zero-length operations, matching the canonical UBSan nonnull-attribute
diagnostic.  Other required translation preparations make fatal range control
flow explicit, split legacy condition side effects, bound name-buffer copies,
and select the canonical portable CRC implementation if C2Rust cannot express
the x86 PCLMUL intrinsics.  Sparse's intrinsic parser failures and the reviewed
path-model false positives remain recorded rather than silently discarded.
Deterministic normalization changes only `gzip.c`, `deflate.c`,
`lib/malloca.c`, and `lib/vasnprintf.c`: it exports `rustbox_gzip_main`, makes
the fatal pack-level range boundary explicit, guards the demonstrated
zero-length null copy, and materializes the checked allocation-size width.
The build selects upstream's portable slice-by-8 CRC implementation through
its configure cache instead of translating the optional x86 PCLMUL intrinsics.
GCC and Clang each retain all 29 runnable upstream passes and compare exactly
to their corresponding canonical oracle across all 54 cases.  The normalized
ASan/UBSan build also passes the full runnable suite with the nonnull-attribute
checker enabled, confirming that the source repair replaces the earlier
suppression.  Compression and decompression retain the exact canonical
Valgrind allocation lifecycles.  The resulting 68-unit translation closure,
all 108 canonical comparisons, exact transformations, compiler results, and
resource evidence are in `evidence/gzip-1.14-normalization.json`.
C2Rust translates the complete 68-source portable production closure with no
generated holes.  Its untouched full audit isolates one unrepresentable ABI:
x86-64 C `long double` in variadic arguments becomes the `f128` crate, which
cannot implement Rust's sealed `VaArgSafe` trait.  The compile-clean reachable
partition therefore translates 64 sources and retains only `vasnprintf`,
`printf-args`, and `printf-parse` as canonical C objects; the optional
`printf-frexpl` helper is neither translated nor linked.  Both the untouched
reachable crate on C2Rust's historical nightly and the mechanically modernized
crate on stable Rust 1.99 compile without holes or generated semantic repairs.
The 66 stable Rust files contain 25,282 lines and 4,086 raw-pointer type
occurrences for the later safety phase.  Complete translation, diagnostics,
partition, modernization, dependency, and unsafe inventory is in
`evidence/gzip-1.14-c2rust.json`.
The linked hybrid extracts exactly those three C archive members and retains
the twelve canonical shell interfaces around the translated `gzip` engine.
It passes the complete 29-runnable-case upstream suite with the canonical one
skip, all 54 command/stream/filesystem comparisons across all 14 installed
names, byte-identical compression, and exact canonical Valgrind allocation
lifecycles.  The standalone translated executable strips to about 0.4 MB;
the much larger static archive is link inventory rather than release size.
Full behavior, bridge, resource, dependency, symbol, and size evidence is in
`evidence/gzip-1.14-hybrid.json`.
The translated native `gzip` engine is also integrated into the unified
Rustbox dispatcher.  Native equivalents of upstream's `gunzip`, `zcat`,
`zcmp`, `zdiff`, `zforce`, `zgrep`, `zegrep`, `zfgrep`, `zmore`, `znew`, and
`gzexe` shell frontends, plus an internal Gzip-to-Less `zless`, provide all
fourteen public names without invoking a shell inside Rustbox.  The comparison,
search, and pager frontends reuse the integrated GNU Diffutils and Grep engines,
Util-linux `more`, and Less through internal Gzip pipes.  Their expanded
108-case differential passes,
compression is byte-identical, decompression matches canonical bytes, and
Valgrind matches the canonical engine lifecycles.  All Gzip and gnulib
symbols except the three deliberate entrypoints are private to the applet,
including its independent Rust personality symbol.  Unified
evidence is in `evidence/rustbox-multicall.json`.  The first three native
frontend names add no stripped bytes beyond the Gzip engine; `zcmp` and `zdiff`
add 8,192 stripped bytes, and the three `zgrep` personalities add 4,096 bytes;
`zmore` adds no further stripped bytes, `znew` adds 8,208 bytes, and `gzexe`
adds 8,192 bytes.

Less 710 is pinned to Mark Nudelman's signed canonical release.  Its complete
38-source production closure passes the 19-case upstream terminal suite under
GCC, Clang, and ASan/UBSan, and the two independent builds agree across 22
public `less` and `lessecho` comparisons.  The six-tool static audit and
deterministic entrypoint normalization retain those results.  C2Rust emits all
38 sources and all 38 declaration maps without holes.  Eight mechanically
reviewed casts restore the destination-type promotions used by C23 `ckd_mul`
and `ckd_add`; no algorithm is changed.  The stable crate contains 77,087 Rust
lines and 10,041 raw-pointer type occurrences for the later safety phase.  The
linked translated fixture passes all 22 comparisons and exactly matches both
canonical allocation lifecycles under Valgrind.  It strips to 924,648 bytes
versus 304,552 bytes for the canonical standalone binary; terminal-info code
is still a fixture-time shared dependency and must be internalized at the
final static release gate.  Translation and hybrid evidence is in
`evidence/less-710-c2rust.json` and `evidence/less-710-hybrid.json`.
Both names are privately namespaced and integrated into Rustbox; their 22-case
multicall differential and resource checks pass, and Less also supplies the
final internal `zless` frontend.

XZ Utils 5.8.4 is pinned to Lasse Collin's signed canonical release, including
the September 2026 security fix.  Its exact 101-source production closure
(34,216 lines) builds independently with GCC and Clang with Landlock enabled;
the sanitizer build follows upstream's requirement to disable only the
sandbox instrumentation conflict.  All three builds pass the 22-case upstream
suite.  The compiler oracles agree on 70 behavioral cases across every one of
the 23 installed command and compatibility names, and emit byte-identical
`.xz` and `.lzma` streams.  Each physical command depends only on libc because
liblzma is built internally.  Valgrind reports no definite, indirect, or
possible loss and no memory errors; canonical XZ intentionally retains its
codec state until process exit.  Reproducible oracle details are in
`evidence/xz-5.8.4-oracle.json`.  The five-tool production audit found no
demonstrated canonical defect.  Deterministic normalization changes only three
entrypoint source files to export four physical command personalities, and
selects upstream's portable C CRC implementation for translation.  All three
normalized compiler suites pass, and both canonical compiler baselines agree
with normalization across 140/140 comparisons.  Audit and normalization
evidence is in `evidence/xz-5.8.4-static-analysis.json` and
`evidence/xz-5.8.4-normalization.json`.  C2Rust translates all 101 production
sources and both decoder personalities as 102 actions without holes.  The
translation-source build retains all 22 upstream tests and all 70 public
comparisons after selecting XZ's documented pure-C range decoder and omitting
two optional compiler-specific optimizations.  One repeated aligned-copy type
pattern accounts for 474 of 487 raw compiler diagnostics; deterministic,
audited repairs also restore four integer truth tests, five `size_t` arithmetic
orders, one shadowed binding, and two local static tables.  The complete
104-file crate checks and release-builds on stable Rust 1.99.  Translation,
repair, unsafe inventory, and build evidence is in
`evidence/xz-5.8.4-c2rust.json`.  The translated archive and fourteen native
shell replacements are now privately integrated into Rustbox.  All 70 XZ
public comparisons and all 690 aggregate help/version comparisons pass;
compression is byte-identical and both engine directions have zero Valgrind
errors and no lost bytes.  Unified linkage and resource evidence is in
`evidence/rustbox-multicall.json`.

zstd 1.5.7 is pinned to Meta's canonical checksum-authenticated release and
annotated release commit.  Its exact 45-source production closure (56,648
lines) builds independently under GCC, Clang, and ASan/UBSan with all native
compression, decompression, dictionary, benchmark, legacy-decoder, and POSIX
thread functionality enabled.  All three builds pass the complete upstream
`make check` suite.  The two optimized oracles agree on all 17 public command
comparisons across `zstd`, `zstdmt`, `unzstd`, `zstdcat`, `zstdgrep`, and
`zstdless`, and produce byte-identical frames.  The physical command depends
only on libc: optional zlib, liblzma, and liblz4 foreign-format backends are
deliberately disabled because Rustbox already owns those formats and must not
gain external runtime dependencies.  Both Valgrind directions report zero
errors and no definite, indirect, or possible loss.  Reproducible details are
in `evidence/zstd-1.5.7-oracle.json`.  The five-tool production audit
found no demonstrated canonical defect.  Deterministic normalization changes
only `programs/zstdcli.c` to export `rustbox_zstd_main`, and zstd's documented
`ZSTD_NO_ASM=1` configuration selects its portable C Huffman implementation in
place of one optional x86-64 assembly unit.  The exact 44-source portable
closure passes all three complete upstream suites and 34/34 canonical versus
normalized command comparisons, with no external runtime library beyond
libc.  Audit and normalization evidence is in
`evidence/zstd-1.5.7-static-analysis.json` and
`evidence/zstd-1.5.7-normalization.json`.  C2Rust then translates every one of
the 44 portable production sources with `--fail-on-error` and
`--preserve-unused-functions`: the 46-file, 217,221-line stable Rust 1.99
crate contains no translation holes or generated semantic repairs.  Its
25,255 raw-pointer type occurrences and 7,643 unsafe functions are recorded
for the later safety phase.  Fourteen retained upstream assembly directives
are reviewed loop alignment, padding, and one compiler-ordering barrier—not
algorithm holes.  The linked hybrid passes all 17 public comparisons, emits
byte-identical frames, and has zero Valgrind errors or lost bytes in both
directions.  Translation and hybrid evidence is in
`evidence/zstd-1.5.7-c2rust.json` and `evidence/zstd-1.5.7-hybrid.json`.
All six names are now integrated with privately namespaced engine symbols and
native frontends.  The unified executable passes all 690 help/version checks,
all 14,022 pre-existing batch regressions, the 17-case zstd differential, and
both zstd Valgrind directions; combined evidence is in
`evidence/rustbox-multicall.json`.

GNU tar 1.35 is pinned to Sergey Poznyakoff's canonical signed release.  Its
exact 197-source production closure comprises 24 tar units, GNU `rmt`, six tar
support units, and 166 configured gnulib units (67,232 lines); no configured
support source is omitted.  GCC, Clang, and ASan/UBSan builds each run all 224
upstream tests: 202 pass, 20 are upstream-declared skips, and the only two
failures require Docker capabilities for trusted xattrs and binary capability
restoration.  Both huge sparse-file cases, including storage above 8 GiB and
listing above 2^33 bytes, pass in all three builds.  GCC and Clang agree on all
18 command, protocol, archive, extraction-tree, and compression-personality
comparisons.  Valgrind reports no lost allocation for create, list, or `rmt`;
extract records the exact canonical process-exit cleanup baseline of 152 direct
and one indirect byte, which the multicall integration must improve rather
than inherit.  The canonical oracle uses libacl and external compressors only
as test fixtures; the final executable must reuse Rustbox's integrated ACL and
compression engines and add no external runtime dependency.  Reproducible
evidence is in `evidence/tar-1.35-oracle.json`.  The complete 197-unit
Cppcheck, GCC `-fanalyzer`, Clang analyzer/tidy, Flawfinder, and configured
Sparse audit found no demonstrated canonical defect; Sparse finishes with no
parser error after one analyzer-only same-alignment spelling for gnulib scratch
storage.  Its locked findings and ownership review are in
`evidence/tar-1.35-static-analysis.json`.  Deterministic normalization changes
only `src/tar.c`, `rmt/rmt.c`, and gnulib `human.c`: the first two export the
multicall entrypoints while retaining standalone wrappers, and the third uses
an equivalent `unsigned long` local only where
`UINTMAX_MAX == ULONG_MAX`.  That target-guarded spelling removes C2Rust's one
unsupported long-double conversion without changing an algorithm or data
layout.  GCC, Clang, and ASan/UBSan each reproduce the complete 224-test result,
both canonical-versus-normalized differentials pass 18/18, and a strict
per-unit C2Rust probe translates all 197 production actions with zero failures.
Reproducible details are in `evidence/tar-1.35-normalization.json`; combined
strict translation covers all 197 production actions.  The 199-file stable
Rust 1.99 crate builds with no placeholder or compile-error holes after one
reusable C23 checked-arithmetic modernization handles 80 mixed-type
`ckd_add`, `ckd_sub`, and `ckd_mul` sites.  Five C2Rust fallthrough guards are
all unreachable immediately after canonical `_Noreturn` calls.  GNU's four
x86-64 SysV long-double/variadic units remain canonical C because Rust's
stable `VaList` and the translator's `f128` wrapper cannot represent that ABI
faithfully; their translated forms remain in the audit inventory.  The
25,082 raw-pointer type occurrences and 5,775 unsafe functions are recorded
for the later safety phase.  Reproducible translation evidence is in
`evidence/tar-1.35-c2rust.json`.
The first linked hybrid passes all 18 canonical comparisons for `tar` and
`rmt`, including byte-identical deterministic archives, extraction trees, the
remote-tape protocol, and gzip/xz/zstd personalities.  Create, list, and
`rmt` have zero Valgrind errors or lost bytes.  A deterministic ownership
repair also frees the three name-list allocations that canonical tar leaves
for process exit, reducing extract from 152 direct plus one indirect lost byte
to zero without changing any of the 18 behavior comparisons.  The temporary
standalone bridge links system libacl only as an independent oracle fixture.
In the unified executable, tar's 13 ACL API imports and Coreutils' ten ACL
imports are deterministically rebound to Rustbox's privately namespaced
translated ACL archive; the final ELF has no `libacl.so` dependency.  Tar's
GNU underscore helpers and four canonical long-double/variadic residue objects
are namespaced with the translated archive.  A deterministic rmt repair routes
program metadata through gnulib argp's single shared globals, removing archive
member-order sensitivity without changing standalone tar help.  The integrated
binary passes all 18 tar/rmt comparisons, all four zero-loss Valgrind paths,
all 690 aggregate dispatcher comparisons, and all 14,022 pre-existing batch
regressions.  Hybrid and unified evidence is in
`evidence/tar-1.35-hybrid.json` and `evidence/rustbox-multicall.json`.

Ncurses 6.6 is pinned to Thomas E. Dickey's canonical signed stable release.
The archive, detached signature, current release-key fingerprint, and all
1,298 archive members are authenticated before use.  The scoped wide-character
oracle builds the ten installed native personalities (`captoinfo`, `clear`,
`infocmp`, `infotocap`, `tabs`, `tic`, `toe`, `tput`, `tset`, and `reset`),
the generated `ncursesw6-config` helper, and shared/static `ncursesw`, `panelw`,
`formw`, `menuw`, `tinfow`, and `ticw` libraries.  Ada, the C++ binding,
interactive demo binaries, GPM, and PCRE2 are outside this utility tranche.
GCC, Clang, and ASan/UBSan cover the same 264-source production closure; all
33 scoped header checks pass per compiler, all 27 functional compiler
differentials pass, and all ten native personalities report zero Valgrind
errors with no direct or indirect loss on their version paths.

The sanitizer oracle also records one canonical upstream defect during
terminfo installation: `read_entry.c:92` left-shifts byte value 255 into a
signed `int`.  Only that exact diagnostic is allowlisted for the canonical
install; normalization must remove the signed-shift UB while retaining
byte-identical terminfo output and behavior.  Reproducible evidence is in
`evidence/ncurses-6.6-oracle.json`.  The production-only
Cppcheck, GCC `-fanalyzer`, Clang analyzer/tidy, Flawfinder, and Sparse audit
is now complete and reproducibly locked in
`evidence/ncurses-6.6-static-analysis.json`.  It confirms the sanitizer's one
signed-shift defect and finds no second demonstrated canonical defect; Sparse
has no parser error.  The remaining reports are explicit translation and
ownership inventory, including analyzer paths disproved by control-flow
macros, initialization macros, configured invariants, and the zero-loss
public Valgrind paths.
Deterministic normalization changes exactly nine files: seven installed-tool
sources export multicall entrypoints while retaining standalone wrappers, all
three compiled-number byte-assembly sites promote the input byte to `unsigned`
before shifting, and four function-local static blank values receive unique
internal names so C2Rust can hoist them without colliding with ordinary C
locals.  Six program sources also retain their standalone `_nc_progname`
definition outside multicall builds but share one exported cell inside the
combined crate, preserving alias-specific diagnostics without duplicate C ABI
symbols.  These changes remove the canonical signed-shift UB and Rust naming
restrictions without changing values, storage duration, or control flow.  GCC
and Clang each pass all 27
canonical comparisons, both complete installed terminfo trees are
byte-identical, ASan/UBSan installation is clean, and all ten normalized native
personalities pass Valgrind.  Reproducible evidence is in
`evidence/ncurses-6.6-normalization.json`.  Strict independent C2Rust 0.22.1
probing translates all 264/264 normalized production sources with
`--fail-on-error` and `--preserve-unused-functions`.  The complete combined
266-file Rust crate has no translation-hole macros and compiles with zero
errors on stable Rust 1.99.0 after the shared deterministic modernization
pass.  It required no Ncurses-specific generated-Rust repair.  Complete
translation, pointer/unsafe, modernization, and compiler evidence is in
`evidence/ncurses-6.6-c2rust.json`.  The optimized archive exports each of the
seven entrypoints exactly once and links all ten native personalities without
canonical C residue or an external Ncurses library.  All 27 hybrid differential
cases and all ten Valgrind version paths pass.  `toe -a` compares exact record
multisets because upstream deliberately emits filesystem `readdir` order;
running both binaries against the same terminfo tree is byte-identical.
Reproducible hybrid evidence is in `evidence/ncurses-6.6-hybrid.json`;
all eleven public names are now integrated into the unified Rustbox dispatcher;
`ncursesw6-config` is an in-process native frontend rather than a copied shell
script.
The shared executable retains the seven translated entrypoints exactly once,
isolates 1,063 Ncurses implementation symbols, and has no canonical C residue
or external Ncurses dependency for those translated applets.  All 27 canonical
multicall comparisons, eleven multicall Valgrind paths, and the complete 884-case
cross-package dispatcher audit pass.  Reproducible unified evidence is in
`evidence/rustbox-multicall.json`.

GNU Findutils 4.10.0 is pinned to the latest canonical stable release from the
GNU archive.  The archive, detached signature, Bernhard Voelker release-key
fingerprint, and all 2,214 extracted source paths are authenticated before use.
The public scope is `find`, `xargs`, `locate`, and the generated `updatedb`
frontend; `frcode` is retained as a private database encoder.  SELinux is
explicitly disabled.  GCC, Clang, and ASan/UBSan independently compile the
same 218-source production closure.  GCC and Clang each pass 615 DejaGNU
checks plus the complete gnulib and shell suites with only the 41 identical
platform/expense skips, and all 38 stateful compiler differentials pass,
including filesystem traversal, `-exec`, null-delimited `xargs`, LOCATE02
encoding, and a functional `updatedb` rebuild.  The four compiled programs
have zero Valgrind errors and no direct, indirect, or possible loss on their
version/empty-input paths.

The sanitizer oracle demonstrates one canonical upstream defect:
`locate/locate.c:200` left-shifts signed `-1` while decoding a negative
LOCATE02 prefix delta.  Its minimal reproducer and exact diagnostic are locked
in the evidence; deterministic normalization must replace that expression
with defined signed-16-bit arithmetic while preserving database bytes and all
behavior.  Reproducible evidence is in
`evidence/findutils-4.10.0-oracle.json`.

Deterministic normalization changes exactly five sources.  The decoder now
constructs the unsigned 16-bit value from two bytes with defined arithmetic
and explicitly maps values above `0x7fff` into the signed range; it no longer
left-shifts a negative operand or relies on implementation-defined narrowing.
The same mechanical pass exports narrow C ABI entrypoints for `find`, `xargs`,
`locate`, and private `frcode` while retaining their conditional standalone
wrappers.
On LP64 targets, the existing `long double` to `uintmax_t` conversion in
`gl/lib/human.c` is spelled as an `unsigned long` conversion under the proven
`UINTMAX_MAX == ULONG_MAX` condition so C2Rust can represent the same range
and C conversion semantics; other targets retain the canonical cast.
GCC, Clang, and ASan/UBSan each retain the complete 218-source production
closure and pass all upstream suites.  All 76 canonical-versus-normalized
stateful comparisons pass, the sanitizer reports no undefined behavior or
address errors, and all four normalized programs pass Valgrind.  Reproducible
evidence is in `evidence/findutils-4.10.0-normalization.json`.

Strict C2Rust 0.22.1 translates all 193 installed-runtime sources with
`--fail-on-error` and `--preserve-unused-functions`; 24 gnulib test-only
sources and the standalone `getlimits` build helper are excluded from the
runtime closure.  Bison-generated `parse-datetime.c` is translated in a
singleton batch because its `#line` spans break only C2Rust's optional
declaration-map emitter; the translated code itself is complete.  The
no-hole stable crate contains 190 translated sources and exports all four
entrypoints exactly once.  The complete audit retains the three remaining
sources and records Rust's sealed `VaArgSafe` rejection of C2Rust's `f128`
wrapper; the hybrid therefore keeps only canonical `printf-args.c`,
`printf-parse.c`, and `vasnprintf.c` for the x86_64 SysV `long double`
variadic ABI.  All 38 hybrid stateful comparisons and all four Valgrind paths
pass.  Reproducible evidence is in `evidence/findutils-4.10.0-c2rust.json`
and `evidence/findutils-4.10.0-hybrid.json`.
All four public names are integrated into the unified dispatcher.  `updatedb`
is no longer an installed shell dependency: an in-binary C coordinator streams
the translated `find` through the already linked translated GNU `sort` and the
translated private `frcode` encoder.  All 38 stateful canonical-versus-multicall
cases, including byte-identical database generation, and all four multicall
Valgrind paths pass.  Reproducible evidence is in
`evidence/findutils-4.10.0-multicall.json` and
`evidence/rustbox-multicall.json`.

GNU Bison 3.8.2 is complete for its declared C/C++ scope.  The signed oracle's
exact 152-source production closure has a strict, no-hole C2Rust translation;
four canonical C files remain only for the x86_64 SysV `long double` variadic
ABI.  The unified multicall privately namespaces 1,063 Bison symbols and
exports native `bison` and `yacc` frontends.  Its 22 required skeleton, M4,
CSS, and XSLT resources (679,009 bytes) are embedded, and Bison invokes the
already integrated GNU M4 applet through `/proc/self/exe`; no installed Bison
datadir or external M4 executable is required.  `--print-datadir` materializes
a verified content-addressed resource directory that remains usable after the
command exits.  HTML report transformation still follows upstream by using
the optional external `xsltproc`; it is not part of the C/C++ completion gate.

The final artifact passes all 12 independent canonical comparisons, compiles
and runs five generated C/C++ parsers, matches native yacc behavior, leaks no
temporary extraction directories, and is clean under Valgrind.  A complete
776-group upstream inventory found 707 passing in-scope groups and 13
environmental skips; the other 56 groups are exactly the declared Java/D
exclusions.  The one diagnostic-name mismatch found by that sweep was fixed
and its upstream group passes on the final binary.  The combined executable is
27,504,976 bytes unstripped and 13,869,088 bytes stripped.  Reproducible
evidence is in `evidence/bison-3.8.2-oracle.json`,
`evidence/bison-3.8.2-normalization.json`,
`evidence/bison-3.8.2-translation.json`,
`evidence/bison-3.8.2-hybrid.json`, and
`evidence/bison-3.8.2-multicall.json`.  Its exact production-only Cppcheck,
GCC, Clang, Flawfinder, and Sparse audit is recorded in
`evidence/bison-3.8.2-static-analysis.json`; Cppcheck reaches all 152 source
files but its `strversion.c` child is bounded after reproducible nontermination,
while GCC successfully replays all 152 exact production compile actions.

curl 8.23.0 has a complete signed canonical oracle for the `curl` tool,
generated `curl-config` interface, and static libcurl runtime.  The deliberate
standalone profile depends only on libc/POSIX threads: external TLS,
compression, SSH, IDN, PSL, LDAP, GSS, HTTP/2, HTTP/3, and libuv libraries are
disabled until their canonical queued libraries are integrated.  It retains
15 built-in protocols (`dict`, `file`, `ftp`, `gopher`, `http`, `imap`, `ipfs`,
`ipns`, `mqtt`, `pop3`, `rtsp`, `smtp`, `telnet`, `tftp`, and `ws`).  GCC and
Clang expose the same exact 240-source production closure across 477 compile
actions each; both pass all 1,601 applicable cases from 2,138 considered
upstream tests.  All 12 deterministic cross-compiler comparisons and focused
Valgrind version/file-transfer gates pass with no errors or retained bytes.
Reproducible evidence is in `evidence/curl-8.23.0-oracle.json`.  Its exact
477-action Cppcheck, GCC, Clang, Flawfinder, and Sparse audit is recorded in
`evidence/curl-8.23.0-static-analysis.json`; GCC successfully replays every
configured action and Sparse completes without parser errors.  Deterministic
one-file normalization exports `rustbox_curl_main` while retaining the
standalone wrapper; all 1,601 applicable upstream tests, 12 canonical
differential cases, generated-source comparisons, and both Valgrind paths
remain clean in `evidence/curl-8.23.0-normalization.json`.  No-hole translation
is complete for all 240 production sources with `--fail-on-error` and
`--preserve-unused-functions`.  Stable Rust compiles and archives 239 translated
sources without holes; canonical `lib/mprintf.c` remains the sole C bridge
because stable Rust's sealed variadic ABI cannot express x86_64 SysV
`long double`.  The inactive `f128` and `num-traits` dependencies are removed
from the stable partition.  The exact closure, compiler diagnostics, archive,
pointer inventory, and boundary decision are recorded in
`evidence/curl-8.23.0-c2rust.json`.  The resulting hybrid passes all 12 exact
canonical CLI/file-protocol comparisons and both Valgrind paths with every
allocation freed.  A native in-process `curl-config` frontend matches the
generated canonical script in all 24 option and diagnostic cases;
`evidence/curl-8.23.0-hybrid.json` records both frontends, the one-source C
boundary, and package-independent dynamic dependency surface.  Both names are
now collision-isolated and integrated in the unified multicall executable.
The multicall curl retains all 12 exact canonical CLI/file comparisons,
`curl-config` retains all 24 exact option and diagnostic comparisons, and both
Valgrind paths remain error- and leak-free; this is recorded in
`evidence/curl-8.23.0-multicall.json` and the global multicall evidence.

GNU Inetutils 2.8 is pinned to its canonical signed GNU release and retains
all 16 clients and ten daemons in the no-systemd/no-PAM profile.  Independent
GCC and Clang builds cover the same exact 288-source production closure and
agree on all 52 help/version comparisons across the 26 executables.  Each
upstream suite reports 11 passes, five environmental skips, and the same one
capability-only failure: Docker correctly denies the test's attempt to change
the container hostname.  Four focused Valgrind paths report zero errors.
The oracle and that explicit environmental classification are recorded in
`evidence/inetutils-2.8-oracle.json`.  Deterministic normalization exports all
26 `rustbox_inetutils_*_main` entrypoints while retaining standalone wrappers,
makes one shared `libls` declaration explicit, and preserves the exact file
set.  Both compiler builds retain their complete
288-source closure, both upstream results, 104/104 canonical differential
comparisons, and four clean Valgrind paths.  This is recorded in
`evidence/inetutils-2.8-normalization.json`.  Strict C2Rust translation covers
all 288 production sources with no holes.  Rust 1.99 compiles 287 translated
sources into a stable audit archive; only gnulib's long-double variadic
extractor remains canonical C because Rust's sealed `VaArgSafe` trait cannot
represent that ABI operation.  The archive contains all 26 unique entrypoint
symbols, while its 132 cross-program declaration clashes explicitly show why
the formerly separate programs must be partitioned before hybrid parity and
multicall linkage.  This boundary and the raw-pointer inventory are recorded
in `evidence/inetutils-2.8-c2rust.json`.
The first program-scoped slice—`dnsdomainname`, `hostname`, `logger`, and
`whois`—uses the exact 20-, 24-, 22-, and 20-source canonical linker closures.
All four stable Rust hybrids have no translation holes or C residue, pass
22/22 exact behavioral comparisons and four clean Valgrind runs, and remain
separate until all 26 programs are ready for collision-isolated multicall
linkage.  This is recorded in
`evidence/inetutils-2.8-hybrid-small-01.json`.
The second slice adds `rexec`, `tftp`, `traceroute`, `ifconfig`, `ping`, and
`ping6`.  Its exact linker-map closures contain 147 source instances (52
unique sources), including every directly linked multi-object component of
`ifconfig`, `ping`, and `ping6`.  All six no-hole, zero-C-residue stable Rust
hybrids pass 38/38 exact non-network canonical comparisons and six clean
Valgrind paths.  This brings program-scoped parity to 10/26 and is recorded in
`evidence/inetutils-2.8-hybrid-small-02.json`.
The remaining client slice—`rcp`, `rlogin`, `rsh`, `ftp`, `talk`, and
`telnet`—covers 159 source instances (71 unique sources), passes 33/33 exact
canonical comparisons including offline FTP and Telnet command loops, and has
six clean Valgrind paths.  Telnet retains canonical `lib/printf-args.c` as the
same one-source long-double variadic ABI boundary documented by the full audit;
all other sources are stable Rust and no translation holes remain.  All 16
Inetutils clients now have program-scoped hybrid parity, recorded in
`evidence/inetutils-2.8-hybrid-clients-03.json`; the ten daemons remain.
The daemon slice completes `inetd`, `rexecd`, `rlogind`, `rshd`, `syslogd`,
`tftpd`, `uucpd`, `ftpd`, `talkd`, and `telnetd`.  Their exact closures cover
269 source instances (86 unique sources), all ten stable Rust hybrids compile
without holes or C residue, and they pass 40/40 exact canonical CLI comparisons
plus ten clean Valgrind paths.  All 26 Inetutils programs now have separate
program-scoped hybrid parity.  Each program's formerly global symbol surface is
now privately namespaced and all 26 are linked into the unified multicall.
Every one of the preceding 133 differential cases passes through Rustbox, as do
26 multicall Valgrind version paths; the complete 764-case cross-package
dispatcher audit also remains exact.  The daemon and final integration evidence
are `evidence/inetutils-2.8-hybrid-daemons-04.json` and
`evidence/inetutils-2.8-multicall.json`.

## Work queue after util-linux

This queue starts only after all in-scope util-linux applets reach canonical
parity and the completed Coreutils and util-linux translations are linked and
verified together as the single `rustbox` multicall executable.  That gate is
now satisfied.
This ordering is from lower to higher estimated translation and integration
complexity; build dependencies may be prepared earlier when a queued package
requires them.  Names include canonical installed aliases, but not examples or
test-only binaries.  The duplicate `gzip` request is represented once.

Standalone library-only work stays isolated and does not block the utility
queue.  Zlib 1.4 is complete at canonical parity as an isolated stable Rust
library; its final shared/static linkage remains deferred.  Readline's
library-only tranche is likewise deferred until a utility consumer requires
it.  Libraries that are inseparable from an installed utility may be built and
verified with that utility, but executable integration remains the priority.

Library-only checkpoints (outside the active utility order):

- [x] zlib 1.4 — isolated stable Rust library at canonical parity; no
  installed applet (`minigzip` is an example/test helper).
- [ ] Readline — isolated `readline` and `history` libraries; no canonical
  installed applet (`rlfe` remains an example).

1. Small and single-purpose utilities:
   - [x] pkgconf 3.0.11 — `pkgconf`, its compatible `pkg-config` alias,
     `bomtool`, `pccritic`, and `spdxtool`; use this maintained implementation
     instead of the dormant freedesktop pkg-config 0.29.2 codebase.
   - [x] M4 1.4.21 — `m4`; integrated at canonical parity.
   - [x] File 5.48 — `file`; integrated at canonical parity.
   - [x] GNU patch 2.8 — `patch`; integrated at canonical parity.
   - [x] GNU sed 4.10 — `sed`; integrated at canonical parity.
   - [x] Diffutils 3.12 — `cmp`, `diff`, `diff3`, `sdiff`; integrated at
     canonical parity.
   - [x] Grep 3.12 — `grep`, `egrep`, `fgrep`; integrated at canonical parity.
   - [x] bc 1.08.2 / dc 1.5.2 — `bc`, `dc`; integrated at canonical parity.
   - [x] attr 2.6.0 — `attr`, `getfattr`, `setfattr`; integrated at canonical
     parity.
   - [x] acl 2.4.0 — `chacl`, `getfacl`, `setfacl`; integrated at canonical
     parity.
   - [x] LZ4 1.11.1 — `lz4`, `lz4c`, `lz4cat`, `unlz4`; integrated at
     canonical parity.
2. Compression, archive, and terminal foundations:
   - [x] GNU Gzip 1.14 — translated hybrid at canonical parity; native `gzip`,
     `gunzip`, `zcat`, `uncompress`, `zcmp`, `zdiff`, `zforce`, `zgrep`,
     `zegrep`, `zfgrep`, `zless`, `zmore`, `znew`, and `gzexe` integrated.
   - [x] XZ Utils 5.8.4 — signed canonical oracle, normalization, static audit,
     complete stable translation, and multicall integration finished for all 23 names:
     `xz`, `unxz`, `xzcat`, `lzma`, `unlzma`, `lzcat`, `xzdec`, `lzmadec`,
     `lzmainfo`, `xzcmp`, `xzdiff`, `xzegrep`, `xzfgrep`, `xzgrep`, `xzless`,
     `xzmore`, `lzcmp`, `lzdiff`, `lzegrep`, `lzfgrep`, `lzgrep`, `lzless`, and
     `lzmore`; all native frontends are internal and canonical parity is complete.
   - [x] zstd 1.5.7 — canonical checksum oracle, five-tool audit, verified
     portable-C normalization, complete no-hole stable translation, and
     hybrid parity finished for `zstd`, `zstdmt`, `unzstd`, `zstdcat`,
     `zstdgrep`, and `zstdless`; multicall integration is complete.
   - [x] GNU tar 1.35 — `tar`, `rmt`; translated hybrid and unified multicall
     integration at canonical parity with internal translated ACL linkage.
   - [x] Ncurses 6.6 — signed canonical oracle complete for `captoinfo`,
     `clear`, `infocmp`, `infotocap`, `tabs`, `tic`, `toe`, `tput`, `tset`,
     `reset`, and generated `ncursesw6-config`; shared/static `ncursesw`,
     `panelw`, `formw`, `menuw`, `tinfow`, and `ticw` are included.  Static
     audit, deterministic normalization, complete stable translation,
     ten-name hybrid parity, and unified multicall integration are complete;
     the one
     sanitizer-confirmed signed-shift defect is removed with byte-identical
     terminfo output.  All 27 multicall differential cases and all ten
     multicall Valgrind version paths pass.
   - [x] Less 710 — canonical `less` and private-runtime `lessecho`; full
     translation, standalone hybrid parity, and unified multicall integration
     are complete.  Upstream removed the standalone
     `lesskey` program in version 706 and now parses lesskey source directly
     inside `less`, so it is intentionally not resurrected.
3. Multi-tool text processing and source generators:
   - [x] GNU Findutils 4.10.0 — signed canonical GCC/Clang/sanitizer oracle
     and deterministic normalization complete for `find`, `xargs`, `locate`,
     and `updatedb`; 76/76 canonical-versus-normalized differential cases
     pass.  The sanitizer-confirmed LOCATE02 signed-shift defect is removed
     with defined arithmetic, and all four compiled programs export multicall
     entrypoints while retaining standalone wrappers.  Complete no-hole
     translation, stable reachable compilation, four-program hybrid parity,
     Valgrind verification, native in-binary `updatedb`, and unified multicall
     integration all pass.
   - [x] Gawk 5.4.0 — `gawk` and `awk` have complete no-hole stable
     translation and unified multicall parity; the installed `gawkbug` shell
     workflow is replaced by a native in-binary frontend with canonical
     editor, mailer, and dead-letter recovery parity.
   - [x] Flex 2.6.4 — signed canonical release and full oracle complete for
     `flex` and upstream's `flex++` link; GCC, Clang, and ASan/UBSan each pass
     all 114 upstream tests, and all 14 independent compiler/generator cases
     pass.  Deterministic one-file normalization preserves another 228
     upstream test passes and all 14 canonical differential cases, exports the
     multicall entrypoint, and removes the three canonical early-exit `scanopt`
     leaks with zero lost bytes on help, version, and error paths.  Its exact
     21-source production closure has a complete no-hole stable translation.
     The translated hybrid passes all 114 upstream tests, all 14 generator and
     scanner comparisons, three native `flex++`/`lex` frontend comparisons,
     and leak-free help, version, and error exits.  Unified multicall
     integration is complete for `flex`, `flex++`, and native `lex`; all 764
     dispatcher comparisons and all 14,022 prior batch regressions pass.
   - [x] Bison 3.8.2 — `bison`, `yacc`; signed canonical oracle, deterministic
     normalization, complete no-hole stable translation, embedded C/C++
     resource closure, native yacc frontend, and unified multicall parity are
     complete.  D and Java output remain explicitly out of scope.
4. Network-facing suites:
   - [x] curl 8.23.0 — `curl`, native `curl-config`, and the static translated
     libcurl runtime are collision-isolated in the unified multicall binary.
     The deliberately dependency-free profile retains 15 built-in protocols;
     optional TLS/compression protocols remain queued with their canonical
     libraries.
   - [x] Inetutils 2.8 — signed 26-executable canonical oracle, deterministic
     26-entrypoint normalization, complete 288-source no-hole translation, and
     stable compile audit, all 26 program-scoped hybrids at canonical parity,
     and collision-isolated multicall integration are complete.  Clients:
     `dnsdomainname`, `ftp`,
     `hostname`, `ifconfig`, `logger`,
     `ping`, `ping6`, `rcp`, `rexec`, `rlogin`, `rsh`, `talk`, `telnet`,
     `tftp`, `traceroute`, `whois`; and canonical daemons `ftpd`, `inetd`,
     `rexecd`, `rlogind`, `rshd`, `syslogd`, `talkd`, `telnetd`, `tftpd`,
     `uucpd`.
5. Large Linux system suites:
   - [x] Kmod 34.3 — `kmod` and its installed `depmod`, `insmod`, `lsmod`,
     `modinfo`, `modprobe`, and `rmmod` compatibility links, plus the shared
     `libkmod` runtime.  Its signed 26-source canonical oracle is complete:
     GCC and Clang each pass all 16 upstream tests, all 25 independent command
     and module-fixture comparisons agree, seven Valgrind paths are clean, and
     five production-only analyzer passes complete.  Deterministic normalization
     exports the shared `rustbox_kmod_main` engine while retaining standalone
     dispatch; GCC and Clang each preserve all 16 tests, all 50 compiler-specific
     canonical comparisons pass, and seven normalized Valgrind paths are clean.
     All 26 production sources now have a complete, no-hole stable Rust
     translation with no canonical C residue.  The seven command names are
     collision-isolated in the unified multicall executable, pass all 25 command
     and module-fixture comparisons again, and are Valgrind-clean.  XZ, zlib, and
     zstd module decompression remains available through the canonical libraries.
   - [x] Procps-ng 4.0.7 — `free`, `hugetop`, `kill`, `pgrep`, `pidof`,
     `pidwait`, `pkill`, `pmap`, `ps`, `pwdx`, `skill`, `slabtop`, `snice`,
     `sysctl`, `tload`, `top`, `uptime`, `vmstat`, `w`, `watch`, plus the
     shared `libproc2` runtime.  The signed canonical 4.0.7 oracle is complete
     with systemd, elogind, and SELinux disabled while Ncurses and the optional
     `skill`/`snice` pair remain enabled.  GCC and Clang each pass 158 DejaGNU
     command checks and eight unit checks; all 51 independent public-interface
     comparisons agree, all 49 production sources complete five analyzer
     passes, and all 20 version paths have recorded Valgrind behavior.  Upstream
     `sysctl --version` retains its canonical 16-byte exit leak; the other 19
     paths are clean.  Deterministic normalization now exports 17 engines for
     all 20 programs while preserving standalone dispatch.  GCC and Clang each
     retain all 166 upstream passes, all 102 compiler-specific canonical
     comparisons pass, every expected exported definition is unique, and all
     20 normalized resource paths match the canonical allocation baseline.  A
     mechanical portability pass also replaces all three GNU computed-goto
     tables with enum-and-switch dispatch: 34 `readproc` status actions, 27
     `ps` personalities, and 37 GNU long options.  These are rechecked by the
     complete normalized matrix.  Strict C2Rust translation now covers all 49
     production sources with no holes or canonical C residue.  Three asserted
     representation repairs and two isolated cross-program export collisions
     produce a complete release archive while preserving all 29 thread-local
     attributes.  All 17 engines link behind the 20 command names and pass all
     51 canonical hybrid comparisons; their resource behavior also matches the
     canonical baseline (including `sysctl`'s existing 16-byte exit leak).
     Unified Rustbox integration is complete: 422 Procps symbols are privately
     namespaced, all 51 canonical comparisons pass through the combined binary,
     and all 20 resource paths retain their canonical allocation behavior.
     GNU Coreutils keeps the unqualified `kill` and `uptime` names;
     `procps-kill` and `procps-uptime` explicitly select Procps-ng.  Exact
     evidence is recorded in `evidence/procps-ng-4.0.7-multicall.json` and
     `evidence/rustbox-multicall.json`.
   - [x] Shadow 4.20.4 — `chage`, `chfn`, `chgpasswd`, `chpasswd`, `chsh`,
     `faillog`, `getsubids`, `gpasswd`, `groupadd`, `groupdel`, `groupmod`,
     `grpck`, `grpconv`, `grpunconv`, `lastlog`, `login`, `newgidmap`,
     `newgrp`, `newuidmap`, `newusers`, `nologin`, `passwd`, `pwck`, `pwconv`,
     `pwunconv`, `su`, `useradd`, `userdel`, `usermod`, `vipw`, and the
     installed `sg` and `vigr` compatibility links, plus `libshadow` and
     `libsubid`.  Use the canonical `shadow-maint/shadow` release with SELinux
     and systemd integration disabled; separately verify duplicate public
     names supplied by util-linux before choosing final dispatcher precedence.
     Version 4.20.4 supersedes the initially queued 4.20.3 and includes the
     upstream `newuidmap`/`newgidmap` security fixes.
     The signed canonical oracle covers the exact 201-source production
     closure with independent GCC and Clang builds, both upstream unit suites,
     every public help/version surface, and isolated prefix-root mutations of
     synthetic passwd/group databases.  Normalization and translation follow
     only after that oracle checkpoint is committed.  Deterministic
     normalization now exports all 30 real entrypoint engines while retaining
     standalone wrappers and the canonical `sg`/`vigr` aliases.  Both compiler
     builds, all 16 unit-test runs, all 158 canonical comparisons, and all 32
     resource paths match their oracle baselines.  Exact evidence is recorded
     in `evidence/shadow-4.20.4-oracle.json` and
     `evidence/shadow-4.20.4-normalization.json`.  The first strict translator
     probe exposed unsupported C11 `_Generic` selections rather than emitting
     holes; those compile-time selections are now deterministically lowered to
     their target-ABI C calls.  The next probe exposed auto-typed pointer-span
     helpers; these now use single-evaluation concrete inline functions.  The
     resulting 49-file normalized scope has passed the same complete gates.
     Strict translation completes all 196 selected sources without holes,
     excluding only five named non-installed helper executables.  The complete
     generated crate now type-checks and release-builds after 22 asserted ABI
     representation repairs across 13 files; the repair script always starts
     from the untouched strict-translation output and records every changed
     site and before/after digest.  The 32-name translated hybrid exposes all
     30 real engines exactly once, passes all 79 canonical comparisons and
     matches all 32 canonical resource profiles (including the known
     `gpasswd` baseline).  It is 712,056 bytes stripped.  Translation, unsafe
     inventory, linkage, size, and hybrid evidence is recorded in
     `evidence/shadow-4.20.4-c2rust.json`.  Unified multicall integration is
     complete: 265 Shadow symbols are privately namespaced and the 211
     byte-identical Rust runtime archive members shared with Procps-ng are
     coalesced exactly, without permitting duplicate definitions.  All 79
     comparisons and all 32 canonical resource profiles pass through Rustbox;
     util-linux retains precedence for its eight colliding names, exposed for
     Shadow through `shadow-` aliases.  Exact evidence is recorded in
     `evidence/shadow-4.20.4-multicall.json` and
     `evidence/rustbox-multicall.json`.
   - [x] IPRoute2 7.3.0 — `arpd`, `bridge`, `ctstat`, `dcb`, `devlink`,
     `dpll`, `genl`, `ifstat`, `ip`, `lnstat`, `netshaper`, `nstat`, `rdma`,
     `routel`, `rtacct`, `rtmon`, `rtstat`, `ss`, `tc`, `tipc`, and `vdpa`.
     The current signed kernel.org release no longer installs the former
     `ifcfg`, `routef`, or `rtpr` scripts; it adds the canonical `dpll` and
     `netshaper` programs.  Its 21-name oracle comprises 18 native engines,
     two `lnstat` aliases, and the Python `routel` frontend.  Independent GCC
     and Clang builds cover the same 264 compiled sources (260 production
     utility sources after excluding four netem table generators), all 63
     public comparisons match, and all 20 native resource paths are clean.
     Both isolated privileged suites pass 18/19 tests; the identical
     `bareudp` failure is a documented Docker-host kernel limitation.  The
     five-tool static-analysis baseline and exact signed-source evidence are
     recorded in `evidence/iproute2-7.3.0-oracle.json`.  Deterministic
     normalization changes the 18 native entrypoint source files, exports one
     unique multicall ABI per engine, and retains standalone wrappers.  It
     additionally expands C2Rust-incompatible GNU omitted-middle pointer
     conditionals with explicit single-evaluation temporaries; because two of
     those files also own entrypoints, the 29 transformations touch
     exactly 27 unique source files.
     Both normalized compilers again pass all 63 public comparisons, all 20
     native resource paths, and the same 18/19 upstream tests.  Exact scope
     and before/after hashes are recorded in
     `evidence/iproute2-7.3.0-normalization.json`.
     Exact linker-map closures then split those engines into 18 independent
     C2Rust crates: 460 source occurrences over 261 unique production sources.
     All 496 generated Rust files (1,115,530 raw lines and 265,323 raw-pointer
     type occurrences) translate without holes, type-check, and release-build
     after 46 asserted representation repairs.  The 18 standalone hybrids pass
     all 54 canonical CLI comparisons and 18 Valgrind paths.  Per-engine
     archives, binaries, link maps, symbols, repairs, and hashes are recorded
     in `evidence/iproute2-7.3.0-program-hybrids.json`.
     Unified integration exposes all 21 names, privately renames 8,308 engine
     symbols across 18 namespaces, and replaces Python `routel` with an
     in-process native frontend.  All 66 global comparisons and 21 Valgrind
     paths pass; `evidence/iproute2-7.3.0-multicall.json` records the exact
     binary, map, entrypoint, dispatch, and resource evidence.
   - [x] E2fsprogs 1.47.4 — `badblocks`, `chattr`, `compile_et`, `debugfs`,
     `dumpe2fs`, `e2freefrag`, `e2fsck`, `e2image`, `e2initrd_helper`,
     `e2label`, `e2mmpstatus`, `e2scrub`, `e2scrub_all`, `e2undo`, `e4crypt`,
     `e4defrag`, `filefrag`, `fsck`, `fsck.ext2`, `fsck.ext3`, `fsck.ext4`,
     `fuse2fs`, `logsave`, `lsattr`, `mk_cmds`, `mke2fs`, `mkfs.ext2`,
     `mkfs.ext3`, `mkfs.ext4`, `mklost+found`, `resize2fs`, and `tune2fs`.
     The signed oracle deliberately uses util-linux's canonical `findfs`,
     `blkid`, and UUID tools rather than duplicating them here.  Deterministic
     normalization exports 20 unique native engines covering 28 ELF names;
     the other four installed names are upstream scripts.  GCC and Clang have
     identical 232-source production closures, each matches its signed oracle
     in 96/96 public comparisons, and the normalized builds match each other
     in another 96/96.  Each full upstream suite passes 396 tests and skips
     ten; the one identical failure is the documented Docker backing-storage
     allocation artifact.  All 28 ELF Valgrind paths, four script syntax
     gates, and 40 exported-symbol checks pass.  Exact evidence is in
     `evidence/e2fsprogs-1.47.4-normalization.json`.
     The four upstream scripts are also replaced by native C ABI frontends.
     `compile_et` and `mk_cmds` embed the signed upstream awk/sed templates and
     reproduce generated files byte-for-byte; `e2scrub` and `e2scrub_all`
     implement the mount, journal, LVM snapshot, two-stage fsck, marking,
     cleanup, retry, and optional trim orchestration without a shell or Python.
     All 48 canonical CLI/generator comparisons—including isolated fresh
     generation and metadata-preserving repeat runs—and eight deterministic
     canonical-versus-native fake-LVM flows pass, as do four Valgrind paths
     and zero-diagnostic Cppcheck, GCC analyzer, and Clang analyzer gates.
     Real block-device mutation is deliberately not run.  Systemd integration
     is omitted by policy; narrow exec fallbacks remain for the external LVM
     commands, udev settling, and fstrim until those suites enter scope.  See
     `evidence/e2fsprogs-1.47.4-script-frontends.json`.
     Exact linker-map closures split the native programs into 20 independent
     translations: 1,061 Rust files, 4,171,263 raw lines, 401,012 raw-pointer
     type occurrences, zero holes, and 25 asserted repairs.  All 20 Cargo
     checks and release archives pass; their 28 public ELF names match the
     canonical oracle in 112/112 standalone cases with 20 clean Valgrind
     paths.  Unified integration exposes all 32 names, preserves util-linux
     ownership of `fsck` through the explicit `e2fsprogs-fsck` spelling,
     removes 3,966 byte-identical runtime members, and privately renames 8,979
     symbols across 20 namespaces.  All 112 global canonical comparisons,
     32 global Valgrind paths, and the complete 884-case prior-package
     regression pass.  Exact translation and global evidence is in
     `evidence/e2fsprogs-1.47.4-program-hybrids.json` and
     `evidence/e2fsprogs-1.47.4-multicall.json`.

## Applet inventory

This list is generated from the pinned upstream build definitions by
`scripts/generate_inventory.py`.  Keep it current as each applet advances from
inventory through normalization, translation, integration, and canonical-test
parity.

<!-- BEGIN APPLET INVENTORY -->

### GNU Coreutils 9.12 (108)

- [x] `[` — hybrid canonical parity; repair score 7
- [x] `arch` — hybrid canonical parity; repair score 5
- [x] `b2sum` — hybrid canonical parity; repair score 7
- [x] `base32` — hybrid canonical parity; repair score 7
- [x] `base64` — hybrid canonical parity; repair score 5
- [x] `basename` — hybrid canonical parity; repair score 5
- [x] `basenc` — hybrid canonical parity; repair score 7
- [x] `cat` — hybrid canonical parity; repair score 5
- [ ] `chcon` — excluded by the no-SELinux policy
- [x] `chgrp` — hybrid canonical parity; repair score 5
- [x] `chmod` — hybrid canonical parity; repair score 7
- [x] `chown` — hybrid canonical parity; repair score 7
- [x] `chroot` — hybrid canonical parity; repair score 7
- [x] `cksum` — hybrid canonical parity; repair score 5
- [x] `comm` — hybrid canonical parity; repair score 5
- [x] `cp` — hybrid canonical parity; repair score 7
- [x] `csplit` — hybrid canonical parity; repair score 7
- [x] `cut` — hybrid canonical parity; repair score 7
- [x] `date` — hybrid canonical parity; repair score 7
- [x] `dd` — hybrid canonical parity; repair score 7
- [x] `df` — hybrid canonical parity; repair score 7
- [x] `dir` — hybrid canonical parity; repair score 5
- [x] `dircolors` — hybrid canonical parity; repair score 5
- [x] `dirname` — hybrid canonical parity; repair score 5
- [x] `du` — hybrid canonical parity; repair score 7
- [x] `echo` — hybrid canonical parity; repair score 5
- [x] `env` — hybrid canonical parity; repair score 7
- [x] `expand` — hybrid canonical parity; repair score 7
- [x] `expr` — hybrid canonical parity; repair score 7
- [x] `factor` — hybrid canonical parity; repair score 5
- [x] `false` — hybrid canonical parity; repair score 3
- [x] `fmt` — hybrid canonical parity; repair score 5
- [x] `fold` — hybrid canonical parity; repair score 7
- [x] `groups` — hybrid canonical parity; repair score 5
- [x] `head` — hybrid canonical parity; repair score 7
- [x] `hostid` — hybrid canonical parity; repair score 5
- [x] `hostname` — hybrid canonical parity; repair score 5
- [x] `id` — hybrid canonical parity; repair score 7
- [x] `install` — hybrid canonical parity; repair score 7
- [x] `join` — hybrid canonical parity; repair score 7
- [x] `kill` — hybrid canonical parity; repair score 7
- [x] `link` — hybrid canonical parity; repair score 5
- [x] `ln` — hybrid canonical parity; repair score 7
- [x] `logname` — hybrid canonical parity; repair score 5
- [x] `ls` — hybrid canonical parity; repair score 7
- [x] `md5sum` — hybrid canonical parity; repair score 5
- [x] `mkdir` — hybrid canonical parity; repair score 7
- [x] `mkfifo` — hybrid canonical parity; repair score 5
- [x] `mknod` — hybrid canonical parity; repair score 5
- [x] `mktemp` — hybrid canonical parity; repair score 5
- [x] `mv` — hybrid canonical parity; repair score 7
- [x] `nice` — hybrid canonical parity; repair score 5
- [x] `nl` — hybrid canonical parity; repair score 5
- [x] `nohup` — hybrid canonical parity; repair score 5
- [x] `nproc` — hybrid canonical parity; repair score 5
- [x] `numfmt` — hybrid canonical parity; repair score 5
- [x] `od` — hybrid canonical parity; repair score 5
- [x] `paste` — hybrid canonical parity; repair score 7
- [x] `pathchk` — hybrid canonical parity; repair score 5
- [x] `pinky` — hybrid canonical parity; repair score 5
- [x] `pr` — hybrid canonical parity; repair score 7
- [x] `printenv` — hybrid canonical parity; repair score 5
- [x] `printf` — hybrid canonical parity; repair score 5
- [x] `ptx` — hybrid canonical parity; repair score 7
- [x] `pwd` — hybrid canonical parity; repair score 5
- [x] `readlink` — hybrid canonical parity; repair score 5
- [x] `realpath` — hybrid canonical parity; repair score 5
- [x] `rm` — hybrid canonical parity; repair score 7
- [x] `rmdir` — hybrid canonical parity; repair score 7
- [ ] `runcon` — excluded by the no-SELinux policy
- [x] `seq` — hybrid canonical parity; repair score 5
- [x] `sha1sum` — hybrid canonical parity; repair score 5
- [x] `sha224sum` — hybrid canonical parity; repair score 5
- [x] `sha256sum` — hybrid canonical parity; repair score 5
- [x] `sha384sum` — hybrid canonical parity; repair score 5
- [x] `sha512sum` — hybrid canonical parity; repair score 5
- [x] `shred` — hybrid canonical parity; repair score 7
- [x] `shuf` — hybrid canonical parity; repair score 5
- [x] `sleep` — hybrid canonical parity; repair score 5
- [x] `sort` — hybrid canonical parity; repair score 7
- [x] `split` — hybrid canonical parity; repair score 7
- [x] `stat` — hybrid canonical parity; repair score 7
- [x] `stdbuf` — hybrid canonical parity; repair score 5
- [x] `stty` — hybrid canonical parity; repair score 7
- [x] `sum` — hybrid canonical parity; repair score 7
- [x] `sync` — hybrid canonical parity; repair score 5
- [x] `tac` — hybrid canonical parity; repair score 5
- [x] `tail` — hybrid canonical parity; repair score 7
- [x] `tee` — hybrid canonical parity; repair score 7
- [x] `test` — hybrid canonical parity; repair score 7
- [x] `timeout` — hybrid canonical parity; repair score 5
- [x] `touch` — hybrid canonical parity; repair score 7
- [x] `tr` — hybrid canonical parity; repair score 7
- [x] `true` — hybrid canonical parity; repair score 3
- [x] `truncate` — hybrid canonical parity; repair score 5
- [x] `tsort` — hybrid canonical parity; repair score 5
- [x] `tty` — hybrid canonical parity; repair score 5
- [x] `uname` — hybrid canonical parity; repair score 7
- [x] `unexpand` — hybrid canonical parity; repair score 7
- [x] `uniq` — hybrid canonical parity; repair score 5
- [x] `unlink` — hybrid canonical parity; repair score 5
- [x] `uptime` — hybrid canonical parity; repair score 5
- [x] `users` — hybrid canonical parity; repair score 5
- [x] `vdir` — hybrid canonical parity; repair score 5
- [x] `wc` — hybrid canonical parity; repair score 5
- [x] `who` — hybrid canonical parity; repair score 7
- [x] `whoami` — hybrid canonical parity; repair score 5
- [x] `yes` — hybrid canonical parity; repair score 5

### util-linux 2.42.4 (155)

- [x] `addpart` — hybrid canonical parity; repair score 5
- [x] `agetty` — hybrid canonical parity; repair score 5
- [x] `bits` — hybrid canonical parity; repair score 3
- [x] `blkdiscard` — hybrid canonical parity; repair score 3
- [x] `blkid` — hybrid canonical parity; repair score 5
- [x] `blkpr` — hybrid canonical parity; repair score 5
- [x] `blkzone` — hybrid canonical parity; repair score 5
- [x] `blockdev` — hybrid canonical parity; repair score 5
- [x] `cal` — hybrid canonical parity; repair score 5
- [x] `cfdisk` — hybrid canonical parity; repair score 5
- [x] `chcpu` — hybrid canonical parity; repair score 5
- [x] `chfn` — hybrid canonical parity; repair score 5
- [x] `chmem` — hybrid canonical parity; repair score 5
- [x] `choom` — hybrid canonical parity; repair score 3
- [x] `chrt` — hybrid canonical parity; repair score 5
- [x] `chsh` — hybrid canonical parity; repair score 3
- [x] `col` — hybrid canonical parity; repair score 5
- [x] `colcrt` — hybrid canonical parity; repair score 3
- [x] `colrm` — hybrid canonical parity; repair score 3
- [x] `column` — hybrid canonical parity; repair score 5
- [x] `copyfilerange` — hybrid canonical parity; repair score 3
- [x] `coresched` — hybrid canonical parity; repair score 5
- [x] `ctrlaltdel` — hybrid canonical parity; repair score 3
- [x] `delpart` — hybrid canonical parity; repair score 5
- [x] `dmesg` — hybrid canonical parity; repair score 5
- [x] `eject` — hybrid canonical parity; repair score 5
- [x] `enosys` — hybrid canonical parity; repair score 5
- [x] `exch` — hybrid canonical parity; repair score 3
- [x] `fadvise` — hybrid canonical parity; repair score 3
- [x] `fallocate` — hybrid canonical parity; repair score 5
- [x] `fdformat` — hybrid canonical parity; repair score 3
- [x] `fdisk` — hybrid canonical parity; repair score 5
- [x] `fincore` — hybrid canonical parity; repair score 5
- [x] `findfs` — hybrid canonical parity; repair score 5
- [x] `findmnt` — hybrid canonical parity; repair score 5
- [x] `flock` — hybrid canonical parity; repair score 5
- [x] `fsck` — hybrid canonical parity; repair score 5
- [x] `fsck.cramfs` — hybrid canonical parity; repair score 5
- [x] `fsck.minix` — hybrid canonical parity; repair score 5
- [x] `fsfreeze` — hybrid canonical parity; repair score 5
- [x] `fstrim` — hybrid canonical parity; repair score 5
- [x] `getino` — hybrid canonical parity; repair score 3
- [x] `getopt` — hybrid canonical parity; repair score 5
- [x] `hardlink` — hybrid canonical parity; repair score 5
- [x] `hexdump` — hybrid canonical parity; repair score 5
- [x] `hwclock` — hybrid canonical parity; repair score 5
- [x] `i386` — hybrid canonical parity; repair score 3
- [x] `ia64` — hybrid canonical parity; repair score 3
- [x] `ionice` — hybrid canonical parity; repair score 3
- [x] `ipcmk` — hybrid canonical parity; repair score 3
- [x] `ipcrm` — hybrid canonical parity; repair score 5
- [x] `ipcs` — hybrid canonical parity; repair score 5
- [x] `irqtop` — hybrid canonical parity; repair score 5
- [x] `isosize` — hybrid canonical parity; repair score 5
- [x] `kill` — hybrid canonical parity; repair score 5
- [x] `last` — hybrid canonical parity; repair score 5
- [x] `lastb` — hybrid canonical parity; repair score 5
- [x] `lastlog2` — hybrid canonical parity; repair score 3
- [x] `ldattach` — hybrid canonical parity; repair score 5
- [x] `line` — hybrid canonical parity; repair score 3
- [x] `linux32` — hybrid canonical parity; repair score 3
- [x] `linux64` — hybrid canonical parity; repair score 3
- [x] `logger` — hybrid canonical parity; repair score 5
- [x] `login` — hybrid canonical parity; repair score 5
- [x] `look` — hybrid canonical parity; repair score 3
- [x] `losetup` — hybrid canonical parity; repair score 5
- [x] `lsblk` — hybrid canonical parity; repair score 5
- [x] `lsclocks` — hybrid canonical parity; repair score 5
- [x] `lscpu` — hybrid canonical parity; repair score 5
- [x] `lsfd` — hybrid canonical parity; repair score 5
- [x] `lsipc` — hybrid canonical parity; repair score 5
- [x] `lsirq` — hybrid canonical parity; repair score 3
- [x] `lslocks` — hybrid canonical parity; repair score 5
- [x] `lslogins` — hybrid canonical parity; repair score 5
- [x] `lsmem` — hybrid canonical parity; repair score 5
- [x] `lsns` — hybrid canonical parity; repair score 5
- [x] `mcookie` — hybrid canonical parity; repair score 3
- [x] `mesg` — hybrid canonical parity; repair score 5
- [x] `mips` — hybrid canonical parity; repair score 3
- [x] `mips32` — hybrid canonical parity; repair score 3
- [x] `mips64` — hybrid canonical parity; repair score 3
- [x] `mkfs` — hybrid canonical parity; repair score 5
- [x] `mkfs.bfs` — hybrid canonical parity; repair score 5
- [x] `mkfs.cramfs` — hybrid canonical parity; repair score 5
- [x] `mkfs.minix` — hybrid canonical parity; repair score 5
- [x] `mkswap` — hybrid canonical parity; repair score 5
- [x] `more` — hybrid canonical parity; repair score 5
- [x] `mount` — hybrid canonical parity; repair score 5
- [x] `mountpoint` — hybrid canonical parity; repair score 3
- [x] `namei` — hybrid canonical parity; repair score 5
- [x] `newgrp` — hybrid canonical parity; repair score 3
- [x] `nologin` — hybrid canonical parity; repair score 5
- [x] `nsenter` — hybrid canonical parity; repair score 5
- [x] `parisc` — hybrid canonical parity; repair score 3
- [x] `parisc32` — hybrid canonical parity; repair score 3
- [x] `parisc64` — hybrid canonical parity; repair score 3
- [x] `partx` — hybrid canonical parity; repair score 5
- [x] `pg` — hybrid canonical parity; repair score 5
- [x] `pipesz` — hybrid canonical parity; repair score 3
- [x] `pivot_root` — hybrid canonical parity; repair score 5
- [x] `ppc` — hybrid canonical parity; repair score 3
- [x] `ppc32` — hybrid canonical parity; repair score 3
- [x] `ppc64` — hybrid canonical parity; repair score 3
- [x] `prlimit` — hybrid canonical parity; repair score 5
- [x] `raw` — hybrid canonical parity; repair score 3
- [x] `readprofile` — hybrid canonical parity; repair score 5
- [x] `rename` — hybrid canonical parity; repair score 3
- [x] `renice` — hybrid canonical parity; repair score 3
- [x] `resizepart` — hybrid canonical parity; repair score 5
- [x] `rev` — hybrid canonical parity; repair score 3
- [x] `rfkill` — hybrid canonical parity; repair score 5
- [x] `rtcwake` — hybrid canonical parity; repair score 5
- [x] `runuser` — hybrid canonical parity; repair score 5
- [x] `s390` — hybrid canonical parity; repair score 3
- [x] `s390x` — hybrid canonical parity; repair score 3
- [x] `script` — hybrid canonical parity; repair score 5
- [x] `scriptlive` — hybrid canonical parity; repair score 3
- [x] `scriptreplay` — hybrid canonical parity; repair score 5
- [x] `setarch` — hybrid canonical parity; repair score 3
- [x] `setpgid` — hybrid canonical parity; repair score 3
- [x] `setpriv` — hybrid canonical parity; repair score 5
- [x] `setsid` — hybrid canonical parity; repair score 3
- [x] `setterm` — hybrid canonical parity; repair score 5
- [x] `sfdisk` — hybrid canonical parity; repair score 5
- [x] `sparc` — hybrid canonical parity; repair score 3
- [x] `sparc32` — hybrid canonical parity; repair score 3
- [x] `sparc32bash` — hybrid canonical parity; repair score 3
- [x] `sparc64` — hybrid canonical parity; repair score 3
- [x] `su` — hybrid canonical parity; repair score 5
- [x] `sulogin` — hybrid canonical parity; repair score 5
- [x] `swaplabel` — hybrid canonical parity; repair score 3
- [x] `swapoff` — hybrid canonical parity; repair score 3
- [x] `swapon` — hybrid canonical parity; repair score 5
- [x] `switch_root` — hybrid canonical parity; repair score 3
- [x] `taskset` — hybrid canonical parity; repair score 3
- [x] `tunelp` — hybrid canonical parity; repair score 3
- [x] `uclampset` — hybrid canonical parity; repair score 3
- [x] `ul` — hybrid canonical parity; repair score 5
- [x] `umount` — hybrid canonical parity; repair score 5
- [x] `uname26` — hybrid canonical parity; repair score 3
- [x] `unshare` — hybrid canonical parity; repair score 5
- [x] `utmpdump` — hybrid canonical parity; repair score 3
- [x] `uuidd` — hybrid canonical parity; repair score 5
- [x] `uuidgen` — hybrid canonical parity; repair score 3
- [x] `uuidparse` — hybrid canonical parity; repair score 3
- [x] `vigr` — hybrid canonical parity; repair score 5
- [x] `vipw` — hybrid canonical parity; repair score 3
- [x] `waitpid` — hybrid canonical parity; repair score 3
- [x] `wall` — hybrid canonical parity; repair score 5
- [x] `wdctl` — hybrid canonical parity; repair score 5
- [x] `whereis` — hybrid canonical parity; repair score 5
- [x] `wipefs` — hybrid canonical parity; repair score 5
- [x] `write` — hybrid canonical parity; repair score 5
- [x] `x86_64` — hybrid canonical parity; repair score 3
- [x] `zramctl` — hybrid canonical parity; repair score 5

**Total: 263 applet names.**

<!-- END APPLET INVENTORY -->

