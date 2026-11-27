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
Valgrind paths; its 20 private namespaces rename 8,126 symbols after removing
3,966 byte-identical Rust runtime members already provided by Procps-ng.
Exact evidence is in `evidence/e2fsprogs-1.47.4-multicall.json`.  The resulting
499-name executable is 42,451,144 bytes unstripped and 24,961,792 bytes
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
Pointer removal is underway alongside static-link work. The later
`no_std` migration has its own compatibility gates.

### Post-applet hardening queue

All 499 public names have reached multicall integration. The current Linux
build still has 34 dynamic dependencies.

GNU Coreutils 9.12 also ships `libstdbuf.so` for the dynamically linked
child that `stdbuf` launches. A copy of the multicall executable by itself
could not run `stdbuf -o0`: canonical Coreutils and Rustbox both returned
125 with the helper missing. With the same 20,176-byte canonical helper
installed, all 750 cases in Coreutils batch 04 passed. A child-process
probe also observed the requested unbuffered, line-buffered and fully
buffered modes through both invocation paths. The final single-file
release still needs to supply this resource.
[Relocation and child buffering results](evidence/coreutils-stdbuf-relocation.json)

On the pre-FDB-hardening x86-64 Linux build, GNU ld packed relative relocations (DT_RELR)
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

#### Pointer removal progress

The target across all 499 public names is zero raw pointers in Rustbox-owned
production code, including the generated applet code and ABI adapters.
Count residual adapters explicitly. Track shared implementations by their
actual callers and verify the final linked executable before recording a
production reduction.

The default 499-name Linux executable uses verified private-helper cleanups
for 89 linked Rust archives. These cover the 20 E2fsprogs, 18 IPRoute2 and
26 GNU Inetutils engines and 25 other package archives. A second compiler pass
removed additional helpers in 58 of those archives. The declaration cleanup
covers 89 archives, including 20 E2fsprogs engines. Across the linked applet
sources the raw-pointer type count fell from **1,379,960 to 754,547**.
Counting byte-identical Rust files once gives **531,898** remaining occurrences.
The count of applets certified pointer-free is still zero.

The 36-archive native-string release at `daff5c9` had 878,920 lexical
occurrences. Parsing all 4,908 compiler inputs found 878,824 raw-pointer
types and 96 additional textual matches outside those parsed types. Across
2,937 distinct inputs the parser found 630,286 types. The parser reads the
source before macro expansion. These counts describe source types and give
no measure of how often a pointer is dereferenced at runtime.

| Where the parsed type occurs | 36-archive release (`daff5c9`) | 123-archive release (`51c7a90`) |
|---|---:|---:|
| Destination of a cast | 363,624 | 239,708 |
| Struct, union or enum field | 171,770 | 171,770 |
| Foreign declaration | 132,832 | 132,832 |
| Defined function signature | 111,477 | 111,477 |
| Pattern type annotation | 51,622 | 51,622 |
| Type alias | 25,826 | 25,826 |
| Generic argument outside the other contexts | 11,308 | 11,308 |
| Static or constant type declaration | 10,365 | 10,365 |
| **Total parsed types** | **878,824** | **754,908** |

In the 36-archive release, IPRoute2 accounted for 100,120 cast-destination types. In E2fsprogs the
largest category was fields at 62,033, followed by 55,074 cast-destination
types. Run `python3 -B scripts/count_pointer_contexts.py LINK` to repeat the
classification for a saved multicall link report.
[Const and mutable types by package](evidence/rustbox-pointer-contexts-native-36.json)

After the native-string build expanded to 123 archives, the same parser
found 754,908 pointer types. All 123,916 additional removals
were cast destinations. Fields, foreign declarations and defined function
signatures retained their previous counts. The lexical audit found
755,004 occurrences, including 96 outside parsed types.
[Expanded release by source context](evidence/rustbox-pointer-contexts-native-expanded.json)

The IPRoute2 `ss` pilot replaces the netlink protocol name table and removes
315 raw-pointer type occurrences from its compiler-selected Rust module.
The parent archive rebuilt byte-for-byte. Under empty, vendor, local and
malformed configurations, the candidate matched IPRoute2 7.3.0 on 21,860
forward/reverse lookups and 48 public `ss` invocations. Four Valgrind runs
passed. The release totals below count substitutions after multicall
integration. [Pilot evidence](evidence/iproute2-netlink-protocols-pilot.json)

| Production change | Raw-pointer type occurrences removed |
|---|---:|
| IPRoute2 nested FDB decoder and its buffer changes | 12 |
| Three shared E2fsprogs checksum implementations, including their remaining raw ABI adapters | 4,832 |
| Compiler-verified removal of unused private helpers across all 20 E2fsprogs engines | 181,096 |
| Compiler-verified removal of unused private helpers across all 18 IPRoute2 engines | 41,619 |
| Compiler-verified removal of unused private helpers across all 26 GNU Inetutils engines | 18,487 |
| Compiler-verified removal of unused private helpers in curl 8.23.0 | 7,833 |
| Compiler-verified removal of unused private helpers in GNU gzip 1.14 | 1,023 |
| Compiler-verified removal of unused private helpers in XZ Utils 5.8.4 | 7,075 |
| Shared E2fsprogs bitmap counter, including its raw ABI argument | 77 |
| Compiler-verified removal of unused private helpers in GNU bc, GNU Findutils, LZ4 and ncurses | 13,777 |
| Compiler-verified removal of unused private helpers in zstd command-line modules | 498 |
| Compiler-verified removal of unused private helpers across 17 further package archives (breakdown below) | 41,548 |
| Second-pass private-helper removal across 15 linked archives | 5,459 |
| Second-pass private-helper removal across 43 further engine archives | 3,256 |
| Compiler-verified removal of unused C declarations in 13 E2fsprogs engines | 16,616 |
| Compiler-verified removal of unused C declarations in IPRoute2 `ip`, `tc` and ncurses | 15,319 |
| Compiler-verified removal of unused C declarations across 12 more archives | 22,617 |
| Compiler-verified removal of unused C declarations in 61 additional archives | 22,736 |
| Fixed-array directory hashing in 13 E2fsprogs engines | 130 |
| Fixed-array Hangul decomposition in 13 E2fsprogs engines | 130 |
| Checked Unicode trie traversal in the same 13 engines | 65 |
| Immutable IPRoute2 address-protocol names across 18 engines | 5,166 |
| IPRoute2 route-scope and route-realm tables across 18 engines | 9,954 |
| IPRoute2 netlink protocol names across 18 engines | 5,670 |
| Packed curl manual and its readers | 11,413 |
| Shared glibc FILE layouts in 42 byte-identical archives | 10,260 |
| Compiler-checked C-string literals in 123 byte-identical archives | 178,288 |
| Borrowed GNU tar timestamp array | 7 |
| GNU Bison constant literal lengths | 450 |
| **Total** | **625,413** |

E2fsprogs accounts for 189,134 remaining occurrences, down from 401,012.
IPRoute2 accounts for 121,686, down from 265,323. GNU Inetutils accounts
for 55,033, down from 104,385. The curl crate accounts for 70,883, down
from 96,855. GNU gzip accounts for 1,656, down from 4,086, and XZ Utils
accounts for 9,412, down from 22,239.
The checksum replacement saved 135,168 stripped bytes. Removing unused source
preserved the entire ELF and link map byte-for-byte in those cleanup releases.
Sharing the live bitmap counter kept the stripped size at 25,081,136 bytes.
The directory-hash conversion also kept the stripped size at 25,081,136 bytes
and added 72 unstripped bytes. The Hangul and trie conversions together
added 11,264 stripped bytes. The IPRoute2 address-protocol conversion added
6,144 stripped bytes and 6,184 unstripped bytes across the multicall. The
scope and realm tables added 9,408 stripped bytes and 4,720 unstripped bytes.
The netlink tables added 5,360 stripped bytes and 12,112 unstripped bytes.
Packing the curl manual saved 151,536 stripped bytes and 618,464 unstripped bytes.
The current unstripped SHA-256 is
`a8b07738a1985cb6ff68e70cc87870fec0712eebe994e920389918136048379b`.
The stripped SHA-256 is
`e4811399269cc456b99bbd63b89ca445fdea2c29bb159bb1d8825330a1716d97`.

| Code | Where it runs | Remaining work |
|---|---|---|
| IPRoute2 nested FDB activity | Default multicall, verified against canonical `bridge` on 259 records and live kernel operations | The adapter still constructs a borrowed slice from the initialized receive buffer |
| IPRoute2 address-protocol names | Immutable lookup table in all 18 linked engine archives. The two public lookup functions are emitted in the `ip` namespace | The configuration loader uses a temporary pointer array and the public functions still take raw ABI arguments |
| IPRoute2 route scope and realm names | Shared Rust implementation across all 18 engines, including the separate `bridge` build | The loader and four public C interfaces still exchange raw pointers |
| IPRoute2 netlink protocol names | Shared table in all 18 linked engines, including the public `ss` command | Loader and public C entry points still have raw ABI arguments |
| curl built-in manual | Immutable packed bytes shared by full manual and option help | Each output or help callback still receives a C string at the ABI boundary |
| IPRoute2 generic `parse_rtattr_flags` | Disposable `bridge` build | Audit the remaining callers before wider use |
| E2fsprogs bitmap population count | Shared by the filesystem checker and resizer | Move the bitmap buffer owners to safe Rust to remove the remaining raw ABI argument |
| E2fsprogs CRC16, CRC32C and big-endian CRC32 | One linked provider for each function, shared across 13 engines | Replace the raw buffers at the caller boundary as their owners are migrated |
| E2fsprogs error names | Three checked archives replace 54 static pointer slots with bounded byte offsets for 18 names | The public C interface still returns a pointer and reuses its fallback buffer for unknown values |
| E2fsprogs directory-hash TEA and half-MD4 transforms | Fixed-array borrows in all 13 linked engines | The outer directory-hash function still accepts C ABI buffers |
| E2fsprogs Hangul decomposition and Unicode trie lookup | Default multicall across 13 engines | The legacy cursor still reads caller-provided filename bytes and writes to its own scratch buffer through raw pointers |

The default GNU gzip 1.14 archive shares glibc's `FILE` layout. One
Rust module supplies the original `#[repr(C)]` struct and its three opaque
pointees to 26 other modules. This removes 468 duplicate raw-pointer field
declarations. The 18 pointer fields in the shared layout still describe the
glibc ABI. The complete static archive and the standalone executable each
matched their respective controls byte for byte. The Linux C and Rust probes
agreed on the struct's 216-byte size, 8-byte alignment, and all 29 field
offsets and widths. All 108 GNU gzip command cases and two Memcheck runs
passed. [Gzip pilot evidence](evidence/gzip-stdio-layout-pilot.json)

The default build selects 42 byte-identical archives. The source reduction
by package is bc-1.08.2 (342), coreutils-9.12 (792), diffutils-3.12 (630), gzip-1.14 (468), inetutils-2.8 (5,382), lz4-1.11.1 (90), patch-2.8 (432), pkgconf-3.0.11 (612), util-linux-2.42.4 (972), xz-5.8.4 (306), zstd-1.5.7 (234). The ELF and link map reproduced the packed-curl
release byte for byte, and the dispatcher and all 14,022 batch cases passed
again. [Release evidence](evidence/rustbox-shared-stdio-replays.json)

Sharing the layout changed 570 compiler inputs. When counting every compiled
copy, the total fell by 10,260. When counting each distinct source file once,
the total rose from 683,429 to 683,588. Copies of 46 formerly identical files
now have different contents across crates. This introduced 378 distinct files
and retired 300. All of those changes compiled to the same executable bytes.
Run `scripts/compare_pointer_source_variants.py PARENT_LINK SELECTED_LINK`
to reproduce both counts from the compiler inputs.
[Distinct source comparison](evidence/shared-stdio-distinct-source-counts.json)

To find identical layouts within other linked crates and reproduce the gzip
comparison, run the following locally. The ranker counts one retained
provider per archive. The pilot checks the compiler input set on both builds.

```sh
link=work/analysis/rustbox-multicall-link.json
python3 -B scripts/rank_stdio_layouts.py "$link"
python3 -B scripts/build_shared_stdio_pilot.py --link "$link" --output work/analysis/gzip-stdio-test
python3 -B scripts/test_gzip_stdio_pilot.py work/analysis/gzip-stdio-test "$link"
```

On the tested netlink release, 93 archives contained duplicate `FILE`
definitions matching the full layout, its three opaque pointees and all
three field type aliases. Retaining one provider per crate gives 39,618
candidate field declarations. To qualify a group, save the ranker's JSON
and supply package names from that report. The first batch cold-built 13
GNU Coreutils and 13 util-linux archives. Eight Coreutils archives preserved
all bytes after removing 792 repeated fields. Six util-linux archives
preserved all bytes after removing 972. The other 12 produced different
archive bytes and are deferred. [Batch evidence](evidence/coreutils-util-linux-stdio-pilots.json)

```sh
python3 -B scripts/rank_stdio_layouts.py "$link" > work/analysis/stdio-ranks.json
python3 -B scripts/build_shared_stdio_batch.py "$link" work/analysis/stdio-ranks.json \
  work/analysis/stdio-batch --package coreutils-9.12 --package util-linux-2.42.4
```

To select byte-identical builds in a multicall release, enroll their pilot
directories against the actual parent link. Enrollment replays every selected
compiler source, installs the cold-built archives and records the receipts.
For a whole-crate candidate with changed archive bytes,
`scripts/recover_shared_stdio.py LINK WHOLE_PILOT NEW_RESULTS --limit 8`
tries smaller groups. Each trial cold-builds the union of the proposed group
and every previously accepted module. The results file identifies the exact
pilot directory that can be enrolled and lists the remaining modules.
In a separate 43-archive sweep, 27 cold builds reproduced their complete
static archives after sharing `FILE` layouts. Those compiler inputs contain
8,028 fewer repeated raw-pointer fields. The other 16 rebuilt archives
differed from their controls and remain outside this selection.
[Archive comparisons and per-module counts](evidence/stdio-package-archive-comparisons.json)

The default build uses the checked-in stdio manifest. The explicit build below
selects a manifest on top of the packed curl manual.
Compare the resulting link report with the saved parent to verify the ELF,
link map, archive inputs and source counts.

```sh
python3 -B scripts/prepare_shared_stdio.py enroll PARENT_LINK work/analysis/stdio-selection.json PILOT_DIR...
scripts/build_rustbox_multicall.sh --shared-stdio work/analysis/stdio-selection.json
python3 -B scripts/audit_linked_pointers.py "$link" --verify-shared-stdio-from PARENT_LINK
```

`scripts/verify_shared_stdio_release.py PARENT_LINK SAVED_ELF PARENT_REPLAYS NEW_DIRECTORY`
checks that the entire binary, link map and every archive input match the
parent, then reruns the dispatcher and batch differential tests on the saved
ELF. It records the parent package-suite results with their hashes and
regenerates the source inventory and rankings for the selected layouts.




The C-string pass recognizes the Rust expression that casts a NUL-terminated
byte literal to `*const u8` and then to `*const c_char`. It parses both
literal spellings and checks their full byte sequences, including the
terminator, before generating `c"...".as_ptr()`. It skips embedded NULs,
macro token bodies and other pointer types. The netlink release had 133,397
matching expressions across 127 archives, or 118,690 in distinct source
files. These are candidates for crates whose compiler supports C literals.
[Candidate inventory](evidence/rustbox-c-string-candidates.json)

A separate pass removes calls to libc `strlen` on byte literals with a single
trailing NUL. It counts decoded bytes, including non-UTF-8 data, and emits a
Rust `usize` constant. Both casts and the call disappear. The pass checks the
foreign declaration and skips modules with ambiguous bindings. On the
499-name packed-curl build it identified 301 calls in 25 archives, including
225 in GNU Bison. Counting identical source files once gives 283 calls.
These are candidate counts. The release inventory records accepted builds.
[Literal length candidates](evidence/rustbox-literal-length-candidates.json)

A scan of the packed-curl build found 185 distinct C struct layouts with
repeated definitions inside individual archives. Their additional copies
account for 17,237 explicit pointer fields. On x86-64 Linux the largest
group is the System V variadic argument tag. Keeping one definition per
archive would remove 6,300 repeated fields across 98 archives. The scan
checks scalar alias targets and counts each archive separately. A cold
build and ABI checks are still required before sharing a definition.
Run `python3 -B scripts/rank_leaf_c_layouts.py LINK --limit 30` to reproduce
the ranking.
[Ranked layouts and per-archive counts](evidence/rustbox-leaf-c-layout-candidates.json)

For the System V tag, the complete E2fsprogs `e4defrag` archive remained
byte-identical with 50 modules sharing one definition. Replaying all 58
compiler inputs measured 100 fewer repeated pointer fields. GNU grep shared
35 definitions (70 fields) but its archive changed, so it is excluded from
the byte-identical selection. Independent GCC and Clang probes at two
optimization levels compared 160 live variadic cursors, including copies
and arguments on the stack. The shared declaration still has two raw ABI
fields. To repeat the archive checks, run
`python3 -B scripts/build_va_list_layout_batch.py LINK OUT --package grep-3.12`.
[Variadic ABI measurements and both archive comparisons](evidence/x86-64-va-list-layout-pilots.json)

The full x86-64 System V variadic-layout sweep rebuilt all 98 eligible archives
against the 123-archive native-string release. Fifty-five rebuilt byte for byte.
Selecting those 55 in an optional build removes 2,158 duplicate raw-pointer
field declarations from the compiler inputs, bringing the source count from
755,004 to 752,846. The other 43 archives changed during compilation and
account for 4,142 further candidate declarations. The ABI still uses two
pointer fields per shared definition.

To reproduce the sweep, run `python3 -B scripts/build_va_list_layout_batch.py LINK OUT`
with the link report from `51c7a90`. To select the 55 identical results, pass
`--va-list-layouts batches/multicall-va-list-layouts.json` to
`scripts/build_rustbox_multicall.sh` with the same parent selections.
[98-archive results](evidence/x86-64-va-list-layout-batch.json) The ordinary Linux linker reproduced the complete 499-name executable and link map byte for byte with these 55 archives selected. [Linux link comparison](evidence/x86-64-va-list-layout-normal-link.json)

For an archive whose full variadic substitution changed the compiled bytes, run
`python3 -B scripts/recover_shared_stdio.py LINK WHOLE_PILOT OUT --kind va-list --limit 8`.
It tests groups of consumer modules against the original archive, retaining a
group only when it compiles byte for byte together with every previously
accepted module. The provider stays fixed. The final source replay checks the
selected modules and their hashes. `OUT/results.json` identifies the accepted
trial and lists the modules still outstanding.
To apply this search across a completed sweep, run
`python3 -B scripts/build_va_list_layout_batch.py LINK OUT --recover-from SWEEP --trials 4`.
The command processes changed archives in order of potential savings and reuses
completed trials on restart. Add `--package grep-3.12` to select one package.
Pass `--manifest PATH` to write an optional multicall selection after all the
requested archives finish and their accepted source hashes replay.

In E2fsprogs `tune2fs`, the first group shared the layout in 39 modules.
All 88 compiler inputs replayed, and the cold-built archive matched its
original SHA-256. The optional archive went from 16,459 raw-pointer type
occurrences to 16,381, a reduction of 78. [Compiler receipt](evidence/tune2fs-va-list-subset.json)

The next jointly verified groups cover 58 `tune2fs` modules (116 fields,
including those first 78) and eight GNU grep modules (16 fields). All
88 and 131 compiler inputs respectively replayed, and both archives
matched their controls byte for byte. To select those 132 reductions on
the native-string parent, pass
`--va-list-layouts batches/multicall-va-list-subsets.json`.
[Two-archive selection](batches/multicall-va-list-subsets.json)

In ncurses, 132 modules shared the variadic layout and removed another 264
duplicate pointer fields. All 266 compiler inputs replayed, and the archive
SHA-256 matched. Combining this optional selection with the 55 full-archive
results and the initial grep and tune2fs selections brought the compiler-input
count from 755,004 to 752,450 across 58 affected archives. When identical
files are counted once, the count increased from 532,355 to 593,216 because
re-exports can give formerly identical files different source bytes. Both
counts measure declarations.
[Ncurses selection](batches/ncurses-va-list-subset.json) ·
[Combined source inventory](evidence/x86-64-va-list-58-source-selection.json)

To carry these selections to a later release, run
`python3 -B scripts/rebase_va_list_layouts.py LINK OUTPUT_MANIFEST INPUT_MANIFEST...`.
It checks archive bytes, replays the selected compiler sources, and lists any
archives that need a new build. On the default tar release at `582f6ba`, all 58
selections replayed. Selecting them would bring the count from 754,997 to
752,443. [Tar release source replay](evidence/tar-default-va-list-rebase.json)

The terminal layouts were also cold-built on top of the 132-module variadic selection. Across the same 266 ncurses inputs the two changes removed 2,703 duplicate pointer fields together, with the archive still byte-identical. [Combined ncurses build](evidence/ncurses-combined-layouts.json)

The util-linux `isosize` candidate reads ISO 9660 sector counts and block sizes from borrowed eight- and four-byte arrays. It removes eight raw-pointer types and fourteen pointer offsets. The archive matched both canonical compilers on 196 generated images, including disagreements between the two byte orders, truncated inputs and mixed-success file lists. Four Memcheck runs passed. [ISO numeric reader checks](evidence/util-linux-isosize-borrowed-numbers.json)

The complete 499-name candidate matched the same ISO profiles through both dispatch modes, passed 100 further util-linux command comparisons, and measured 24,961,776 bytes stripped. [Full executable results](evidence/util-linux-isosize-borrowed-numbers-multicall.json)

The optional release selector accepts verified variadic layouts after the
C-string substitutions. Starting with only the original `e4defrag` archive
in a fresh cache, the normal preparation step rebuilt the same bytes and
compiler receipt. The inventory replay checked 4,908 source inputs across
127 archives and attributed the 100-field change to `e4defrag`. Five
negative tests rejected altered hashes, a different provider, an incomplete
module list, and a missing C-string parent. Use
`scripts/prepare_va_list_layouts.py enroll LINK MANIFEST PILOT` with Python,
then pass `--va-list-layouts MANIFEST` before the parent build options.
[Clean rebuild and source receipt](evidence/e4defrag-va-list-preparation.json)

Ncurses 6.6 has separate narrow and wide numeric terminal layouts. Sharing
each declaration inside its own crate removes 2,439 repeated raw pointer
fields in a replay of all 266 compiler inputs. GCC and Clang each confirmed
the size, alignment and 13 field offsets of both layouts. They also checked
eight numeric reads each, including a wide value of 65,537. A cold rebuild
of all 266 inputs reproduced the complete original archive byte for byte.
The source replay confirmed both providers and all 139 changed modules.
The published pointer count will change when the release selects this archive.
[Ncurses source projections and C ABI measurements](evidence/ncurses-termtype-layout-sources.json)

The optional `--ncurses-termtypes MANIFEST` build selection can follow
other source changes. A combined source replay with the verified
`e4defrag` variadic layout removed 2,539 repeated fields across the two
packages. Every other measured pointer metric matched the parent. The
normal preparation step repeated the ncurses cold build from an empty
selection cache and reproduced the archive and its compiler receipt. The
ncurses verifier also rejected swapped narrow and wide layout hashes,
a wrong provider, missing modules, and changed archive and source hashes.
[Combined inventory and manifest digests](evidence/ncurses-e4defrag-layouts-combined.json)

The GNU Bison 3.8.2 pilot replaced 225 calls to `strlen` and 450 raw
pointer casts in eight modules. Rebuilding all 150 selected sources
produced a different archive. The resulting `bison` and `yacc` passed
13 comparisons against each of the GCC and Clang upstream builds,
including five generated parsers and a yacc parser compiled and exercised
for each oracle. Both frontends generated a parser under Memcheck with
zero reported errors. This result applies to the isolated Bison executable.
[Bison pilot and generated-file digests](evidence/bison-literal-length-pilot.json)

The default 499-name executable selects the checked Bison constant lengths.
[Complete release checks](evidence/rustbox-bison-length-replays.json)

Bison includes its invocation name in help and diagnostics. The comparison
passes `./bison` for the symlink invocation and `bison` for the multicall
subcommand, matching upstream's `argv[0]` in each case. It compares the
original output bytes, including the usage line.

The full 499-name Bison preview passed all 52 comparisons across both
dispatch modes and both canonical compilers, using embedded M4 and Bison
resources. Each combination compiled and ran five C/C++ parsers and a
yacc-generated parser. Rerunning the suite on the saved executable gave
the same results. An empty-cache rebuild reproduced the complete archive
and all 150 compiler-input digests. Use `--bison-literal-lengths` to select the
archive explicitly in the normal multicall build.
[Full Bison multicall comparison](evidence/bison-literal-length-multicall.json)

```sh
python3 -B tests/c-string-literals/lengths.py
python3 -B scripts/rank_c_string_literals.py --lengths "$link"
scripts/build_private_inline_tool.sh
python3 -B scripts/build_literal_lengths_pilot.py --link "$link" --archive "$archive" --output "$pilot"
python3 -B scripts/verify_c_string_sources.py --lengths "$link" "$pilot"
```

On the pinned April 2023 nightly, the same scan uses a crate-private macro
with a `const CStr::from_bytes_with_nul` result and the compiler's
`const_cstr_methods` feature. Each call validates its terminator during
compilation, including in ordinary runtime expressions. The regression
fixture covers non-UTF-8 bytes, missing terminators and embedded NULs.
Run `python3 -B tests/c-string-literals/legacy.py` to repeat it.

E2fsprogs `mklost+found` used this path for 13 literals and removed 26
explicit casts. Its complete static archive and executable each reproduced
their original bytes. Both canonical compilers agreed with the candidate on
all seven command and filesystem cases. Creation and an existing-file error
also passed Memcheck.
[E2fsprogs pilot evidence](evidence/e2fsprogs-mklost-found-c-strings.json)

In a separate GNU gzip pilot, 240 literals across 15 modules removed 480
explicit raw-pointer type occurrences and added 240 pointer extractions
at existing C interfaces. The Rust compiler now checks each string's
termination. Both the full archive and the standalone gzip executable matched
their controls byte for byte. All 108 GNU gzip command cases and both
Memcheck runs passed. [Gzip comparison](evidence/gzip-c-string-pilot.json)

Applied in sequence, the shared stdio and C-string changes remove 948
explicit raw-pointer type occurrences from gzip. The combined build
reproduced the original archive and executable. The 108 GNU gzip command
cases and two Memcheck runs also passed on that executable.
[Combined compiler and test evidence](evidence/gzip-composed-stdio-c-strings.json)

Flex 2.6.4 qualified 5,271 literals across 18 modules, including the
built-in scanner skeleton. This removes 10,542 explicit raw-pointer type
occurrences and adds 5,271 typed pointer extractions at C interfaces. Both
the complete archive and the standalone Flex executable reproduced their
original bytes. Fourteen canonical comparisons passed, including ten
generated scanner builds and executions. All three frontend comparisons
and four Memcheck runs passed. [Flex comparison](evidence/flex-c-string-pilot.json)

```sh
python3 -B tests/c-string-literals/check.py
scripts/build_private_inline_tool.sh
python3 -B scripts/rank_c_string_literals.py "$link"
python3 -B scripts/build_c_string_literal_pilot.py --link "$link" --archive GZIP_ARCHIVE --output NEW_DIRECTORY
python3 -B scripts/test_gzip_stdio_pilot.py NEW_DIRECTORY "$link"
```

For a group of packages, save the JSON from `rank_c_string_literals.py`
and run `scripts/build_c_string_batch.py LINK RANKS NEW_DIRECTORY --package PACKAGE`.
The batch compares the complete archive for each package and records changed
builds separately. To replay an individual pilot's complete source receipt,
run `scripts/verify_c_string_sources.py LINK PILOT_DIRECTORY`.

The first five-package batch reproduced the complete ACL, Flex and gzip
archives after 5,741 literal conversions, removing 11,482 explicit casts.
The complete Bison and tar archives differed and are deferred for separate
verification. [Five-package compiler results](evidence/native-c-string-first-batch.json)

For IPRoute2 the builder starts from the selected netlink archive and
replays the earlier address, scope and realm changes before it converts
strings. In `arpd`, 397 native C strings removed 794 explicit casts while
preserving every archive byte. The independent inventory also reconstructed
the inputs from the checked-in manifests.
[IPRoute2 arpd compiler evidence](evidence/iproute2-arpd-c-string-pilot.json)

The same batch command handles engines that invoke `rustc` directly. It
replays their compiler arguments, dependency archives and source path
remapping, then checks every Rust input to each compilation. IPRoute2
`bridge` reproduced its selected archive after converting 1,309 literals
and removing 2,618 explicit casts. E2fsprogs `badblocks` rebuilt successfully
with 215 checked literals, but its archive bytes changed. It remains outside
the byte-identical selection.
[Direct compiler results](evidence/direct-rustc-c-string-pilots.json)

All 24 GNU Coreutils archives were cold-built with the previously verified
stdio changes applied wherever eligible. Twenty-one reproduced their
original bytes after 10,317 literal conversions, removing 20,634 explicit
casts. Groups 07, 08 and 20 changed archive bytes and remain deferred.
These source counts enter the production inventory only after the complete
link and public multicall checks.
[GNU Coreutils archive results](evidence/coreutils-native-c-strings.json)

All 14 util-linux 2.42.4 archive groups also completed both cold builds.
Groups 01 through 12 reproduced the original archives byte for byte after
11,128 literal conversions, removing 22,256 explicit casts. Groups 13 and
14 changed archive bytes. Across Coreutils and util-linux, 33 of 38 whole
archives qualified, accounting for 42,890 cast occurrences before release
integration. [util-linux archive results](evidence/util-linux-native-c-strings.json)

For a differing Coreutils or util-linux archive, inspect the applet entry
sections with `objdump`. The recovery script uses the changed entries to
choose modules for a second cold build and replays the source modifications.
Only an exact match of the entire archive qualifies the resulting subset.
For Coreutils group 07, retaining the original `ln` module recovered
1,412 literal conversions in 12 other modules, or 2,824 explicit casts.
[Coreutils group 07 recovery](evidence/coreutils-07-literal-recovery.json)

The same check recovered 1,799 literals in 14 Coreutils group 08 modules
with `date` excluded and 1,902 in nine util-linux group 13 modules with
`unshare` excluded. Both complete archives reproduced their original bytes.
Together the first three subset builds recovered another 10,226 casts.
[Coreutils group 08](evidence/coreutils-08-literal-recovery.json) ·
[util-linux group 13](evidence/util-linux-13-literal-recovery.json)

In util-linux group 14 the changed entry sections belonged to `cfdisk` and
`fdisk`. The remaining eight modules recovered 2,528 compiler-checked
strings and 5,056 casts in a byte-identical archive. The 33 whole archives
and four recovered subsets now cover 29,086 literal conversions and **58,172
explicit casts** across Coreutils and util-linux. Six modules remain in
this batch, including the standalone Coreutils `printf` group.
[util-linux group 14](evidence/util-linux-14-literal-recovery.json)

```sh
python3 -B scripts/recover_applet_literal_modules.py "$link" "$whole_pilot" "$subset_pilot"
python3 -B tests/c-string-literals/release.py "$link" "$subset_pilot/pilot.json"
```

All 18 IPRoute2 engines reproduced their full static archives after 26,787
literal conversions removed 53,574 explicit casts. This included the
separate direct-rustc build for `bridge`. Each replacement retains one
pointer extraction at the C interface. An independent source replay against
the packed-curl parent checked all 18 compiler-input digests and archives.
[IPRoute2 per-engine receipts](evidence/iproute2-native-c-string-archives.json)

Eight E2fsprogs archives reproduced every byte after 752 checked C-string
conversions removed 1,504 explicit casts. Source replay verified all eight
against the packed-curl parent. The remaining twelve E2fsprogs archives
and the Procps-ng and Shadow archives changed bytes and remain outside
this selection. Each converted literal still crosses the C interface
through one pointer extraction.
[Complete 22-archive comparison](evidence/e2fsprogs-procps-shadow-native-c-strings.json)

In `badblocks`, converting all 215 literals changed the archive. Splitting
them into 112 literals from shared library code and 103 from the utility
also changed each archive. Testing smaller groups recovered eight modules
with 51 literals. Those 102 explicit casts can be removed while retaining
the original archive bytes. All 60 compiler inputs were replayed against
the packed-curl build. Five subset comparisons expanded that group to 14 modules and 92 literals.
The jointly rebuilt archive reproduced the original bytes, removing a total
of 184 casts and leaving 92 C-interface pointer extractions.
`recover_e2fsprogs_literal_modules.py` can use a verified peer as its seed,
then check the complete target archive independently.
[Badblocks selections and archive hashes](evidence/e2fsprogs-badblocks-literal-subsets.json)

The same eight modules also passed in `mke2fs`. The full 1,394-literal
conversion had changed its archive. The smaller selection reproduced the
original archive and removed 102 explicit casts across its 97 compiler
inputs. The batch script tests each remaining engine against its own
archive and records matching and differing builds separately.
[Verified mke2fs subset](evidence/e2fsprogs-mke2fs-literal-subset.json)

Applying the 14-module `badblocks` selection to the 11 other differing
E2fsprogs engines reproduced the entire archive in 4 cases (`dumpe2fs`, `fuse2fs`, `mke2fs`, `tune2fs`).
Those matching builds remove 736 explicit casts across their compiler inputs.
The other 7 archives changed bytes and are recorded individually.
Each engine contributes at most one independently verified selection to
the release tally.
[Per-engine source and archive hashes](evidence/e2fsprogs-seeded-c-string-archives.json)

In a separate `mke2fs` build, selecting individual static-array literals
covered 319 strings across 11 modules, including the generated error
tables and filesystem feature names. Replaying all 97 compiler inputs
reproduced the complete archive with 638 fewer explicit casts. The
51-literal selection overlaps this one in the extended-attribute module.
[Mixed-array archive and overlap](evidence/e2fsprogs-mke2fs-mixed-array-c-strings.json)

The same static-array selection was cold-built for four E2fsprogs engines.
Counts are per archive. The best complete selection for each engine counts once.

| Engine | Literals selected | Compiler inputs | Explicit casts removed in byte-identical builds |
| --- | ---: | ---: | ---: |
| `badblocks` | 8 | 60 | 16 |
| `mke2fs` | 319 | 97 | 638 |
| `debugfs` | 509 | 125 | 1,018 |
| `e2fsck` | 884 | 115 | 1,768 |

[Complete archive hashes and selected modules](evidence/e2fsprogs-four-static-array-archives.json)

GNU Gawk 5.4.0 reproduced its complete archive after converting 5,005 C
literals in 28 modules. Independent replay checked all 39 compiler inputs,
including the 11 untouched modules. This removes 10,010 explicit casts and
retains 5,005 pointer extractions for the C interface. The verified archive
is eligible for the next C-string selection.
[Gawk archive and source digests](evidence/gawk-native-c-strings.json)

The broader C-string sweep cold-built 44 archives.
Of those, 31 reproduced every archive byte and passed a separate replay
of their compiler inputs. They cover 17,407 literals and 34,814
removable casts, including the Gawk result above. The 13 changed archives
remain eligible for smaller, separately compiled selections.
[Per-archive C-string results](evidence/remaining-utility-native-c-strings.json)

For archives that changed bytes, `recover_literal_array_modules.py` can
select modules where every eligible cast falls inside a top-level static or
constant array. It matches parsed Rust byte ranges against the existing
C-string edits. In curl, 906 literals in three modules meet this condition.
A further 680 array literals occur in modules with other casts. Passing
`--output DIRECTORY` cold-builds the selected subset and checks its full
archive and compiler sources.
[Selection counts for five packages](evidence/static-array-c-string-selection.json)

The static-array-only retry examined 13 differing archives for the Cargo-built utilities.
It reproduced 12 entire archives with 10,912 fewer explicit casts
across those builds. The comparison records 1 different archives
and 0 engines with no proper subset. Counts overlap earlier
per-engine trials and are credited once per selected archive.
[Per-engine outcomes and hashes](evidence/mixed-array-c-string-utilities.json)

The static-array-only retry examined 14 differing archives for the legacy compiler engines.
It reproduced 14 entire archives with 7,662 fewer explicit casts
across those builds. The comparison records 0 different archives
and 0 engines with no proper subset. Counts overlap earlier
per-engine trials and are credited once per selected archive.
[Per-engine outcomes and hashes](evidence/mixed-array-c-string-legacy.json)

Pass `--include-mixed` to select individual literals inside those arrays
when a module also contains casts in functions or other declarations.
`scripts/recover_static_array_batch.py LINK WHOLE_BATCH OUTPUT` applies
the same rule to each differing archive. It records source and archive
hashes and counts a reduction only after the complete archive matches.
Use the same command with `--check REPORT` and the original package filters
to recompute the outcomes from the saved archives and compiler inputs. The replay scans every
compiler input for eligible literals and rejects a whole-archive receipt
that omits an eligible module.
For Diffutils, File and Findutils the replay verified 482, 464 and 530
removed casts respectively. All three archives matched their release
parents byte for byte. These counts describe candidate builds.
[Three-archive replay](evidence/static-array-replay-three-utilities.json) ·
[Missing and altered receipt tests](tests/c-string-literals/array-batch-replay.py)

All 13 utilities archive outcomes were independently reconstructed from their compiler-selected sources and existing archive bytes. Run the read-only batch check against the saved report to repeat the comparison. [Utilities replay inputs](evidence/mixed-array-c-string-utilities.json)

All 14 legacy archive outcomes were independently reconstructed from their compiler-selected sources and existing archive bytes. Run the read-only batch check against the saved report to repeat the comparison. [Legacy replay inputs](evidence/mixed-array-c-string-legacy.json)

For a static-array candidate that still changes archive bytes,
`scripts/refine_static_array_selection.py LINK CANDIDATE OUTPUT` tests
smaller sets of modules. Each newly accepted set is rebuilt together and
checked against the original archive and compiler inputs. The Inetutils
`ifconfig` trial examined 6 combinations after the original four-module
selection changed the archive. It verified 0 removed casts.
[ifconfig refinement outcomes](evidence/ifconfig-array-refinement.json)

In E2fsprogs `badblocks`, the older Rust compiler reproduced all archive
bytes after changing eight literals in the extended-attribute module.
The source replay checked 60 inputs. These 16 removed casts are already
covered by the earlier 184-cast result.
[Mixed-module build and source digests](evidence/e2fsprogs-mixed-array-c-strings.json)

The same array-only conversion reproduced 12 complete E2fsprogs archives.
An independent scan of every compiler input verified 3,461 replaced literals
and 6,922 removed casts across the 12 engines. The counts include the
earlier individual trials. Each archive still has its own source digest.
[Per-engine counts and hashes](evidence/e2fsprogs-twelve-static-array-replay.json)

The Less message-catalog baseline checks all 331 built-in messages against
the canonical definitions. It reloads every override, checks that earlier
pointers still return their original strings, and exercises a help buffer
with an embedded NUL. Both canonical compilers and the linked Rust archive
returned identical output. The Rust archive also passed Memcheck.
[Less API baseline](evidence/less-message-catalog-baseline.json)

The candidate packs the 331 default texts and 332 symbolic names into
immutable byte tables. Overrides retain their original C allocation
addresses across reloads. After 847 native C strings were selected in the
Less archive, this separate conversion removed another 333 explicit pointer
types and 662 pointer extractions. The cold build reproduced its control,
and all 40 compiler inputs were replayed. Both canonical compilers
passed 22 command comparisons. The API checks cover invalid IDs,
unknown names and retained strings under Memcheck.
[Catalog archive and comparisons](evidence/less-checked-message-catalog.json)

The saved 499-name candidate passed 88 public comparisons for
Less and lessecho. The custom help tests exercised raw bytes, newlines,
repeated overrides and embedded NULs through both dispatch modes and
both canonical compilers. The stripped candidate is 24,938,640 bytes.
[Multicall comparison](evidence/less-checked-catalog-multicall.json)

The same 499-name executable also passed the zstd, less, curl suites with those checked archives linked together. Relative to the reproduced production parent it measured 24,934,528 bytes stripped (a signed reduction of 27,248 bytes). [Combined executable results](evidence/checked-triple-multicall.json)

The same 499-name executable also passed the zstd, less suites with those checked archives linked together. Relative to the reproduced production parent it measured 24,934,528 bytes stripped (a signed reduction of 27,248 bytes). [Combined executable results](evidence/checked-pair-multicall.json)

The compiler-source audit follows each archive through preparation and the
live rewrite. It verifies the before and after source hashes, the complete
archive digest, and the pointer counts on the actual compiled Rust. Against
the packed-manual release, the three candidate archives together account for
6,265 fewer explicit raw-pointer type occurrences.

| Archive | Release source | After byte-identical changes | After live rewrite |
|---|---:|---:|---:|
| curl | 74,055 | 70,883 | 70,853 |
| Less | 8,441 | 6,747 | 6,414 |
| Zstd | 24,547 | 23,575 | 23,511 |

The audit also counts raw borrows, pointer extractions and slices created
at raw C boundaries. Run `scripts/count_checked_parser_changes.py` with
the package, original link, prepared link and cold-build directory.
The curl candidate still uses 1,828 pointer extractions at compiled call sites,
including the 1,586 native string literals passed across C interfaces.
[Curl source inventory](evidence/curl-compiled-pointer-counts.json) ·
[Less and Zstd source inventories](evidence/zstd-less-compiled-pointer-counts.json)

The Linux errno candidate replaces integer reads and stores through
`__errno_location()` with a shared pair of Rust functions. The functions
access glibc's thread-local cell at each operation. Modules qualify only
when the syntax checker accounts for the private declaration and every
use. Address-taking and compound assignments leave a module ineligible.

| Compiler-selected sources | Eligible modules | Integer reads | Integer writes | Net pointer declarations removed |
|---|---:|---:|---:|---:|
| GNU gzip | 8 | 4 | 8 | 7 |
| GNU grep | 14 | 11 | 21 | 13 |
| GNU sed | 13 | 5 | 53 | 12 |

These are source projections. The accessor itself matched glibc for signed
integer endpoints, failed file operations and signal-handler save/restore in
four concurrent threads. GCC and Clang each exercised the canonical and Rust
accessors, then repeated the runs under Memcheck.
[Source projections and thread checks](evidence/errno-value-access-source.json)

The GNU grep candidate changed the archive bytes after replay of all 131 compiler inputs.
It replaced 11 direct errno reads and 21 stores in 14 modules.
Both canonical compilers matched all 36 public command cases,
and the linked API tests agreed across all four builds with four Memcheck runs.
[GNU grep archive and comparisons](evidence/grep-errno-archive.json)

The GNU gzip candidate changed the archive bytes after replay of all 66 compiler inputs.
It replaced 4 direct errno reads and 8 stores in 8 modules.
Both canonical compilers matched all 14 public command cases,
and the linked API tests agreed across all four builds with four Memcheck runs.
[GNU gzip archive and comparisons](evidence/gzip-errno-archive.json)

The GNU sed candidate changed the archive bytes after replay of all 87 compiler inputs.
It replaced 5 direct errno reads and 53 stores in 13 modules.
Both canonical compilers matched all 30 public command cases,
and the linked API tests agreed across all four builds with four Memcheck runs.
[GNU sed archive and comparisons](evidence/sed-errno-archive.json)

Across all 127 linked archives at the packed-manual release, the syntax scan
found 942 value reads and 860 stores in 477 eligible modules across 78
archives. One retained glibc declaration per eligible archive would remove
399 duplicate pointer declarations. The four largest groups by access count
are Shadow, Findutils, GNU tar and Gawk. Their individual compiler-source
replays matched the batch scanner, as did GNU sed, grep and gzip.
These are candidate counts. Rebuild and runtime results are recorded separately.
[Per-archive errno candidates](evidence/errno-value-access-candidates.json)

The Shadow archive applies the accessor after 107 verified native C strings.
It replaces 187 direct reads and 224 writes in 49 modules.
Both canonical compilers matched 79 public cases each.
Two error paths also matched across the canonical builds and candidate in six Memcheck runs.
[Shadow archive evidence](evidence/shadow-errno-archive.json)

The GNU Findutils archive applies the accessor after 265 verified native C strings.
It replaces 27 direct reads and 90 writes in 27 modules.
Both canonical compilers matched 38 public cases each.
Two error paths also matched across the canonical builds and candidate in six Memcheck runs.
[GNU Findutils archive evidence](evidence/findutils-errno-archive.json)

To reproduce the source selection and Linux command checks for one archive,
run the following from the repository with the saved link report and package
oracle volume. The optional `--build` cold-builds a missing candidate.
The command also verifies the archive digest when reusing an existing build.

```sh
python3 -B scripts/check_errno_archive.py sed \
  work/analysis/curl-manual-final/release.json work/analysis/sed-errno-pilot --build
```

For Shadow and Findutils, pass the saved link report for the native C string
selection used to build that archive. The Shadow baseline covers 32 programs
in 79 cases per canonical compiler, including eight account database cases.
Findutils covers 38 per compiler. Its archive tests run the canonical
`updatedb` shell with the selected `find` and `frcode` engines.
[Canonical command baselines](evidence/errno-ranked-command-baselines.json)

Shadow and Findutils also passed together in a full 499-name executable.
Each dispatch mode matched both canonical compilers for all 79 Shadow and
38 Findutils cases, for 468 comparisons. The in-binary `updatedb` produced
the same database bytes. The stripped candidate measured 24,961,776 bytes.
[Combined executable evidence](evidence/shadow-findutils-errno-multicall.json)

The source replay also composes these passes across GNU awk, grep, gzip,
sed, Findutils and Shadow. All six replayed from the shared-stdio release
through their verified native string selections. Across their compiled
sources, the errno conversion would replace 310 reads and 414 writes and
remove 124 raw-pointer declarations. Those counts include the package
results above. Reproduce the selection and pass its output link to the
archive checker for the supported package.

```sh
python3 -B scripts/prepare_errno_parents.py work/analysis/shared-stdio-final/release.json \
  work/analysis/composed-errno-parent.json grep gzip sed gawk shadow findutils
```

[Per-package compiler input hashes and counts](evidence/errno-composed-source-counts.json)

All six checked errno archives also linked into one 499-name executable.
This candidate used the native-string inputs for GNU awk, grep, gzip, sed,
Findutils and Shadow. Its command and locale results matched their independent
checks in both dispatch modes. It measured 24,961,776 bytes stripped.
[Six-archive multicall comparison](evidence/six-composed-errno-multicall.json)

Across all 713 compiler inputs for those six rebuilt archives, the packed-curl
release contained 82,241 explicit raw-pointer type occurrences. The prepared
inputs contained 70,493 after verified stdio and native-string changes.
The errno conversion brought that count to 70,369 and replaced 310 direct
reads and 414 writes through the glibc pointer. The total reduction across
all layers is 11,872. GNU awk alone fell from 28,578 to 18,550. The audit
also records pointer extractions and raw borrows for every package.
[Six compiled source inventories](evidence/six-errno-compiled-pointer-counts.json)

GNU grep, gzip and sed also passed after cold-building the errno and
native string changes in order. Each build reproduced its original archive
before conversion. All three matched the earlier public command and
Memcheck results on the newly selected compiler inputs.
[Archive comparisons](evidence/grep-gzip-sed-composed-errno-archives.json)

The complete GNU awk archive replaced 76 errno reads and 18 writes after
5,005 native string substitutions. Both canonical compilers matched 26
public command cases and 17 additional field-width, numeric conversion and
I/O profiles. The two canonical binaries, original archive and candidate
each passed three of those profiles under Memcheck.
[Archive comparisons](evidence/gawk-errno-archive.json)

The GNU awk baseline exercises `FIELDWIDTHS` at and above the 64-bit
unsigned limit, MPFR parsing in decimal and non-decimal modes, and errors
for a missing script with a non-UTF-8 filename. Seventeen profiles matched
between both canonical compilers and the original Rust archive. Each ran
the overflow, non-decimal numeric and I/O cases under Memcheck.
[GNU awk baseline](evidence/gawk-errno-baseline.json)

The byte-classification pilot checks a value-only alternative to indexing
glibc's `__ctype_b_loc()` table. On this target an optimized `isdigit` call
returned 1 for ASCII `0`, while the table returned the mask 2,048.
The Rust helper explicitly reconstructs each glibc mask after classification.
GCC and Clang each checked every byte against all 12 masks in 20 locales
(61,440 comparisons per run), including ISO-8859-1 and EUC-JP.
Every result and caller errno matched, including under Memcheck. These checks
cover the helper before it is selected in an applet.
[Classification and locale results](evidence/glibc-ctype-values.json)

The helper also matched glibc while four threads independently switched
locales. Each thread checked all 256 bytes and 12 masks over 32 rounds,
with a distinct errno sentinel in every thread and round. GCC and Clang
each passed 393,216 comparisons and repeated them under Memcheck.
[Thread-local locale results](evidence/glibc-ctype-thread-local.json)

Pkgconf's argument splitter and package-file parser contain nine calls to
the canonical unsigned-byte classifiers. The matching Rust expressions
read the glibc table directly. A replay through the shared stdio layout and
1,202 native strings preserves the C call order and removes four explicit
pointer types from those two modules. Generate the parent with
`scripts/build_pkgconf_ctype.py --prepare-parent LINK`, then run the same
script with `--link PREPARED_LINK --replay` to check all compiler inputs.
[Pkgconf compiler sources](evidence/pkgconf-ctype-parser-sources.json)

The rebuilt pkgconf archive matched both canonical compilers in
55 command comparisons each. Each full API run covered 51,200
argument splits and 5,120 package files across 20 locales. The comparison
checks raw and decoded arguments, error returns, callback keys and values,
and warnings. Eight Memcheck runs passed across the canonical builds,
original and candidate. [Pkgconf archive results](evidence/pkgconf-ctype-parser-archive.json)

All five pkgconf commands passed 220 comparisons in the complete 499-name
candidate through symlink and subcommand dispatch. Across all 14 upstream
fixture suites, the control and candidate each passed 430 cases per dispatch
mode. The upstream runner skipped four Windows sysroot cases on Linux.
The stripped candidate measured 24,961,776 bytes.
[Pkgconf multicall and fixture results](evidence/pkgconf-ctype-multicall.json)

An inventory of the shared-stdio release found 527 table-read expressions
with an explicit unsigned-byte index in 131 modules across 44 archives.
All uses matched the narrow spelling in 67 modules. The first selected
site is GNU awk's integer array-key classifier. Its exact compiled source
matches the canonical unsigned-byte `isdigit` check. After the errno pass,
the candidate replaces one table read and drops its two pointer types.
Run `scripts/rank_ctype_bytes.py LINK` for the inventory or
`scripts/build_gawk_ctype.py --link LINK --replay` for the reviewed substitution.
[Inventory](evidence/glibc-ctype-byte-candidates.json) ·
[GNU awk compiler-source replay](evidence/gawk-ctype-key-source.json)

The cold-built GNU awk archive passed the same 26 public commands and
17 errno profiles as its predecessor. For array keys, GCC, Clang, the
original and the candidate each received the same 2,140-record byte stream
in all 40 locale and byte-mode combinations. Keys included every possible initial byte,
integer bounds, spellings such as `01` and repeated insertions. Outputs matched
the previous errno-only archive. Eight additional Memcheck runs passed.
[Compiled GNU awk array-key results](evidence/gawk-ctype-key-archive.json)

The full 499-name core also passed 104 GNU awk command comparisons,
the `awk` alias checks and all 40 raw-key locale profiles through both
dispatch forms. The control reproduced the full release, and the candidate
measured 24,961,776 bytes stripped.
[Full GNU awk multicall results](evidence/gawk-ctype-multicall.json)

The predecessor and both canonical compilers also agree on array-key
identity for a corpus of 2,140 input records per invocation. It contains
every leading byte, repeated keys, signed numbers and integer bounds.
All byte-mode runs read 2,140 records. In EUC-JP and GB18030 locale
mode, all four implementations read the invalid multibyte stream as one
record and produced identical warnings and output. Eight Memcheck runs passed.
[GNU awk array-key baseline](evidence/gawk-integer-key-baseline.json)

Both dispatch modes of the original full executable also reproduced these
40 locale profiles and the `awk` alias checks. The standalone command suite
added 104 comparisons against the two canonical compilers. In subcommand
mode, Memcheck ran the multicall executable directly with `gawk` as its
first argument. [Release executable baseline](evidence/gawk-array-key-multicall-baseline.json)

GNU Inetutils' argument-help formatter contains four unsigned-byte blank
tests in each of its 26 engine archives. Five distinct compiled versions of
the formatter account for all 26 copies. Replaying the substitution on each
archive's compiler inputs would remove 104 classification-table reads and
52 explicit raw-pointer types. These are source counts. The hostname
archive is the first build under test.
[Per-engine compiler-source hashes](evidence/inetutils-argp-classification-sources.json)

The hostname archive cold-built and reproduced its compiler inputs. The
default C-locale help, usage and version matched, including four clean
Memcheck runs for default help. At a custom right margin, Memcheck reported
an error on the canonical GCC executable. The public comparison stopped
there. The direct formatter stress run also failed on canonical GCC.
All 26 formatter substitutions remain outside the release pending a reliable
comparison for that behavior. [Hostname test result](evidence/inetutils-hostname-ctype-gate.json)

GNU sed's two canonical gnulib builds and its production Rust archive
preserved the caller's errno in all 75 quoting calls, including signed
integer endpoints and buffers too small for the output. Five overflowing
`reallocarray` calls returned ENOMEM and preserved the existing allocation.
All three builds repeated these cases under Memcheck.
[GNU sed errno baseline](evidence/sed-gnulib-errno-baseline.json)

GNU grep and gzip also exercise errno when moving low file descriptors
away from standard input, duplicating a closed descriptor, creating
a pipe, and detecting allocation overflow. Each package's GCC, Clang
and production archives passed five initial errno values. Every build
repeated the checks under Memcheck. The driver checks that the tested
functions are defined in each archive.
[Descriptor and allocation baselines](evidence/gnu-descriptor-errno-baselines.json)

The checked GNU sed, grep and gzip archives linked into one 499-name executable. The saved control reproduced the release ELF exactly. Both dispatch modes passed 712 command comparisons against GCC and Clang, including grep aliases and all 14 gzip names. The candidate measured 24,961,760 bytes stripped. [Complete multicall results](evidence/gnu-errno-multicall.json)

The native C-string manifest can grow within an archive already selected.
`prepare_native_c_strings.py enroll --extend` checks that the new cold
build covers every earlier edit on the same compiler sources and produces
the same archive bytes. The inventory credits only the additional casts.
Extending the eight-literal `badblocks` selection to 92 literals credited
168 additional casts. The regression also rejects a lost module, a
changed compiler input and counting the original 16 casts twice.
[Manifest extension regression](tests/c-string-literals/extensions.py)

A clean curl build with just those three static-array modules reproduced
the complete packed-manual archive. The independent replay checked all
241 compiler inputs and counted 1,812 removed casts and 906 C-interface
pointer extractions. The next native C-string release can enroll this
subset alongside other byte-identical archives.
[Verified curl static-array subset](evidence/curl-static-array-native-c-strings.json)

Extending that curl build to array initializers inside mixed modules preserved
all 906 earlier literals and added 680. Across all 241 compiler inputs, the
1,586-literal selection reproduced the complete packed-manual archive with
3,172 fewer explicit casts. Its incremental reduction over the three-module
selection is 1,360 casts. The source audit replayed both selections and
checked the 680 additional C-interface pointer extractions.
[Verified extension and overlap](evidence/curl-static-array-c-string-extension.json)

The default build selects 89,144 native C strings across 123 archives.
Their 178,288 removed explicit casts leave 89,144 typed pointer extractions at
C interfaces. The ELF and link map reproduced the previous release. Public
dispatch and all 14,022 batch comparisons passed again.
[Linked release evidence](evidence/rustbox-native-c-strings-replays.json)

To select cold-built C-string archives in the multicall, enroll them against
the same compiler inputs as the intended parent release. When that release
shares stdio layouts, rebuild overlapping literal pilots on top of those
layouts first. Enrollment replays every changed module, checks the hashes
of all compiler inputs, and requires a byte-identical archive. The linked
inventory checks both raw casts removed and C-interface pointer extractions
added per package. To add further archives to an existing release, pass
`--extend LINKED_MANIFEST` to enrollment. An existing archive can gain sites after a
joint cold build preserves every previous edit. Submitting the same archive
twice in one enrollment fails.

```sh
python3 -B scripts/prepare_native_c_strings.py enroll "$link" "$manifest" "$pilot"
scripts/build_rustbox_multicall.sh --native-c-strings "$manifest" --shared-stdio "$stdio_manifest"
python3 -B scripts/audit_linked_pointers.py work/analysis/rustbox-multicall-link.json --verify-native-c-strings-from "$link"
```

A failed independent package suite can be rerun with
`scripts/test_inline_release.py --all-packages --package NAME` on the saved
ELF and its original link reports. Supply the initial complete result to
`verify_dirhash_release.py --independent-replay` and the successful rerun
to `--independent-retry`. Verification checks all three hashes, requires a
passing result for each failed package, and records the original exit status
alongside the retry receipt. `RUSTBOX_GREP_TEST_JOBS` controls upstream GNU
grep test concurrency when reproducing its timed signal checks.

The `pipesz --get` fixture preloads a kernel pipe before starting each
process. The earlier fixture wrote concurrently with the command, so the
canonical binary could observe zero queued bytes while Rustbox observed
nine. After the change, all 32 paired runs observed nine bytes and the
entire 53-case util-linux batch passed. Release qualification runs the
dispatcher and all differential batches on the saved executable.
[Original mismatch and corrected results](evidence/util-linux-pipesz-fixture.json)

The LZ4 benchmark dictionary pilot stores its 255 ordered words in 1,598
immutable bytes. Rust slices use checked offsets, and word lengths are
computed at compile time. The original generator still allocates the
padded work buffer that its 16-byte copies require. A compiled C reader
and the Rust dictionary matched on every word and length. The source
change removes 539 raw-pointer type occurrences on the stdio parent, or
11 additional occurrences when native C strings are already selected. The
cold-built archive matched both upstream compilers on 2,625 generator
cases, comparing all 647,605 result bytes and checking the buffer guards.
All 2,625 cases passed Memcheck. Each canonical compiler also agreed on
all 27 CLI cases across the four LZ4 command names.
[LZ4 generator and command results](evidence/lz4-benchmark-dictionary-pilot.json)

The 499-name multicall preview passed 108 command comparisons across both
canonical compilers and both dispatch modes. The synthetic benchmark
generated 10,000,000 bytes and compressed them to 4,658,239 bytes in all
four runs, with successful decompression and checksum checks. The packed
dictionary reduced this preview by 4,096 stripped bytes.
[LZ4 multicall results](evidence/lz4-benchmark-dictionary-multicall.json)

With 1,382 native C-string literals already compiled into LZ4, the dictionary
removes another 11 raw-pointer type occurrences. A fresh build reproduced the
same dictionary archive and the same stripped multicall executable as the
earlier trial. All 2,625 generator and Memcheck cases, 108 multicall command
comparisons and four 10 MB benchmark runs passed again.
[Combined source, archive and executable evidence](evidence/lz4-native-c-string-dictionary.json)

The source audit for this preview counted 261 fewer `.as_ptr()` calls and
three fewer raw borrows alongside the 11 fewer explicit raw-pointer types.
The archive manifest ties the result to four earlier compiler receipts. The
audit replays all 14 LZ4 compiler inputs and checks the canonical dictionary,
the selected archive and the complete source totals for both links.
[Dictionary manifest](batches/lz4-benchmark-dictionary.json) ·
[Selection regression](tests/lz4-dictionary/release.py)

The regular Linux build accepts `--lz4-benchmark-dictionary`. By itself this
option reconstructs the two required LZ4 source selections. With
`--iproute2-routing-protocols` it also includes the 18 routing parents. An
explicit stdio or native C-string manifest can supply the same verified
compiler inputs alongside other packages. The linker checks both archive
hashes and the exported C symbols before substituting LZ4.
The saved-executable test checks that the link selects the pinned archive,
then compares 108 commands and four benchmark runs against the canonical
results. It accepts later builds that retain the qualified LZ4 inputs.
[Saved-executable test](scripts/test_lz4_dictionary_multicall.py)

The ordinary Linux linker reproduced both the complete and stripped LZ4
preview executables byte-for-byte. The saved ordinary build passed all four
10 MB benchmark runs and 108 canonical command comparisons.
[Ordinary Linux link evidence](evidence/lz4-dictionary-normal-link.json)

Zstd 1.5.7 uses a related 255-word benchmark dictionary. Its separate Rust
generator writes into a bounded slice of potentially uninitialized output.
The candidate removes 13 mutable statics and 574 explicit pointer types
from the selected module. GCC, Clang, the parent archive and the isolated Rust
module agreed on 2,625 boundary cases, a partial paragraph and a 10 MB
block. Memcheck covered both drivers. The original oversize assertion and
zero-length null-buffer behavior were also exercised.
[Canonical generator comparison](evidence/zstd-lorem-generator.json)

A cold rebuild reproduced the selected Zstd control archive. All 46
compiler inputs were replayed, and both generator drivers passed again
against the candidate archive. Each canonical compiler passed 17 public
command comparisons. The public benchmark compressed the 64 KiB and
10 MB generated inputs to the same sizes as the Rust candidate.
[Zstd archive and public benchmark evidence](evidence/zstd-lorem-archive.json)

The Zstd repeat-offset candidate borrows the caller's three-element array in
all three sequence encoder paths. This removes seven raw-pointer type
occurrences and four unchecked offsets. Each of GCC and Clang matched the safe
Rust helper on 131,072 input combinations, including equal repeat offsets and
unsigned wraparound. Both canonical builds and both translated archives produced
the same 72 compressed frames and decoded every frame back to its input.
The candidate also passed Memcheck and all 17 command comparisons per compiler.
[Zstd repeat-offset checks](evidence/zstd-repeat-offsets-archive.json)

The complete 499-name multicall candidate passed all 68 Zstd command
comparisons across both dispatch modes and both canonical compilers. Compressed
benchmark sizes matched at 64 KiB and 10 MB. Both the parent and candidate
measured 24,961,776 bytes stripped. [Full multicall comparison](evidence/zstd-repeat-offsets-multicall.json)

The next Zstd candidate replaces twelve generated copies of the repeat-offset
updater with one safe Rust function used by the sequence encoders, optimal
parser and superblock compressor. The optimal parser copies the three-element
array by value. Together with the preceding change, the candidate removes
80 raw-pointer type occurrences and 160 unchecked offsets. Each canonical
compiler matched both helper results for 131,072 inputs. The four builds
produced identical bytes for 144 frames spanning external sequences and all
nine compression strategies, and decoded every frame back to its input. Both
Memcheck runs passed. [Zstd updater checks](evidence/zstd-repeat-updates-archive.json)

The 499-name multicall with the shared updater passed 68 command comparisons
across applet and subcommand dispatch. Both canonical compilers matched its
benchmark output sizes. The candidate measured 24,961,776
bytes stripped, compared with 24,961,776 for its control.
[Shared updater multicall](evidence/zstd-repeat-updates-multicall.json)

A separate cold build applies the writer after the verified Zstd stdio layout
and 369 selected native C strings across the archive.
Relative to that compiler input it removes 64 explicit pointer types.
All 46 compiler inputs were replayed, both generator drivers passed
Memcheck, and both canonical command suites and benchmark sizes matched.
[Composed archive and exact input receipts](evidence/zstd-lorem-composed-archive.json)

The isolated 499-name link reproduced the complete parent ELF before replacing the archive. All six Zstd command names passed 68 differential cases across both dispatch modes. The 64 KiB and 10 MB benchmarks matched the canonical compression sizes. The candidate measured 24,949,472 bytes stripped.
[Multicall results](evidence/zstd-checked-buffer-multicall.json)

The source replay also checks the Zstd generator after native C-string
conversion. With the 255 dictionary literals already converted, the writer
removes 64 more raw-pointer types and reproduces the original pilot source
byte for byte. With all 273 literals converted it removes 34 more types.
The latter source retains the checked C strings in the size assertion.
These are incremental counts from two alternative compiler inputs.
[Source hashes and counts](evidence/zstd-lorem-c-string-composition.json)

The Zstd command suite uses an initial NUL for the binary grep fixture
and separately checks the exact matching line on plain text. On the older
fixture, canonical GCC zstdgrep printed 1,024 matching lines in 14 of
16 runs and a binary-match diagnostic in two, depending on how the
decompression pipe delivered the late NUL. The revised fixture passed
the GCC and Clang command suite.
[Zstd differential test](tests/zstd-oracle-differential.py)

```sh
python3 -B tests/lz4-dictionary/source.py "$link"
python3 -B scripts/build_lz4_dictionary_pilot.py --link "$link" --archive "$lz4_archive" --output "$pilot"
```

The curl calendar pilot replaces 23 raw offsets in `checkmonth` with a
three-byte array match. Its single caller copies three bytes only after
the existing date scanner has counted three ASCII letters. The Rust helper
forbids unsafe code. Across all 16,777,216 three-byte inputs it returned the
same month number as upstream curl under GCC and Clang, each with signed
and unsigned `char`. Exactly 96 spellings matched. This check covers the
helper. The cold build reproduced the selected 241-source archive before
replacing the month reader. All 106 public `curl_getdate` cases agreed
across both canonical C builds, the Rustbox parent and the candidate.
The candidate passed the same 106 cases under Memcheck and all 12 CLI
cases against each canonical compiler.
[Exhaustive month comparison](evidence/curl-month-exhaustive.json)
[Archive, date API and command results](evidence/curl-month-array-pilot.json)

In the 499-name multicall preview, a local HTTP server captured both
`If-Modified-Since` and `If-Unmodified-Since` for every one of the 96
month spellings. All 192 requests per invocation matched independently
calculated GMT headers for GCC curl, Clang curl, the `curl` symlink and
`rustbox curl`. The isolated linker reproduced the entire packed-manual
parent before substituting the date reader. Its stripped candidate was
24,961,760 bytes, 16 bytes smaller than that parent.
[Multicall HTTP results](evidence/curl-month-array-multicall.json)

```sh
scripts/run_multicall_tool.sh python3 -B /work/tests/curl-calendar/exhaustive.py
python3 -B scripts/build_curl_month_pilot.py --link "$link" --output "$pilot"
```

Run `python3 -B scripts/rank_fixed_array_helpers.py work/analysis/rustbox-multicall-link.json`
to find private functions in generated Rust whose pointer parameters occur
only in constant-offset accesses. The scan groups identical definitions and
ranks them by total accesses across the compiler-selected sources. Each
candidate still needs a check of its callers, allocation sizes and aliasing.
The ranked candidates and compiler-selected archive paths are in
`evidence/rustbox-fixed-array-candidates.json`.

For curl's FTP mode reader, run `tests/curl-ftp-permissions/decoder.py` in
the Linux tool image to compare the nine-byte Rust helper against upstream C.
The four compiler and char-signedness combinations each passed 9,437,184
byte mutations. Running `tests/curl-ftp-permissions/wildcard.py` without
arguments checks the public libcurl baseline. GCC and Clang both delivered
all 4,096 mode values and rejected five malformed directory listings.
[Decoder comparisons](evidence/curl-ftp-permissions-decoder.json) ·
[Canonical FTP transfers](evidence/curl-ftp-wildcard-oracle.json)

GNU tar 1.35 now has a tested fixed-array pilot. Both callers copy two
timestamps into a local array. The private validator borrows that array and
uses checked indexing for all 16 former raw offsets. The compiler forbids
unsafe code in the validator. Its public callers preserve the null-input
path and report invalid nanoseconds through `errno`. This removes seven
explicit raw-pointer types. Timestamp results, errno and filesystem effects
matched canonical GCC and Clang builds in 732 cases each. All 732 cases
also passed Memcheck. The candidate tar and rmt executables passed 18 public
comparisons against each canonical build. The default 499-name executable includes the checked timestamp borrow.
[Release checks](evidence/rustbox-tar-timestamps-replays.json)
[GNU tar timestamp evidence](evidence/tar-borrowed-timespec-pilot.json)

Curl's time-zone parser has a checked Rust lookup over the original three
tables. The caller passes the ASCII word it has already counted. Making
the tables immutable and replacing the private C binary search removes
28 explicit pointer types in the parser module. GCC and Clang, each with
signed and unsigned plain char, agreed for all 7,454,980 one- to four-letter
inputs per build, including the 69 accepted spellings. These counts cover
the isolated lookup. [Time-zone comparison](evidence/curl-timezone-lookup.json)

The source replay composes the month and time-zone changes in the same
date parser and the FTP decoder in a second module. It reproduces all
241 compiler inputs after the previously qualified 1,586 native C strings.
The three readers together remove another 30 raw-pointer types. For the
public API baseline, the production and checked-month archives matched
both canonical builds on 3,010 dates. The checked-month archive repeated
all 3,010 under Memcheck.
[Compiler inputs and public baseline](evidence/curl-checked-parser-composition.json)

The cold-built combined archive passed the 3,010 time-zone dates, the month API and all 4,096 FTP file modes. The public tests ran against GCC, Clang, the original and the candidate, with another run of each API under Memcheck. The source replay includes all 241 compiler inputs.
[Combined archive results](evidence/curl-checked-parser-archive.json)

The complete 499-name parent ELF reproduced byte for byte before the combined substitution. Each dispatch mode passed 24 curl command comparisons and sent 206 canonical conditional requests. The stripped candidate is 24,961,776 bytes. [Multicall execution](evidence/curl-composed-checked-multicall.json)

The cold-built time-zone archive reproduced its control, then matched the original archive and both canonical compilers for all 3,010 public dates. Memcheck repeated those dates and the curl CLI passed 12 cases per compiler.
[Time-zone archive results](evidence/curl-timezone-archive.json)

At the HTTP boundary, both canonical curl builds and both dispatch paths
of the checked-FTP multicall emitted the expected conditional headers for
206 requests each. The cases exercise month spellings and seven named time
zones east and west of UTC.
[HTTP header baseline](evidence/curl-timezone-http-baseline.json)

To reproduce the combined compiler inputs, start with the recorded
pre-string link and select its verified curl parent.

```sh
python3 -B scripts/build_curl_checked_parsers.py --prepare-parent \
  --link work/analysis/native-strings-remaining-parent.json > work/analysis/curl-checked-parent.json
python3 -B scripts/build_curl_checked_parsers.py --replay --link work/analysis/curl-checked-parent.json
```

The curl FTP permission decoder now has a checked nine-byte candidate.
Its only caller checks the available buffer before copying the field.
This removes 24 raw offset reads in the decoder and one raw-pointer type.
The GCC and Clang references agreed with Rust on all 4,096 Unix modes
and 9,437,184 single-byte mutations per compiler and char signedness.
The archive-level test used libcurl's wildcard API over loopback FTP.
Both canonical builds, the linked parent and the candidate reported
all 4,096 permission values and rejected all five malformed listings.
The candidate repeated those transfers under Memcheck. This is an
archive pilot pending multicall integration.
[Source and test evidence](evidence/curl-ftp-permissions-pilot.json) ·
[Public API comparison](tests/curl-ftp-permissions/wildcard.py)

The isolated 499-name link reproduced the complete parent ELF before replacing the archive. The curl command passed 48 comparisons across both dispatch modes. The candidate measured 24,961,776 bytes stripped.
[Multicall results](evidence/curl-checked-buffer-multicall.json)

The isolated 499-name link reproduced the packed-curl parent executable
byte for byte before substituting the tar archive. The resulting tar and rmt
passed all 18 cases through each dispatch mode against each canonical compiler.
Memcheck passed archive creation and extraction. Both the regular file and
the symlink recovered the original nanosecond modification time. The candidate
remained 24,961,776 bytes stripped and grew by 208 bytes unstripped.
[Tar multicall comparison](evidence/tar-borrowed-timespec-multicall.json)

The normal build accepts `--tar-borrowed-timestamps` before its other
selection flags. Its source audit reconstructs all 195 tar compiler inputs
from the pinned parent and verifies the seven removed types. The release
gate repeats the canonical comparisons and Memchecks on the saved ELF.
When the preceding release has the packed-curl preview's executable hash,
the resulting executable must also reproduce the tested tar preview hash.

```sh
python3 -B scripts/tar_timespec_archive.py
python3 -B tests/tar-timestamps/release.py "$packed_curl_parent"
scripts/qualify_pointer_release.sh --tar-borrowed-timestamps "$parent_link" "$new_results"
```

```sh
python3 -B scripts/build_tar_timespec_pilot.py --link "$link" --output "$pilot"
python3 -B scripts/test_tar_timespec_pilot.py "$pilot" "$link"
```

To rank complete static C-string pointer tables, run
`python3 -B scripts/rank_shared_applet_modules.py LINK_REPORT --tables --limit 20`.
This scan groups identical declarations even when their surrounding modules
differ. It includes single-engine tables and records whether the translated
static is public. The scan identified curl's former private manual table, which contained
5,704 literal entries, one null sentinel and 11,409 raw-pointer type occurrences
in its declaration. Public tables such as Flex's scanner skeleton require a
separate check of their ABI consumers.

The curl 8.23.0 pilot packs the manual into one immutable buffer. Its
converter checks all 5,704 record boundaries and escaped bytes against
canonical `src/tool_hugehelp.c`. The complete curl archive reproduced the
selected parent and removed 11,413 raw-pointer type occurrences. The
299,017-byte manual and all 614 public test cases matched canonical GCC
and Clang builds, including option-specific help for 274 long spellings
and 59 short spellings. Closed-pipe and full-device behavior matched, and
five Memcheck runs passed. The isolated stripped curl executable fell from
2,046,200 to 1,894,656 bytes, a saving of 151,544 bytes. In the default multicall, all 614 cases passed through both
`rustbox curl` and the `curl` applet name. All 28 package suites and 14,022
batch differential cases passed. [Pilot evidence](evidence/curl-manual-pilot.json)
[Release replay](evidence/rustbox-curl-manual-replays.json)

```sh
link=work/analysis/rustbox-multicall-link.json
python3 -B scripts/build_curl_manual_pilot.py --link "$link" --output work/analysis/curl-manual-pilot
python3 -B scripts/test_curl_manual_pilot.py work/analysis/curl-manual-pilot --link "$link"
```

The default multicall selects this archive. The explicit build command is
`scripts/build_rustbox_multicall.sh --curl-manual`. To build it from the
saved netlink release, run the local package suites and publish the source
inventory together, use the command below. The results directory must be new.
The optional fourth argument supplies the previous release's address-protocol
comparisons. The verifier checks those archive hashes and test inputs again.
The full 499-name test link matched all 614 cases through both dispatch forms.
That executable was 24,961,776 bytes stripped. The release verifier can reuse
the comparisons when the ELF, archives, canonical binaries, bridge, test driver
and Docker image match the recorded hashes. A change runs the full comparison
again. Pass `--fresh-curl` to `verify_dirhash_release.py` to force a rerun.
[Multicall comparison](evidence/curl-manual-multicall-comparison.json)

```sh
scripts/qualify_pointer_release.sh --curl-manual NETLINK_LINK NEW_DIRECTORY NETLINK_REPLAYS
```


To find work that can be reused across engines, run
`python3 -B scripts/rank_shared_applet_modules.py LINK_REPORT --limit 20`.
The scanner groups compiler-selected modules by package and exact source
bytes and selects groups containing a public C-ABI function. Across 187
groups it measures 203,855 raw-pointer type occurrences in copies beyond the
first archive. IPRoute2's `rt_names.rs` contains 1,389 occurrences in each of
17 identical copies, or 22,224 beyond the first. Two remaining 256-slot name tables in
each copy contain 490 explicit null initializers. These entries contribute
to the source count even before any lookup executes. The tables load local
configuration and keep process state. A shared implementation must preserve
those behaviors and its callers' ownership rules. The 20 leading groups are
in `evidence/rustbox-shared-module-candidates.json`. The production reduction
table counts only verified changes to the linked sources.

`scripts/test_iproute2_address_protocols.sh` checks the first IPRoute2 name
table against canonical `rt_names.c` and the `ip` archive selected by the
multicall link. All 6,320 results matched under four isolated configurations.
Coverage includes all 256 protocol IDs, short output buffers, vendor and
local configuration precedence, duplicate names, raw bytes and diagnostics
for a malformed configuration line.

The IPRoute2 address-protocol conversion stores 256 immutable optional
C-string references in a table initialized on the first lookup that needs
names. The C-compatible configuration loader still fills a temporary raw
pointer array. Rustbox passes 255 as the loader's inclusive upper limit so
every accepted ID fits the 256 slots. Loaded names retain their process
lifetime, and the public C functions still accept raw arguments. Each converted module contains 287
fewer raw-pointer type occurrences. Across the 18 compiler-selected sources, raw
borrows fell by 72 and pointer-accessor calls rose by 162 at the ABI boundary.
Counting each distinct module once removes 574 raw-pointer type occurrences.
Only the `ip` namespace emits the two lookup symbols in the final executable.
Their canonical callers are in
`ip/ipaddress.c`.

The cold builds reproduced all 18 original static archives byte for byte.
Seventeen engines compile identical copies of `rt_names.rs` with Cargo.
The separate `bridge` build uses rustc directly and has a different enclosing
module. Its address-protocol definitions match the same 22,725 source bytes.
The manifests in `batches/iproute2-address-protocols.json` and
`batches/iproute2-address-protocol-copies.json` record the original and
replacement archive hashes and the compiler-selected source hashes.

To reproduce the standalone `ip` experiment, use a fresh output directory.
The candidate passed 6,320 canonical lookup comparisons, 17 public command
comparisons and five Memcheck runs. Its stripped executable grew by 1,168
bytes, from 1,287,904 to 1,289,072. The results are in
`evidence/iproute2-address-protocol-pilot.json`.

```sh
python3 -B scripts/build_iproute2_address_protocol_pilot.py --output work/analysis/ip-address-pilot
scripts/test_iproute2_address_protocols.sh --archive work/analysis/ip-address-pilot
```

The following commands rebuild the other 17 archives, compare them with
canonical IPRoute2, and publish the verified artifacts into the local build
cache. Each of the 17 candidates matched all 6,320 canonical lookup results.
Their 85 Memcheck runs covered the four configuration profiles and a separate
cache-lifetime check per candidate. Use a fresh batch directory for a cold
rebuild.

```sh
link=work/analysis/rustbox-multicall-link.json
batch=work/analysis/ip-address-copies
python3 -B scripts/build_iproute2_address_protocol_batch.py "$link" "$batch" --jobs 3
scripts/test_iproute2_address_protocols.sh --batch "$batch"
python3 -B scripts/build_iproute2_address_protocol_batch.py "$link" "$batch" --cache
```

To reproduce the address-protocol checkpoint, select its 18 archives and
save the original link report from before that conversion. The package suites operate on a saved copy of the resulting
Linux executable.

```sh
scripts/build_rustbox_multicall.sh --iproute2-address-protocol-copies
scripts/test_iproute2_address_protocols.sh --multicall
scripts/test_iproute2_address_protocols.sh --linked-copies
python3 -B scripts/verify_dirhash_release.py ORIGINAL_LINK SAVED_LINUX_ELF NEW_RESULTS_DIRECTORY --jobs 4
```

The `--multicall` check compares both `rustbox ip` and applet-name invocation
with canonical `ip`. The `--linked-copies` check exercises the other 17 archives
selected by the linker. The release verifier runs both. It can reuse the last
JSON line from a completed `--batch` run with `--copy-replay FILE` after checking
the exact parent and candidate archives, canonical sources, test inputs and
Docker image against the current build.

The address-protocol release matched 113,760 lookup results across
the 18 candidate archives. The 90 Memcheck runs reported zero errors.
All 17 public `ip` commands matched the canonical exit status, stdout and
stderr in each of the two dispatch modes. The combined executable passed
all 884 dispatcher checks and all 14,022 Coreutils and util-linux comparisons.
The 28 package suites and ten integration check results are recorded in
`evidence/rustbox-address-protocol-replays.json`.

IPRoute2 shares the route-scope and route-realm table
implementation. A built-in lookup can return before configuration loads. A
later missing ID loads the configuration and can replace a built-in name.
The reverse lookup retains its last matched name across numeric parses.
For example, in a fresh default configuration, looking up `global`, then
`256`, then `global` returns success with ID 0, a parse failure, and success
with ID 256. The Rust cache preserves that observable sequence. Both tables
store immutable C-string references after loading. The loader still fills a
temporary pointer array, and the four public functions retain their C ABI.
Across the 18 engine sources the substitution removes 108 explicit raw
borrows and adds 180 pointer-accessor calls at the C interfaces.

The standalone `ip` archive reproduces the linked parent byte for byte and
removes 553 raw-pointer type occurrences from its compiler-selected source.
It matched 42,048 canonical lookup results, including errno, and 96 public
commands. Four Memcheck runs passed. See
`evidence/iproute2-route-names-pilot.json`. To repeat the experiment with a
fresh output directory, run the following on the local build host.

```sh
python3 -B scripts/build_iproute2_address_protocol_pilot.py --route-names --output work/analysis/route-name-pilot
python3 -B scripts/test_iproute2_route_names.py work/analysis/route-name-pilot
```

For the netlink protocol pilot, build the `ss` engine and run the lookup
driver and public command tests against canonical IPRoute2. The socket
fixture uses the upstream `PROC_NET_NETLINK` override. It makes symbolic
and numeric output reproducible across binaries. The tests cover first-call
overrides of built-in names, duplicate names, non-UTF-8 bytes, short output
buffers, cached reverse lookups and malformed configuration diagnostics.

```sh
python3 -B scripts/build_iproute2_address_protocol_pilot.py --netlink-protocols --engine ss --output work/analysis/ss-netlink-protocols
python3 -B scripts/test_iproute2_netlink_protocols.py work/analysis/ss-netlink-protocols
```

All 18 netlink candidates reproduced their parent archives. Together they
matched 393,480 canonical lookup results and passed 72 Memcheck runs. The
compiler receipts are in [the batch manifest](batches/iproute2-netlink-protocols.json).

The default build links all 18 netlink archives. All 28 package suites and
14,022 batch differential cases passed. Both public dispatch forms matched
canonical `ss` on all 48 socket-fixture commands. The table lookup count
covers all 18 archives. [Release replay](evidence/rustbox-netlink-protocol-replays.json)

Use
`scripts/audit_linked_pointers.py CANDIDATE_LINK --verify-netlink-protocols-from PARENT_LINK`
to replay the compiler inputs and verify the difference.

The routing protocol table `rt_protos` also has 18 copies. Replaying the
source substitution on the packed-curl compiler inputs replaced 319 raw
pointer type occurrences per copy, or 5,742 in total. With the separate
native C-string pass already applied to `ip`, its measured reduction was
267. The totals overlap. The `ip` pilot reproduced its parent archive
before compiling the changed routing table. The default still uses the
previous table until multicall qualification.
[Per-engine source hashes](evidence/iproute2-routing-protocol-candidates.json)

The `ip` candidate matched canonical GCC and Clang builds on all 21,860
forward and reverse lookups and 40 read-only route commands. The four
profiles covered empty, vendor, local and malformed configuration, including
overrides in `rt_protos.d` and non-UTF-8 names. Memcheck reported zero
errors in each profile.
[Routing protocol results](evidence/iproute2-routing-protocol-pilot.json)

Replaying the routing-table change after all 18 byte-identical C-string
archives gives 267 additional type occurrences per engine, or 4,806 in
total. This source estimate records both complete compiler input digests
for each engine. The batch command rebuilds each archive, checks those
digests, and runs the same four canonical configuration profiles. It
reuses completed comparisons after checking the archive and source hashes.
[Composed source inventory](evidence/iproute2-routing-protocol-after-c-strings.json)

All 18 selected IPRoute2 engines completed cold builds and canonical lookup
comparisons on top of their checked C strings. They removed 4,806 further
explicit pointer types. Under four configuration profiles, 393,480 lookup
results matched the GCC and Clang controls. The candidates passed 72
Memcheck runs. The `ip` engine also matched the canonical process on 40
read-only route commands.
[Per-engine build and command results](evidence/iproute2-routing-protocol-archives.json)

Relinking all 18 routing protocol engines together produced a complete
499-name multicall preview. Its 21 IPRoute2 entry points passed 72 command
cases per compiler and dispatch mode, for 288 comparisons in total. The
cases include six real-kernel `routel` queries and six named or numerical
protocol filters. The stripped preview measured 24,979,328
bytes against 24,961,776 for the reproduced parent.
[Complete multicall comparison](evidence/iproute2-routing-protocol-multicall.json)

On that same 18-engine preview, all 884 dispatcher checks and 14,022
differential cases passed. The records for all 38 batches bind the individual
reports to the saved executable's SHA-256.
[Dispatcher and differential results](evidence/iproute2-routing-protocol-public-batches.json)

`stage_routing_protocol_archives.py` reconstructs the compiler inputs for all 18 engines
from the pinned netlink and C-string records and stages each resulting
archive under its SHA-256. Replaying the selected sources measured 4,806
fewer explicit raw pointer types, 72 fewer raw borrows and 414 fewer
pointer extractions. A separate rebuild of the directly compiled bridge
reproduced its archive from all 24 sources, and the stage rejected an
altered cached copy.
[Staged archive digests and measured source changes](evidence/iproute2-routing-protocol-stage.json)

The release checks resolve each engine’s original name to the exact parent
and replacement archives. They verify the preceding C-string sources and
both archive hashes. To repeat the public commands on a saved executable,
run `python3 scripts/test_routing_protocol_multicall.py ELF
evidence/iproute2-routing-protocol-multicall.json --link RELEASE.json`.
The test also verifies the hash of the executable and the coverage from
both canonical compiler builds.
[Archive selection regression](tests/iproute2-netlink-protocols/routing-release.py)

The regular Linux linker also rebuilt the 499-name candidate in an isolated
build directory. Its stripped and unstripped SHA-256 digests matched the
independent relink. All 288 command comparisons passed again on the saved
executable. Run `scripts/build_rustbox_multicall.sh --iproute2-routing-protocols
--curl-manual` for the routing and packed-curl combination.
[Normal build, inventory and command results](evidence/iproute2-routing-protocol-normal-link.json)

The IPRoute2 `ip` pilot replaces the 256-slot mutable DS field name table
with checked indices and optional borrowed C strings. It preserves lazy
configuration loading, the cached name across numeric conversions, and the
different numeric rules for DS fields and DSCP. All five C interfaces agreed
with GCC and Clang on 21,776 lookup observations across four configuration
profiles. The candidate passed four Memcheck runs and all 36 public route
filters. The compiled `ip` archive removes 265 explicit raw-pointer types.
Source replay found the same opportunity in 18 engines, totaling 4,770
candidate occurrences. Only the `ip` build is counted in this pilot.
[Canonical observations](evidence/iproute2-dsfield-pilot.json) ·
[Per-engine source estimates](evidence/iproute2-dsfield-source-candidates.json)

A 499-name multicall containing the rebuilt `ip` engine matched both canonical compilers on
288 IPRoute2 command comparisons and 144 DS field filter comparisons in four
configuration profiles. Its stripped size was 24,981,488 bytes.
[Full executable comparison](evidence/iproute2-dsfield-ip-multicall.json)

A source replay replaced the IPRoute2 terminal color palettes in all 18 engine
archives. Each palette now stores seven bounded eight-byte rows for each
background brightness. The printer takes a row address at the `fprintf`
boundary. Across the 18 compiler selections this removes 288 static pointer
slots, 54 mutable tables and 18 explicit raw-pointer types after the earlier
C-string conversion. Run `scripts/build_iproute2_colors.py --link LINK
--all-replay` against the checked routing-protocol parent to reproduce the
source results. [Color palette source hashes](evidence/iproute2-color-palette-sources.json)

The original `ip` archive and the GCC and Clang builds of canonical
`lib/color.c` matched all 336 attribute cases per build. These cover seven
attributes, twelve background settings and four color/JSON modes. The probe
compares the formatted bytes, the reported length and the null-format return.
Eight public loopback queries matched, including forced color on dark and
light backgrounds. All three baseline Memcheck runs passed.
[Canonical palette and public-output baselines](evidence/iproute2-color-palette-baseline.json)

All 18 rebuilt IPRoute2 archives matched canonical GCC and Clang on 336 attribute and formatting cases per engine. The `ip` command also matched eight loopback output profiles. The probes passed 72 Memcheck runs across both compilers, the parent archives and the replacements. The checked sources remove 288 static pointer slots. [Archive comparisons](evidence/iproute2-color-palette-archives.json)

Both dispatch modes of the complete executable matched canonical IPRoute2 on 288 command comparisons and 32 color-output comparisons with 18 engine replacements. The candidate measured 24,975,232 bytes stripped. [Complete multicall results](evidence/iproute2-color-palette-archives-multicall.json) The same executable matched all 30 pseudoterminal profiles through each dispatch mode. [Terminal results](evidence/iproute2-color-terminal-archives.json)

A Linux pseudoterminal exercised automatic color with an actual terminal on stdout. The default executable matched both canonical compilers through both dispatch modes in all 30 combinations of background, explicit color mode and unset, empty or nonempty `NO_COLOR`. [Terminal profiles](evidence/iproute2-color-terminal-baseline.json)

The rebuilt `ip` and `bridge` archives matched canonical GCC and Clang on 336 attribute and formatting cases per engine. The `ip` command also matched eight loopback output profiles. The probes passed 8 Memcheck runs across both compilers, the parent archives and the replacements. The checked sources remove 32 static pointer slots. [Archive comparisons](evidence/iproute2-color-palette-first-archives.json) To replay the batch, run `python3 -B scripts/build_iproute2_color_batch.py LINK OUTPUT evidence/iproute2-color-palette-baseline.json --jobs 2` with the pinned routing-protocol link report.

Both dispatch modes of the complete executable matched canonical IPRoute2 on 288 command comparisons and 32 color-output comparisons with two engine replacements. The candidate measured 24,979,328 bytes stripped. [Complete multicall results](evidence/iproute2-color-palette-first-archives-multicall.json) The same executable matched all 30 pseudoterminal profiles through each dispatch mode. [Terminal results](evidence/iproute2-color-terminal-first-archives.json)

All 18 IPRoute2 engine archives then reproduced their controls and passed
the same comparisons on their rebuilt DS field readers. This covers 391,968
canonical lookup observations, 72 Memcheck runs and 36 public `ip` route
filters. Together the archives remove 4,770 raw-pointer type occurrences.
[Per-engine checks and compiled source hashes](evidence/iproute2-dsfield-archives.json)

A 499-name multicall containing all 18 rebuilt DS field engines matched both canonical compilers on
288 IPRoute2 command comparisons and 144 DS field filter comparisons in four
configuration profiles. Its stripped size was 24,983,632 bytes.
[Full executable comparison](evidence/iproute2-dsfield-all-multicall.json)

The DS field multicall driver checks the 21 IPRoute2 command names and
runs each route filter through symlink and subcommand dispatch against both
canonical compilers. The routing parent passed all 288 general comparisons
and 144 DS field comparisons. The latter use isolated empty, vendor, local
and malformed configuration files.
[Public baseline for the parent executable](evidence/iproute2-dsfield-public-baseline.json)

The optional `--iproute2-routing-protocols` build flag selects all 18
archives and verifies their C exports before linking. It accepts an
explicit C-string manifest or prepares the required IPRoute2 entries.
[Build option regression](tests/iproute2-netlink-protocols/routing-build-options.py)

With the new routing archives selected, the earlier IPRoute2 interfaces
also matched canonical C across 393,480 netlink and 756,864 scope and realm
lookups. The two suites passed 144 Memcheck runs across the 18 engines.
The address-protocol checks covered the public `ip` commands and the
other 17 archives on the same executable.
[Per-engine lookup and command results](evidence/iproute2-routing-protocol-abi-regressions.json)

With the `ip` engine switched to the new routing protocol reader, all 21
IPRoute2 names passed 288 canonical comparisons in the complete multicall.
The suite covers six live `routel` queries and six route-protocol filters,
both dispatch modes, and the GCC and Clang builds. A second run on the
saved ELF passed with only Rustbox applets on the candidate's `PATH`.
The isolated change removes 267 pointer types in `ip`. Its stripped ELF
grew by 2,176 bytes, from 24,961,776 to 24,963,952.
[Full link and IPRoute2 command results](evidence/iproute2-routing-protocol-ip-multicall.json)

To repeat these comparisons, run
`python3 -B scripts/test_routing_protocol_multicall.py ELF RECEIPT`.
The runner verifies the saved executable, copies it to a Linux volume, and
compares output and status against each compiler's oracle in the same
network namespace. It records fresh hashes for the observed route output.

```sh
python3 -B scripts/rank_routing_protocols.py "$link"
python3 -B scripts/build_routing_protocol_pilot.py --link "$link" --archive "$ip_archive" --output "$pilot"
python3 -B scripts/test_routing_protocol_pilot.py "$pilot" "$link"
python3 -B scripts/build_routing_protocol_batch.py "$link" "$batch" --jobs 2
```

To reproduce the netlink candidates for all 18 engines, use the scope/realm
parent link report and two output directories. The batch builds larger
crates first, reproduces each parent archive and checks each candidate
against the canonical program as soon as its build finishes.

```sh
link=work/analysis/rustbox-multicall-link.json
python3 -B scripts/build_iproute2_route_names.py "$link" work/analysis/netlink-batch \
  --netlink-protocols --compare work/analysis/netlink-comparisons --jobs 4
```

The same substitution applies to the compiler-selected scope and realm
functions in all 18 engine archives of the default multicall. Counting the
two distinct compiler-selected source files once removes 1,106 raw-pointer
type occurrences. Of the four namespaced lookup symbols, `nm --defined-only`
finds one in the final executable, `rustbox_iproute2_ip_private_rtnl_rtscope_n2a`.
The archive totals also cover code the compiler inlines or the linker discards.
The batch builder checks the exact
address-protocol parent and every selected compiler input. `bridge` uses
its recorded rustc command. The other 17 archives use their original Cargo
builds. To repeat the cold build and canonical lookup comparisons, use fresh
output directories.

```sh
link=work/analysis/rustbox-multicall-link.json
python3 -B scripts/build_iproute2_route_names.py "$link" work/analysis/route-name-batch --jobs 4
python3 -B scripts/test_iproute2_route_names.py work/analysis/route-name-batch --link "$link" --batch work/analysis/route-name-test
```

All 18 archives matched 756,864 canonical scope and realm lookup results.
The four configuration profiles covered numeric and named output, short
buffers, configuration overrides, raw name bytes, parse errors and cache
state. The 72 Memcheck runs reported zero errors. For the 96 public `ip`
commands, status, stdout and stderr matched canonical IPRoute2 in both
applet-name and `rustbox ip` dispatch. The results for this executable and
the package suites are in `evidence/rustbox-route-name-replays.json`.

For the combined release, save its address-protocol parent report before
running the default build. The release verifier checks the source deltas,
actual Linux executable, both public dispatch modes, and all package suites.

```sh
scripts/build_rustbox_multicall.sh
python3 -B scripts/verify_dirhash_release.py PARENT_LINK SAVED_LINUX_ELF NEW_RESULTS_DIRECTORY --jobs 4
```

In E2fsprogs the sole caller of the TEA and half-MD4 directory-hash transforms
owns two distinct, initialized stack arrays of four and eight words. The
transforms now borrow those arrays. Forty constant-offset dereferences become
bounds-checked array accesses in each engine. The hash arithmetic is unchanged.

Run `scripts/test_e2fsprogs_dirhash_arrays.sh` to rebuild the release
`debugfs` control from its actual source selection, compile the candidate,
and compare it to canonical E2fsprogs. The candidate passed 98,592 directory
hash comparisons, a further 14,148 under Memcheck, and 12 public `debugfs`
commands. The test covers signed and unsigned hashes, seeds, block boundaries,
raw filename bytes, unsupported versions, and optional or aliased outputs.
The candidate archive differs from the control. Their SHA-256 hashes are in
`evidence/e2fsprogs-dirhash-array-pilot.json`.

To build the fixed-array candidates for all 13 engines, run the command below
inside the local multicall Linux build environment. Each control must reproduce
its production archive after the earlier source cleanups. The candidate build
must use exactly the same compiler inputs. The per-engine receipt records both
archive hashes, the earlier cleanup receipts, the changed module hashes and a
digest of every selected Rust source. Candidate archives are stored separately
under their content hashes.

```sh
python3 -B scripts/e2fsprogs_dirhash_archives.py work/analysis/rustbox-multicall-link.json work/analysis/dirhash-archive-trial --jobs 3
```

The first directory-hash release pinned its 13 converted archives in
`batches/e2fsprogs-dirhash-arrays.json`. Subsequent builds check these parent
records and the exported C symbols.
Across the 13 compiler-selected copies this replaces 520 pointer dereferences
and removes 130 raw-pointer type occurrences and 52 raw borrows. A fresh build
of `badblocks` reproduced its entire compiler receipt and archive.

To verify a migration from the preceding release, save the previous link
report, run `scripts/build_rustbox_multicall.sh`, and copy the resulting ELF
out of the build volume. Run the following on the build host:

```sh
python3 -B scripts/verify_dirhash_release.py PREVIOUS_LINK_REPORT SAVED_ELF NEW_RESULTS_DIRECTORY --jobs 4
```

The verifier replays the compiler inputs against both inventories, runs the
package suites, and exercises the linked `debugfs` and `e2fsck` against their
canonical counterparts. To repeat the directory-hash checks alone, run
`scripts/test_e2fsprogs_dirhash_arrays.sh --multicall`. This also compiles the
two extracted functions with unsafe code forbidden and compares the complete
filesystem images and index dumps after rebuilding a 1,200-entry ext4 directory.
On this release the directory hashes matched canonical C in 98,592 direct
comparisons and another 14,148 under Memcheck. All 12 public `debugfs` cases
matched both output streams. The package and integration results for the original directory-hash
release are in `evidence/rustbox-dirhash-array-replays.json`.

The E2fsprogs Hangul conversion builds a nine-byte or twelve-byte leaf using
fixed-size Rust arrays. The cursor can point into its own scratch buffer, so
the adapter reads all three input bytes first and writes exactly the selected
leaf. The shorter decomposition preserves the remaining three bytes. Both
cursor and validation paths have twelve bytes of scratch storage.

To build this layer in the Linux build environment, pass the previous
directory-hash link report to
`scripts/e2fsprogs_dirhash_archives.py PREVIOUS_LINK NEW_DIRECTORY --jobs 4 --hangul`.
Each compiler run reproduces the preceding archive and its full source digest.
Run `scripts/test_e2fsprogs_hangul.sh NEW_DIRECTORY/manifest.json` on the host
to compare the converted `debugfs` against canonical E2fsprogs. The pilot
covers all 11,172 modern Hangul syllables, four overlapping or disjoint buffer
layouts, destination limits, invalid bytes, normalization and public directory
hashing. Its exact counts and archive hashes are in
`evidence/e2fsprogs-hangul-pilot.json`.

The error-name lookup in `debugfs`, `dumpe2fs` and `tune2fs` now has a separately qualified archive selection. Each uses a 134-byte string table and eighteen one-byte offsets. Both canonical compilers and all parent and candidate archives passed Memcheck on all 18 named values and 4,096 fallback calls per build, including returned-buffer reuse and errno. Tests also compared complete output for regular ext2 images containing known and unknown error codes. [Archive, API and image comparisons](evidence/e2fsprogs-packed-error-names-archives.json) The complete 499-name candidate passed the same 48 file-image comparisons and 168 further canonical E2fsprogs command checks. Its stripped size was 24,961,776 bytes. [Complete executable](evidence/e2fsprogs-packed-error-names-multicall.json)

The error-name baseline covers all 18 defined E2fsprogs codes and 4,096 unknown-code calls per build. Canonical GCC and Clang and all three selected Rustbox archives preserved errno and the lifetime of returned strings under Memcheck. On unmounted ext2 images, both multicall dispatch modes also matched both canonical compilers in 48 comparisons through `debugfs`, `dumpe2fs` and `tune2fs`. [API and filesystem-image baseline](evidence/e2fsprogs-error-name-baseline.json)

The Unicode trie conversion makes the 64,256-byte canonical table immutable and
uses checked table indices for each branch. Its input reader visits only the
bytes requested by the trie, including when the legacy caller passes
`SIZE_MAX`. The differential test compares the exact leaf selected by all six
canonical trie roots and the public validation and case-folding results for
every code point through U+10FFFF, including surrogate encodings. Truncated
inputs end at an inaccessible page. The standalone pilot build and test are
`scripts/check_e2fsprogs_utf8_trie.py` and `scripts/test_e2fsprogs_utf8_trie.sh`.
The measured archive and comparison counts are in
`evidence/e2fsprogs-utf8-trie-pilot.json`. To reproduce all 13 archives, run
`scripts/e2fsprogs_dirhash_archives.py HANGUL_LINK NEW_DIRECTORY --jobs 3 --trie`
inside the Linux build environment. The release preparer verifies the
compiler inputs and archive hash at each preceding stage. The final archive
records are in `batches/e2fsprogs-trie-arrays.json`. The default multicall build
uses this manifest. Each engine adds one private Rust symbol for Hangul
decomposition and one for trie lookup. Reproduce the symbol measurements
with `scripts/e2fsprogs_unicode_symbols.py MANIFEST STAGE` inside the Linux
build environment, using `hangul` or `trie` for the matching manifest.

To verify both migrations from the saved original and intermediate link
reports, run the command below on the build host. It checks both compiler
input inventories and runs the complete package suites on the final ELF.
The results are in `evidence/rustbox-unicode-replays.json`.

```sh
python3 -B scripts/verify_dirhash_release.py HANGUL_LINK FINAL_ELF NEW_RESULTS_DIRECTORY --jobs 4 --chain-from ORIGINAL_LINK
```

Reproduce the linked Rust source inventory with
`python3 -B scripts/audit_linked_pointers.py work/analysis/rustbox-multicall-link.json`.
It checks the archive hashes, reads the Rust compiler's source lists and
counts textual occurrences of `*const` and `*mut`. The current report covers
4,908 source entries from 127 applet archives and three shared objects.
It separately tracks raw borrows, pointer accessors and
raw slice constructors. It excludes native C objects, dependent libraries and
code outside the selected applet crates. See `evidence/rustbox-linked-pointers.json`
for package counts. The inventory command records both the executable hash and
the link-report hash so successive source cleanups can be distinguished when
they compile to identical machine code. For a release that only adds
unused-helper cleanup receipts, save the previous link report before the
build. Both reports can then be replayed against the verified archives.

```sh
link=work/analysis/rustbox-multicall-link.json
cp "$link" work/analysis/before-inline-cleanup.json
scripts/build_rustbox_multicall.sh
python3 -B scripts/audit_linked_pointers.py "$link" \
    --verify-cleanup-from work/analysis/before-inline-cleanup.json
```

The comparison checks the executable and link-map hashes, every linked
archive and the existing cleanup receipts. It independently counts both
source trees and requires each package’s decrease to match its newly
removed pointer types. Run
`scripts/test_iproute2_rtattr.sh --multicall` to replay the nested and live
FDB checks on that executable.

Inside `bridge -d`, the nested FDB activity decoder uses the shared walker
and stores child offsets in safe Rust. A single borrowed byte slice replaces
the generated child-pointer table. The adapter obtains the slice from the
validated parent and the initialized receive backing described below. Both
levels use the same four-byte alignment, so the nested cursor can reach at
most the aligned parent end. The detailed-output regression checks all 256
activity values, duplicate parents and children, nested type flags, an empty
parent, a full-size record and the diagnostic for a rejected child. This
verification covers the FDB extension printer.

E2fsprogs 1.47.4 supplied the same generated checksum modules in 13 engine
crates. The previous link retained 12 copies of the CRC16 table alone. The
release builder removes the per-engine definitions, verifies that the engines
retain their other C exports and links two Rust objects that own all three
checksum functions. Each algorithm reads a borrowed slice. A zero-length
call accepts null and preserves the entire seed.

Run `scripts/test_e2fsprogs_crc16.sh` after building the E2fsprogs oracle and
program translations. It runs offline and uses read-only build inputs. The
test compares the candidate with the pinned C function across 16,977,457
cases, traces a real checksum call during a read-only filesystem check, and
compares both passes of the upstream `f_uninit_checksum_bad` fixture and the
repaired image bytes.
Run `scripts/test_e2fsprogs_crc16.sh --all-engines` to rebuild all 13 checksum
consumers and compare the 28 standalone public names. All 112 command cases
passed alongside the checksum and repaired-image checks. Run
`scripts/test_e2fsprogs_crc16.sh --multicall` to check linkage, trace the
CRC16 and CRC32C paths in the final executable, and compare repaired image
bytes against canonical E2fsprogs.

The shared CRC32 module implements E2fsprogs CRC32C (little-endian) and
Ethernet CRC32 (big-endian). Each of the same 13 generated modules contains
369 raw-pointer type occurrences. In each copy, 30 occur in the checksum
functions and 339 in the preceding generated declarations and helpers. The implementation in `compat/e2fsprogs/crc32.rs`
uses eight-byte chunks and safe table indexing. Run `scripts/test_e2fsprogs_crc32.sh`
for the upstream test vectors and 565,444 comparisons against pinned C,
including all 32 input alignments, single-bit seeds and zero-length inputs.
The production source count above credits only changes present in its recorded
executable. The CRC32 ABI adapter still accepts raw input buffers.

E2fsprogs uses one shared bitmap counter in `compat/e2fsprogs/bitcount.rs`.
The algorithm counts set bits in safe eight-byte chunks and then in the
remaining bytes. Its unsigned 32-bit result wraps as in upstream C. The
x86-64 function occupies 200 machine-code bytes. The C entry point takes
one raw pointer and a byte length. The build checks the original source
hashes before removing the counter and its two internal helpers from 13
archives. It verifies that only `e2fsck` and `resize2fs` reference the shared
symbol and that the executable defines it exactly once.

Run `scripts/test_e2fsprogs_bitcount.sh --multicall` to compare the linked
Rust object with the pinned E2fsprogs C on 16,452 inputs, including guarded
page boundaries and an all-ones bitmap large enough to wrap the counter.
The same test checks a 32 MiB ext4 image with `e2fsck` and grows it to
40 MiB with `resize2fs`. It compares output, status and the complete image,
traces both callers with Callgrind, and checks both operations with Memcheck.
The report binds the results to the executable and object hashes. Omit
`--multicall` to test a rebuilt provider with standalone copies of the two
engines.

Run the following audit to group finalized files by their SHA-256 and list
every engine path in each group. The counts use the translation inventory's
textual `*const` and `*mut` metric.

```sh
python3 scripts/audit_pointer_duplicates.py \
  work/analysis/e2fsprogs-1.47.4/program-translations \
  work/analysis/iproute2-7.3.0/program-translations
```

| Baseline translation | All pointer occurrences | Counting identical files once per package | Repeated occurrences |
|---|---:|---:|---:|
| E2fsprogs | 401,012 | 102,161 | 298,851 |
| IPRoute2 | 265,323 | 142,065 | 123,258 |

Use this report to pick shared functions for review. A shared file can still
refer to private per-engine state. Verify callers, allocation ownership,
configuration and runtime use before sharing an implementation. Prefer a
small safe rewrite when the input bytes and output values give the function a
clear, independently testable contract. Review allocation lifetimes and
aliasing explicitly for APIs that return pointers into caller-owned buffers.

The compiler-assisted cleanup pilot starts with the original E2fsprogs
`badblocks` crate. The pinned compiler reports unused functions, then a
Rust syntax parser selects private `#[inline]` functions in leaf modules
whose names occur only at their declarations. Removing 12,122 functions
from 56 files reduces the pilot source count from 22,235 to 11,302. The
release archive, standalone executable and stripped executable were each
byte-identical before and after removal. The canonical command comparisons
also cover read-only disk scans. These removals shrink the source requiring
review. They contribute zero bytes of executable-size savings.

Run `scripts/test_e2fsprogs_private_inlines.sh` to reproduce this experiment.
It uses the Linux compiler image and the locked host build dependencies. On
a new host, populate the Cargo cache with
`cargo fetch --locked --manifest-path tools/private-inlines/Cargo.toml`.
The syntax checker is a build tool. The
production inventory above counts only the sources of the recorded link.

The default build verifies archive identity across all 20 E2fsprogs engines.
The 13 engines with shared checksums remove 178,032 raw-pointer type
occurrences from unused private helpers. The other seven remove 3,064.
Together they remove 197,857 unused private function definitions and
44,759,411 bytes of generated Rust across 963 source entries. Each before/after pair has the same archive SHA-256.

`scripts/build_private_inline_tool.sh` builds the syntax checker for the
offline Linux image. The inline checker uses its original Cargo manifest.
The other syntax tools enable the additional `syn` visitor separately. A
different inline checker can produce identical ranges while changing the
producer digest embedded in every dependent receipt. Run
`python3 -B tests/inline-proof-producer.py` to check all 13 direct E2fsprogs
parents against the rebuilt checker. A fresh, offline Linux build from an empty Cargo target reproduced the same checker executable.
[Compiler and receipt hashes](evidence/inline-producer-cold-rebuild.json)

`scripts/check_cargo_private_inlines.py --prepare-e2fsprogs`
rebuilds the seven Cargo archives at their original paths in disposable
mounts. The other 13 use the compiler flags and dependencies of their
checksum builds. Each cleanup saves its source ranges, source digests and
verified archive hash for replay. The `byte_identical_inline_cleanups` section
in `evidence/rustbox-linked-pointers.json` records removed functions, source bytes
and raw-pointer type occurrences per engine. Run `python3 -B tests/linked-pointer-audit.py`
to check that replay preserves the original comparison inputs.

The IPRoute2 release build removes 22,311 private helper definitions and
6,852,678 bytes of staged Rust from 460 source entries. Of its 41,619 removed
raw-pointer type occurrences, 10,422 came from `tc` and 9,261 from `ip`.
The release inventory records each engine’s contribution. The local link report
identifies the exact source-range record used for each archive.

To reproduce the IPRoute2 Cargo checks on a fresh host, first run
`scripts/fetch_iproute2_pointer_deps.sh` after generating the IPRoute2
program translations. This populates the local Docker registry cache from
the pinned `ss` lockfile. Run
`python3 -B scripts/check_cargo_private_inlines.py --prepare-iproute2`
to rebuild the 17 Cargo engines offline. Each comparison uses its own
source copy and target directory mounted at the original Linux paths.
The hardened `bridge` archive uses a separate rustc build.

The Cargo checker runs rustc's dead-code lint on the selected crate, keeps
its dependency builds, and cleans and rebuilds the applet itself. It verifies
that the archive disappeared after cleaning, then checks the rebuilt archive
hash and compiler input list. `fsck` and `lnstat` selected the same ranges
and post-cleanup source hashes as the earlier full-target rebuilds.
`--prepare-inetutils` applies the same archive checks to the 26 engines in
Inetutils’ shared Cargo target. The first pass retains the original newlines.
If its archive differs, the checker keeps the byte positions of all remaining
code by padding each removed range with whitespace, then recompiles and
compares the entire archive again. The release inventory replays the layout
named in each receipt. Both strict predecessor checks can supply receipts
when their original verifier, syntax tool, archive, source and configuration
digests match. Receipts from the first verifier that supported byte-offset
padding also bind the digest of the padding implementation.

For curl 8.23.0, the same checker reads the pinned dependencies from the
offline Cargo registry used by IPRoute2 and Inetutils. To run a disposable
comparison against the curl archive selected by the Linux release, use

```sh
curl_crate=work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable
python3 -B scripts/check_cargo_private_inlines.py "$curl_crate/target/release/libcurl_8_23_0_normalized_audit.a"
```

The curl archive reproduced its original SHA-256 after removing 4,317 unused
functions across 238 files, including 7,833 raw-pointer type occurrences
and 1,471,444 source bytes. The default build passes this same repository-relative
archive path to `--prepare-archive curl` before linking. Run `scripts/test_curl_multicall.sh` to compare the two public
commands with canonical curl and check the version and local file transfer
paths under Valgrind.

GNU gzip and XZ Utils use the same archive check. The gzip crate lost
520 unused helpers across 45 files and 182,406 source bytes. The XZ crate
lost 3,635 helpers across 102 files and 1,036,340 source bytes. Run
`scripts/test_gzip_multicall.sh` and `scripts/test_xz_multicall.sh` for
108 gzip and 70 XZ command comparisons, compression output checks and
Valgrind. The XZ script also runs the upstream shell tests.

The next four packages share 21 public command names. Each rebuilt archive
matched its original SHA-256 after the following reductions in staged Rust.

| Package | Source files changed | Unused functions removed | Source bytes removed | Raw-pointer types removed | Raw-pointer types remaining |
|---|---:|---:|---:|---:|---:|
| GNU bc 1.08.2 | 20 | 338 | 118,669 | 572 | 2,896 |
| GNU Findutils 4.10.0 | 142 | 2,548 | 805,830 | 4,763 | 15,708 |
| LZ4 1.11.1 | 12 | 114 | 42,608 | 273 | 6,874 |
| ncurses 6.6 | 264 | 5,215 | 1,787,899 | 8,169 | 40,262 |

The four package test scripts cover 169 canonical command comparisons, all 18
shipped GNU bc workloads and the LZ4 upstream essentials suite. They run 19
multicall paths under Valgrind, plus the standalone LZ4 decompression control.

For zstd 1.5.7, removing all 3,431 compiler-selected helpers across 42 files
changed the release archive with both newline-preserving and byte-offset-preserving
edits. Restricting the cleanup to the ten files under `src/programs` reproduced
the complete archive byte-for-byte. This removed 275 unused functions, 98,413
source bytes and 498 raw-pointer type occurrences. The linked zstd crate has
24,786 occurrences remaining. Its six command names pass 17 canonical comparisons,
and compression and decompression pass their Valgrind and byte-output checks.
The rebuilt 499-name binary also passed all 884 dispatch comparisons.

To reproduce the zstd archive check, run

```sh
zstd_crate=work/analysis/zstd-1.5.7/translations/c2rust-0.22.1/zstd-1.5.7-stable
python3 -B scripts/check_cargo_private_inlines.py --source-dir src/programs \
  --prepare-archive zstd "$zstd_crate/target/release/libzstd_1_5_7_normalized_audit.a"
```

The source directory forms part of the receipt key. The release audit checks that
each edited file lies within that directory, then verifies the complete crate's
compiler inputs and the linked archive hash.

To prioritize the remaining Cargo translations, run

```sh
python3 -B scripts/batch_cargo_private_inlines.py work/analysis/rustbox-multicall-link.json
```

The scan uses the compiler's list of source files. It ranks archives by how many
private inline function names appear only at their declaration in a file. Macro
expansion and references from other files can change that estimate. Add
`--prepare --jobs 4` to run independent single-crate builds in parallel, or add
`--package NAME` to retry a specific package. An unsuccessful verifier keeps
its log and makes the overall command exit unsuccessfully. The run directory's
`results.json` records completed, failed and pending packages after each check. Other packages finish
and retain their independently verified receipts. Packages with several archives
share one index and use their dedicated workflow.

Use `--fetch` with the link report to populate the shared dependency cache for
queued candidates. On a fresh build host, use the release selection instead.

```sh
python3 -B scripts/batch_cargo_private_inlines.py --fetch --release-args batches/multicall-inline-archives.args
```

Each fetch runs from the crate directory so Cargo respects its pinned toolchain
and lockfile. This also populates the separate registry cache used by the 2023
nightly compiler for Shadow and Procps-ng. The archive comparisons run offline.

The release preparation and the Linux linker read the same archive arguments
from `batches/multicall-inline-archives.args`. This keeps a candidate out of the
default release until its archive has been explicitly selected. The post-link
audit compares the actual executable, link map and library hashes and checks
each package's reduction against its receipts. Package test launchers use the
release's Linux image. For checks that overlap a build, set
`RUSTBOX_MULTICALL_TEST_BINARY` to the absolute path of a saved Linux executable.
The launcher verifies the file, caches it in a Linux Docker volume named for
its SHA-256, and mounts it read-only at `/rustbox-test-elf/rustbox`. Package
suites use that path even while the linker replaces its own output.
Compare that SHA-256 with the final link report before attributing the tests
to that release.

After linking, run the existing package suites selected by the difference in receipts.

```sh
python3 -B scripts/test_inline_release.py previous-link.json work/analysis/rustbox-multicall-link.json /absolute/path/to/rustbox
```

The runner checks the ELF hash before and after testing. It runs independent
suites in parallel and runs the timing-sensitive suites separately. Use
`--package NAME` to replay one changed package with the same checks.

The 17-package batch removed 20,691 unused private functions across 1,090
compiler-selected source entries, saving 7,434,700 source bytes. Each package
reproduced its entire original release archive. The linked executable and link
map also reproduced their original hashes. All 17 affected package suites and
884 unified dispatcher comparisons passed on this executable. The unified
evidence retains the previous 14,022 Coreutils and util-linux comparisons.
The GNU patch replay used the pinned GNU ed from its oracle image and
exercised the upstream `ed-style` case.

| Package | Unused functions removed | Raw-pointer type occurrences removed | Occurrences after the first pass |
|---|---:|---:|---:|
| acl-2.4.0 | 1,149 | 2,221 | 5,261 |
| attr-2.6.0 | 208 | 444 | 1,815 |
| bison-3.8.2 | 2,782 | 5,775 | 24,769 |
| diffutils-3.12 | 1,956 | 3,616 | 8,825 |
| file-5.48 | 411 | 685 | 6,935 |
| flex-2.6.4 | 374 | 606 | 13,686 |
| gawk-5.4.0 | 989 | 3,668 | 29,789 |
| grep-3.12 | 1,628 | 2,830 | 7,419 |
| kmod-34.3 | 1,038 | 1,599 | 9,672 |
| less-710 | 661 | 1,061 | 8,980 |
| m4-1.4.21 | 452 | 813 | 3,740 |
| patch-2.8 | 913 | 1,826 | 6,337 |
| pkgconf-3.0.11 | 1,057 | 2,097 | 10,646 |
| procps-ng-4.0.7 | 901 | 1,640 | 30,543 |
| sed-4.10 | 980 | 2,436 | 8,351 |
| shadow-4.20.4 | 2,615 | 5,561 | 26,311 |
| tar-1.35 | 2,577 | 4,670 | 19,837 |

The private-inline scanner can also follow calls between private helpers in a
leaf module. It keeps the dependencies of any helper referenced from outside
the group. On the default tar build (`582f6ba`), the source scan found 31,178
candidate pointer declarations across 74 archives. Of these, 1,849 occur in
helpers with more than one identifier reference in their module. Counting
identical source files once gives 16,957 candidates overall. These figures
are estimates pending rustc diagnostics and archive comparisons. Reproduce the
ranking with `python3 -B scripts/rank_closed_inlines.py LINK`.
[Per-archive candidates](evidence/rustbox-closed-inline-candidates.json)

The scalar C ABI audit found 37,532 repeated raw-pointer declarations in 113
archives on the same tar baseline. It groups private, fixed-arity C functions
with matching names, scalar argument and return types, and pointer qualifiers.
For example, the most frequent `memcpy` signature accounts for 4,173 repeated
pointer types. Sharing a declaration keeps one raw C boundary per archive.
These are source estimates across 720 signatures. They can overlap other
candidate changes. Reproduce them with
`python3 -B scripts/rank_scalar_ffi.py LINK`.
[Signature and package counts](evidence/rustbox-scalar-ffi-ranking.json)

The gzip pilot shares eight libc declarations across the selected translation
units. Its complete archive rebuilt byte for byte with 54 fewer raw-pointer
types and the independent replay reproduced the changed source hashes. To run
the eleven-interface batch, pass the scalar ranking to
`scripts/batch_closed_inlines.py LINK RANK OUT --scalar-ffi`. The ranking
identified up to 16,029 repeated pointer types for these interfaces across
111 archives. [Gzip compiler receipt](evidence/gzip-shared-scalar-ffi.json)

E2fsck also reproduced its archive after sharing 976 duplicate pointer types.
The E2fsck and gzip source selections together account for 1,030 declarations
on the verified Bison release. Its inventory goes from 754,547 to 753,517
when both archives are selected. Pass `--shared-scalar-ffi MANIFEST` to the
multicall builder to select them. [Two-archive manifest](batches/multicall-initial-scalar-ffi.json)
[Replayed release counts](evidence/rustbox-initial-scalar-ffi-rebase.json)




The first cold build removed 599 private helpers from the E2fsck Rust compiler
inputs, including 1,367 raw-pointer declarations. Twelve of those helpers
referenced one another or appeared elsewhere inside the removed group. The
control and rebuilt archive had identical SHA-256 hashes. An independent
source replay reproduced both compiler input hashes and the removal counts.
This is a candidate for the multicall release. The shipped inventory on the
tar baseline is still 754,997. The Zstd trial removed 4,965 declarations in
4,012 helpers and changed its archive bytes. Flex had no compiler-confirmed
raw-pointer declarations eligible for this pass.
[E2fsck compiler receipt](evidence/e2fsck-closed-inline-groups.json)

The first four verified archives remove 3,861 declarations on the tar baseline:
1,367 in E2fsck, 1,237 in debugfs, 1,011 in mke2fs and 246 in Shadow.
Replaying the E2fsck and mke2fs receipts together on the Bison candidate
reduced its full compiler-input count from 754,547 to 752,169. Counting
each distinct source file once gave 544,237, up from 531,898. Removing
helpers in two engines left distinct versions of previously identical files
in the other engines. [Four archive receipts](evidence/rustbox-closed-inline-checkpoint.json)
[Cross-release inventory](evidence/rustbox-closed-inline-bison-rebase.json)


The multicall linker accepts `--closed-inlines MANIFEST`. To make a manifest
from independently replayed batches, run `scripts/collect_closed_inlines.py`
with the release, ranking, output manifest, output summary and batch directories.
Add `--complete` to require a result for every ranked archive. Enrollment
reconstructs the preceding substitutions and checks the change in each
package's pointer types, raw borrows, pointer conversions and slice creation.
The linker verifies the selected archive hashes and their compiler receipts.

For an archive whose bytes changed, `scripts/recover_closed_inlines.py LINK
WHOLE_PILOT OUTPUT` tests smaller groups of modules. Each accepted group is built
together with the modules already accepted. A resumed search checks the saved
compiler sites and archive hashes before reusing a completed trial.


To reproduce one archive, use the archive path recorded in its receipt.
The batch runner checks each completed pilot again when resumed and saves
verified counts to `results.json` after each archive.

```sh
link=work/analysis/tar-timestamps-final/release.json
archive=$(python3 -c 'import json; print(json.load(open("evidence/e2fsck-closed-inline-groups.json"))["archive"])')
python3 -B scripts/build_closed_inlines.py --link "$link" --archive "$archive" --output work/analysis/e2fsck-closed-inline-pilot
python3 -B scripts/build_closed_inlines.py --link "$link" --replay work/analysis/e2fsck-closed-inline-pilot
python3 -B scripts/batch_closed_inlines.py "$link" evidence/rustbox-closed-inline-candidates.json work/analysis/e2fs-ip-closed-inlines --package e2fsprogs-1.47.4 --package iproute2-7.3.0
```

A second pass can find functions whose only remaining callers disappeared in
the first pass. To prioritize builds, rank only functions that became newly
unreferenced in their source files. The first ranking estimated 1,144 candidates
across 14 of the 25 single-crate package archives. Each selected archive still
requires fresh compiler diagnostics, an offline rebuild, matching archive
bytes and an independent replay of both edits from the original sources.

```sh
link=work/analysis/rustbox-multicall-link.json
python3 -B scripts/check_next_inline_layer.py "$link" --rank
archive=work/analysis/xz-5.8.4/translations/c2rust-0.22.1/xz-5.8.4-stable/target/release/libxz_5_8_4_normalized_audit.a
python3 -B scripts/check_next_inline_layer.py "$link" "$archive" work/analysis/xz-next-layer.json
```

To rebuild the candidates in parallel, run the batch checker against a saved
link report. It records a log and result for each archive. Each successful
cleanup with at least one removal installs the recompiled archive and a
content-addressed receipt next to it. The Linux build selects receipts from
`batches/multicall-second-inline-proofs.json` and reproduces a missing receipt
from the original sources and the first cleanup. The inventory replays both
layers in order and checks each intermediate file digest.

```sh
python3 -B scripts/batch_next_inline_layers.py "$link" --jobs 3
python3 -B scripts/check_next_inline_layer.py "$link" --rank --grouped
python3 -B scripts/batch_next_inline_layers.py "$link" --grouped --limit 2 --jobs 2
```

To enroll completed batches, pass their `results.json` files to
`scripts/prepare_second_inline_layers.py --from-link "$link" --enroll-results`.
It verifies each receipt against the original release before writing the manifest.
For an interrupted archive, repeat the batch command with `--archive PATH`
and pass both result files to enrollment. Every requested archive must have
a verified result, and overlapping successful results must agree. The
disposable Cargo builds hide the host Git index so a concurrent commit
cannot interrupt package fingerprinting.
Run the multicall build and the previous-to-current inventory comparison above
to record the production count. Package suites can also run on partial selections
while other archives compile. To combine their results, run
`python3 -B scripts/verify_inline_replays.py PREVIOUS FINAL --replay SELECTION RESULTS`
and repeat `--replay` for each group. This checks the binary hash, both link reports
and coverage of every changed archive in each package.

The second pass checked 16 archives. It removed 1,789 private helpers and
5,459 raw-pointer type occurrences across 530 compiler-selected source entries
in 15 archives. The source files shrank by 724,266 bytes. All 14 affected
package suites passed on the final ELF digest, as recorded in
`evidence/rustbox-second-inline-replays.json`. All 884 dispatcher comparisons
passed. The live IPRoute2 replay matched canonical bridge on 259 records and
the kernel monitor matched two add and two delete notifications. The executable
and link map retained their previous hashes. GNU M4 had no
eligible second-pass helper. GNU gzip had also yielded zero in its prior
experiment.

| Archive | Additional private helpers removed | Additional raw-pointer type occurrences removed |
|---|---:|---:|
| bison-3.8.2 | 157 | 231 |
| diffutils-3.12 | 10 | 10 |
| findutils-4.10.0 | 11 | 2 |
| gawk-5.4.0 | 41 | 295 |
| grep-3.12 | 37 | 8 |
| iproute2-7.3.0 (ip) | 261 | 1,044 |
| iproute2-7.3.0 (tc) | 362 | 1,448 |
| kmod-34.3 | 33 | 33 |
| m4-1.4.21 | 0 | 0 |
| patch-2.8 | 1 | 2 |
| pkgconf-3.0.11 | 117 | 199 |
| sed-4.10 | 18 | 8 |
| shadow-4.20.4 | 75 | 285 |
| tar-1.35 | 11 | 33 |
| xz-5.8.4 | 569 | 1,753 |
| zstd-1.5.7 | 86 | 108 |
| **Total** | **1,789** | **5,459** |

Counting each distinct file once rose from 744,397 to 746,529 occurrences.
Sixteen groups of formerly identical IPRoute2 files now have separate source
variants. For example, `ip` and `tc` removed additional helpers from
`src/lib/ll_addr.rs` while `arpd` retains its earlier version. The inventory
across all 4,908 linked source entries fell by 5,459.

The grouped second pass checked 43 more engines. It removed 833 private
helpers containing 3,256 raw-pointer type occurrences from 234 source entries,
saving 424,242 source bytes. The initial ranking estimated 1,482 possible
helpers. The compiler and whole-archive comparisons determined which removals
entered the release.

| Package | Engines | Private helpers removed | Raw-pointer type occurrences removed |
|---|---:|---:|---:|
| IPRoute2 | 15 | 774 | 3,089 |
| GNU Inetutils | 26 | 38 | 116 |
| E2fsprogs | 2 | 21 | 51 |

All three package suites passed on the release ELF, including 66 IPRoute2,
133 GNU Inetutils and 112 E2fsprogs comparisons. All 884 dispatcher checks
passed. The live bridge replay matched 259 nested records, two adds and two
deletes. The executable, its stripped
form and its link map reproduced their previous hashes. The package replay
record is in `evidence/rustbox-grouped-second-inline-replays.json`.

The linked E2fsprogs declaration cleanup removed 24,724 unused declarations
from 937 source entries. This eliminated 16,616 raw-pointer type occurrences
and 2,585,798 source bytes. All 13 engines reproduced their complete archives
with compact source removal. See `evidence/rustbox-e2fsprogs-declaration-replays.json`
for the E2fsprogs suite and its release hashes.

| E2fsprogs engine | Unused declarations removed | Raw-pointer type occurrences removed |
|---|---:|---:|
| badblocks | 1,533 | 1,011 |
| debugfs | 2,792 | 1,979 |
| dumpe2fs | 1,651 | 1,145 |
| e2freefrag | 1,472 | 979 |
| e2fsck | 2,997 | 1,972 |
| e2image | 1,687 | 1,111 |
| e2initrd_helper | 1,540 | 1,021 |
| e2undo | 1,533 | 1,018 |
| e4defrag | 1,470 | 970 |
| fuse2fs | 1,666 | 1,107 |
| mke2fs | 2,315 | 1,568 |
| resize2fs | 1,989 | 1,311 |
| tune2fs | 2,079 | 1,424 |
| **Total** | **24,724** | **16,616** |

The original E2fsprogs `badblocks` experiment removed 1,533 unused C
declarations across 55 files. This eliminated 1,011 raw-pointer type
occurrences and 160,356 source bytes in the trial. Both builds reproduced
the complete release archive. Four comparisons with canonical E2fsprogs
matched exit status and output and preserved the input image. The production
table includes these `badblocks` removals once, within the 13-engine total.
See `evidence/badblocks-foreign-declarations-trial.json` for the hashes.

To repeat the trial, build the selector and run it against the current link.
It matches private foreign functions and statics to compiler diagnostics by
name and byte offset. It requires a single use of the identifier in its
leaf module and skips attributed declarations and attributed extern blocks.

```sh
scripts/build_private_inline_tool.sh
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 scripts/run_tool.sh \
  python3 -B tests/foreign-declarations.py work/analysis/private-inlines-linux/release/foreign-declarations
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 scripts/run_tool.sh \
  python3 -B scripts/check_badblocks_foreign_declarations.py work/analysis/rustbox-multicall-link.json
```

To check the same transformation across the staged E2fsprogs engines, run the
following command with a new output directory. Each archive must first rebuild
from its released compiler inputs and earlier cleanup receipts. The candidate
must then reproduce the same archive hash and compiler input list.

```sh
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 scripts/run_tool.sh \
  python3 -B scripts/e2fsprogs_foreign_declarations.py \
  work/analysis/rustbox-multicall-link.json work/analysis/e2fs-declaration-results --jobs 3
```

The output directory holds a receipt selection for each successful engine.
The complete `manifest.json` can be installed as
`batches/e2fsprogs-foreign-declarations.json`. During the production link,
a missing receipt is rebuilt from its pinned parents and must reproduce its
recorded hash. The linked inventory independently replays the source changes
and checks the count of declarations, pointer types and bytes removed.

Run `python3 -B scripts/rank_foreign_declarations.py work/analysis/rustbox-multicall-link.json`
to rank the remaining engine archives. It reads the compiler-selected sources
after applying the linked receipts, counts candidate pointer types in each
archive and analyzes identical file contents once. The text scan recognizes
generated declarations whose names appear once in a leaf module. Its counts
are estimates. A removal still needs a fresh rustc diagnostic, an exact syntax
match, a clean rebuild and a matching full archive.

The ranking after the 13-engine release flags 81,652 pointer types in 46,220
possible declarations across the 127 archives. For calibration, the same scan
flagged 22,158 pointer types in the 13 E2fsprogs engines before their cleanup.
The verified removal was 16,616. After the following three Cargo archives,
the scan flagged 66,333 pointer types. Following the 12-archive batch below,
the scan flagged 43,736 pointer types in 25,533 possible declarations.
After checking the remaining ranked Cargo archives and the staged IPRoute2
bridge, the scan flags 21,022 types in 13,500 potential declarations.
Every archive with a positive estimate now has a compiler-checked selection. See
`evidence/rustbox-foreign-declaration-candidates.json` for the current paths
and link-report hash.

The next production batch removed 7,688 private declarations containing
15,319 raw-pointer types from 474 source entries. It saved 1,150,651 bytes of
generated Rust source. A fresh build reproduced all three trial receipts and
the release archives. See `evidence/rustbox-cargo-declaration-replays.json`
for the package tests.

| Cargo engine | Unused declarations removed | Raw-pointer type occurrences removed |
|---|---:|---:|
| IPRoute2 tc | 2,903 | 5,724 |
| IPRoute2 ip | 2,452 | 4,915 |
| ncurses | 2,333 | 4,680 |

The following 12 archives removed 13,017 private declarations from 1,254
compiler-selected source entries. They contained 22,617 raw-pointer types
and occupied 1,411,276 source bytes. Each compiler run reproduced its complete
release archive. All 11 affected packages met their recorded regression criteria,
and all 884 multicall dispatch comparisons passed. The live IPRoute2 bridge
replay matched 259 records and four notifications. The GNU Awk upstream suite
retains its documented QEMU persistent-memory exception.
See `evidence/rustbox-twelve-cargo-declaration-replays.json` for package coverage.

| Package or engine | Unused declarations removed | Raw-pointer type occurrences removed |
|---|---:|---:|
| acl-2.4.0 | 528 | 1,007 |
| bison-3.8.2 | 993 | 1,993 |
| curl-8.23.0 | 1,925 | 3,554 |
| diffutils-3.12 | 1,144 | 1,625 |
| findutils-4.10.0 | 1,212 | 1,786 |
| gawk-5.4.0 | 489 | 916 |
| grep-3.12 | 1,102 | 1,376 |
| iproute2-7.3.0 (dcb) | 586 | 1,154 |
| iproute2-7.3.0 (rdma) | 828 | 1,628 |
| shadow-4.20.4 | 1,217 | 2,229 |
| tar-1.35 | 1,069 | 1,722 |
| xz-5.8.4 | 1,924 | 3,627 |
| **Total** | **13,017** | **22,617** |

The next release checked 60 ranked Cargo archives and the separately staged
IPRoute2 `bridge`. Across 61 nonempty archive selections the compiler verified
12,053 unused declarations. Removing them eliminated 22,736 raw-pointer
type occurrences and 1,495,382 generated source bytes. Every resulting archive,
the final multicall ELF and the link map matched the preceding release
byte-for-byte. All 17 affected package suites and 884 dispatch checks passed.
The filesystem image checks and live IPRoute2 bridge replay also passed.
See `evidence/rustbox-remaining-declaration-replays.json` for package coverage
and `evidence/rustbox-linked-pointers.json` for individual archive counts.

| Package | Archives | Unused declarations removed | Raw-pointer type occurrences removed |
|---|---:|---:|---:|
| attr-2.6.0 | 1 | 94 | 200 |
| bc-1.08.2 | 1 | 126 | 240 |
| e2fsprogs-1.47.4 | 7 | 237 | 287 |
| file-5.48 | 1 | 169 | 294 |
| flex-2.6.4 | 1 | 153 | 294 |
| gzip-1.14 | 1 | 245 | 459 |
| inetutils-2.8 | 26 | 4,326 | 7,763 |
| iproute2-7.3.0 | 14 | 4,373 | 8,640 |
| kmod-34.3 | 1 | 218 | 376 |
| less-710 | 1 | 288 | 539 |
| lz4-1.11.1 | 1 | 59 | 137 |
| m4-1.4.21 | 1 | 132 | 288 |
| patch-2.8 | 1 | 336 | 710 |
| pkgconf-3.0.11 | 1 | 345 | 642 |
| procps-ng-4.0.7 | 1 | 372 | 700 |
| sed-4.10 | 1 | 516 | 1,036 |
| zstd-1.5.7 | 1 | 64 | 131 |
| **Total** | **61** | **12,053** | **22,736** |

IPRoute2 `bridge` has a separate rustc build. Its declaration trial uses the
production bridge compiler arguments and the same remapped source path.
Run the following inside the local multicall Linux build environment. The
resulting manifest can be pinned in
`batches/iproute2-bridge-foreign-declarations.json` after verification.

```sh
python3 -B scripts/e2fsprogs_foreign_declarations.py work/analysis/rustbox-multicall-link.json work/analysis/bridge-declaration-trial --bridge
```

For a Cargo archive, take its full path from that ranking and run a trial
against the same link. The trial restages earlier helper removals in order,
then rebuilds a control and a candidate at the original Linux compiler paths.
Use a new report filename for each run.

```sh
link=work/analysis/rustbox-multicall-link.json
archive=work/analysis/iproute2-7.3.0/program-translations/cargo-target/tc/release/libtc_audit.a
python3 -B scripts/check_cargo_foreign_declarations.py "$link" "$archive" work/analysis/tc-declarations.json --publish
python3 -B scripts/check_cargo_foreign_declarations.py "$link" --enroll work/analysis/tc-declarations.json
scripts/build_rustbox_multicall.sh
```

Enrollment accepts several report paths. It checks the archive and both
earlier receipt selections. The release build reproduces a missing receipt
from scratch and requires its exact hash before linking.

For a group of engines, generate the ranking from the release you intend to
use. The batch skips already enrolled archives and stores a compiler log and
a verified report for each engine. If interrupted, repeat the batch command
with `--resume` and the same inputs. It checks the archive and the published
receipt before reusing a successful report.

```sh
link=work/analysis/rustbox-multicall-link.json
rank=work/analysis/cargo-declaration-ranking.json
batch=work/analysis/cargo-declaration-batch
python3 -B scripts/rank_foreign_declarations.py "$link" > "$rank"
python3 -B scripts/batch_cargo_foreign_declarations.py "$link" "$rank" "$batch" --limit 12 --jobs 3 &&
  python3 -B scripts/check_cargo_foreign_declarations.py "$link" --enroll "$batch"/reports/*.json
```

After enrollment, `scripts/verify_declaration_release.py` can run the full
release check. Give it a saved copy of the current unstripped Linux executable
and a new output directory. It snapshots the old link report, runs independent
package suites against the hash-pinned ELF during the build, and waits for the
build to finish before starting timing-sensitive suites. It compares every
link-report field, independently inventories both source selections, replays
the dispatcher and refreshes the multicall summaries. If a package suite
already finished on a partial selection, pass `--replay SELECTION RESULTS`.
It can cover that package only when the ELF hash and all of its changed
archive selections match the final release.

```sh
python3 -B scripts/verify_declaration_release.py /absolute/path/to/saved/rustbox work/analysis/verified-declaration-release
```

The default build removes 9,189 unused private helper definitions and 18,487
raw-pointer type occurrences from 606 GNU Inetutils source entries. The
25 engines using compact removal account for all 3,148,896 source bytes saved.
Run `scripts/test_inetutils_multicall.sh` to replay 133 comparisons with GNU
Inetutils across the 26 public commands and check each command’s `--version`
path under Valgrind.

In Inetutils `ifconfig`, the compact form changed generated symbol names in
three object files. Preserving byte offsets removed all 467 selected helper
definitions and 933 raw-pointer type occurrences across 29 files. It reproduced
the original archive SHA-256 `7f71416e28b6c193c2c902568dbc524a518e85517094ba30f1ff16c2f899202b`.
The source files retain their original byte lengths. Run
`python3 -B tests/cargo-inline-provenance.py` to check that older receipts
require their exact inputs and source layout.

The IPRoute2 7.3.0 pilot replaces `parse_rtattr_flags` in a disposable
`bridge` build. The shared generated `libnetlink.rs` occurs in 18 engine
crates. The safe walker in `compat/iproute2/rtattr.rs` applies the type mask,
keeps the first match and advances by the aligned attribute length. Its ABI
adapter accesses the two header fields individually so callers can supply
buffers containing uninitialized payload or padding bytes.

Run `scripts/test_iproute2_rtattr.sh` after building the IPRoute2 oracle and
program translations. It compares 14,285 cases against the pinned C build
under Valgrind Memcheck, including returned pointers, table initialization,
signed residuals and exact diagnostic bytes. A saved forwarding database
(FDB) replay exercises the candidate through `bridge monitor file` under
Memcheck and Callgrind.

The pinned source has four paths into the top-level FDB attribute walker.
On a nonzero residual its diagnostic reads a two-byte length field. The
length advertised in the message and the number of initialized bytes in its
owner's buffer are separate quantities.

| FDB path | Buffer owner in IPRoute2 7.3.0 | Pilot coverage |
|---|---|---|
| Saved monitor file | `rtnl_from_file` reads aligned records into a reusable buffer | The pilot provides initialized storage through the final diagnostic field. |
| Live monitor | `rtnl_listen` dispatches records at aligned offsets in a received datagram | The pilot uses the same initialized buffer as file replay and still offers exactly 16 KiB to `recvmsg`. |
| FDB dump | `rtnl_recvmsg` allocates the datagram and `rtnl_dump_filter_l` iterates messages within the received length | The receiver initializes through the aligned end plus the diagnostic field. The public FDB dump matched canonical output under Memcheck. |
| Single FDB reply | `rtnl_talk` returns the owned receive buffer to `fdb_get` | The same initialized suffix travels with the allocation. The public single-entry query matched canonical output under Memcheck. |

For both monitor paths, `compat/iproute2/monitor_buffer.rs` keeps the
16,384-byte wire limit and reserves two initialized bytes beyond it in the
same aligned array. For a top-level FDB message, the first attribute starts
at byte 28. Every accepted attribute starts on a four-byte boundary and fits
in the remaining logical length, so its aligned end is at most the rounded-up
message end. The test checks the bound for each accepted FDB length from 28
through 16,384 and checks the final cursor at every possible aligned live
record start. Canonical and candidate commands also replay small, full-size
and small records in sequence and compare rejection of a 16,388-byte record.
The nested attribute handlers and other engines still require their own
caller checks before rollout to the default multicall.

The live test sends the same datagrams over local `NETLINK_USERSOCK` sockets
to the canonical and translated listeners. It checks FDB event order, the
exact truncation diagnostic, and continued dispatch on the following datagram.
Memcheck and Callgrind run on the translated listener and FDB printer.
Run `scripts/test_iproute2_rtattr.sh --kernel-events` to also compare both
public `bridge monitor fdb` commands on kernel-generated add and delete
events. This option gives the temporary container `NET_ADMIN` in its own
network namespace so it can create a test bridge and compare the public
`bridge fdb show` and `bridge fdb get` commands against the same entry.

For heap receives, the pilot keeps the upstream 32 KiB minimum and the
wire capacity passed to `recvmsg`. It reserves space through the next
four-byte boundary plus a two-byte field. After a successful receive, it
initializes only the two to five bytes following the actual payload. The
receiver frees the allocation on a receive error. A caller that requests
the buffer takes ownership and frees it after use.
Ten socket cases check payload bytes, advertised capacity and the initialized
suffix under Memcheck, covering short receives and all four length residues
above the allocation minimum.

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

GNU patch’s help candidate stores the 65 canonical lines in 2,907 bytes and
walks bounded, NUL-terminated slices. It removes a 66-entry static pointer
array, its raw traversal cursor and eight explicit pointer type occurrences.
The 18 blank lines and the tab in the backup-style description matched the
canonical help bytes. GCC, Clang, the parent and the rebuilt archive agreed
on help, invalid options and writes to a full device in 20 locales. Four
Memcheck runs passed. Reproduce the 69 compiler inputs with
`scripts/build_patch_help_catalog.py --prepare-parent LINK` and replay or
cold-build against that saved parent. [GNU patch archive results](evidence/patch-packed-help-archive.json)

The full 499-name executable passed 112 file comparisons across both dispatch modes and both canonical compilers. Each mode also reproduced the canonical upstream outcome of 47 passes and two expected failures, including a pass for the ed-style fixture. The candidate measured 24,961,776 bytes stripped. [Results](evidence/patch-packed-help-multicall.json)

The same transformation covers 120 GNU Diffutils message IDs across
`cmp`, `diff`, `diff3` and `sdiff`. Each applet still calls gettext for
individual messages. The source replay removes four traversal cursors and
124 pointer-array slots, including four sentinels. Its source count falls
by 20 explicit raw-pointer type occurrences. The shared transformation
reproduces the previously checked GNU patch compiler inputs byte for byte.
[Diffutils source replay](evidence/diffutils-packed-help-sources.json)

Both packed GNU help implementations also ran in one 499-name executable. Each public dispatch mode matched both canonical compilers for all five utilities, including translated help. The candidate measured 24,957,680 bytes stripped. [Results](evidence/diffutils-patch-packed-help-multicall.json)

The rebuilt archive matched GCC and Clang on 48 file cases each and 24 help and error profiles across four commands. French and German runs checked actual translated option text from the shipped GNU catalogs. All 16 Memcheck runs passed. [Results](evidence/diffutils-packed-help-archive.json)

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
LZ4 behavior suite. Compression retains the standalone allocation lifecycle.
On the current 499-name ELF, decompression and the canonical utility both
make and free 29 allocations. Valgrind traces the full 192-byte difference to
glibc thread-local storage for the two worker threads, 368 bytes per thread
in Rustbox and 272 in the standalone canonical program.
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

