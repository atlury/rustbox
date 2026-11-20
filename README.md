# Rustbox

Rustbox is a single Rust multicall binary built by mechanically normalizing,
translating, and differentially verifying canonical Linux utility sources.
It is a new project; no applet is considered complete merely because it
compiles.

The initial authoritative source releases are:

- GNU Coreutils 9.12, released September 14, 2026;
- util-linux 2.42.4, released September 21, 2026.

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

| Upstream | Inventory | Signed source oracle | Hybrid canonical parity | Integrated Rust applets |
|---|---:|---:|---:|---:|
| GNU Coreutils 9.12 | 108 | 108 | 106 | 106 |
| util-linux 2.42.4 | 155 | 155 | 155 | 155 |
| GNU M4 1.4.21 | 1 | 1 | 1 | 1 |
| pkgconf 3.0.11 | 5 | 5 | 5 | 5 |
| File 5.48 | 1 | 1 | 1 | 1 |
| GNU patch 2.8 | 1 | 1 | 0 | 0 |

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
recorded in `evidence/rustbox-multicall.json`.  One binary dispatches all 267
distinct public names (106 Coreutils, 155 util-linux applets, GNU M4, and five
pkgconf names, with `kill` shared and `util-linux-kill` available explicitly).
It passes all 534
help/version oracle comparisons, all 14,022 cases in the 38 original batch
differential harnesses, and M4's full 242-check language suite, stack-overflow
check, 108-case differential suite, and Valgrind.  Pkgconf also passes all 429
CLI fixture checks, 55 exact differential comparisons, and Valgrind through
the unified dispatcher.  `chcon` and `runcon` remain absent, and the linked
binary has no SELinux or systemd dependency.

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

The next canonical oracle is zlib 1.4.  Its signed release, independent GCC
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
its own canonical libmagic behavior.  The resulting 268-name executable
is 5,668,624 bytes stripped, a 180,000-byte increase over the prior build, and
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
`evidence/patch-2.8-c2rust.json`.

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
   - [ ] GNU patch 2.8 — `patch`.
   - [ ] sed — `sed`.
   - [ ] Diffutils — `cmp`, `diff`, `diff3`, `sdiff`.
   - [ ] Grep — `grep`, `egrep`, `fgrep`.
   - [ ] bc — `bc`, `dc`.
   - [ ] attr — `attr`, `getfattr`, `setfattr`.
   - [ ] acl — `chacl`, `getfacl`, `setfacl`.
   - [ ] lz4 — `lz4`, `lz4c`, `lz4cat`, `unlz4`.
2. Compression, archive, and terminal foundations:
   - [ ] Gzip — `gzip`, `gunzip`, `zcat`, `uncompress`, `gzexe`, `zcmp`,
     `zdiff`, `zegrep`, `zfgrep`, `zforce`, `zgrep`, `zless`, `zmore`, `znew`.
   - [ ] xz — `xz`, `unxz`, `xzcat`, `lzma`, `unlzma`, `lzcat`, `xzdec`,
     `lzmadec`, `lzmainfo`, `xzcmp`, `xzdiff`, `xzegrep`, `xzfgrep`, `xzgrep`,
     `xzless`, `xzmore`.
   - [ ] zstd — `zstd`, `zstdmt`, `unzstd`, `zstdcat`, `zstdgrep`,
     `zstdless`.
   - [ ] tar — `tar`, `rmt`.
   - [ ] Ncurses — `captoinfo`, `clear`, `infocmp`, `infotocap`, `tabs`,
     `tic`, `toe`, `tput`, `tset`, `reset`, and the generated
     `ncurses*-config` helper; shared `ncurses`, `panel`, `form`, and `menu`
     libraries are part of the same integration.
   - [ ] less — `less`, `lesskey`, `lessecho`.
3. Multi-tool text processing and source generators:
   - [ ] Findutils — `find`, `xargs`, `locate`, `updatedb`.
   - [ ] Gawk — `gawk`, `awk`, `gawkbug`.
   - [ ] Flex — `flex`, `flex++`, `lex`.
   - [ ] Bison — `bison`, `yacc` (C/C++ skeletons only; Java output is out of
     scope).
4. Network-facing suites:
   - [ ] curl — `curl`, `curl-config`, plus the shared `libcurl` runtime.
   - [ ] Inetutils — `dnsdomainname`, `ftp`, `hostname`, `ifconfig`, `logger`,
     `ping`, `ping6`, `rcp`, `rexec`, `rlogin`, `rsh`, `talk`, `telnet`,
     `tftp`, `traceroute`, `whois`; and canonical daemons `ftpd`, `inetd`,
     `rexecd`, `rlogind`, `rshd`, `syslogd`, `talkd`, `telnetd`, `tftpd`,
     `uucpd`.
5. Large Linux system suites:
   - [ ] Kmod 34.3 — `kmod` and its installed `depmod`, `insmod`, `lsmod`,
     `modinfo`, `modprobe`, and `rmmod` compatibility links, plus the shared
     `libkmod` runtime; retain xz, zlib, and zstd module decompression through
     the corresponding canonical queued libraries.
   - [ ] Procps-ng 4.0.7 — `free`, `hugetop`, `kill`, `pgrep`, `pidof`,
     `pkill`, `pmap`, `ps`, `pwait`, `pwdx`, `skill`, `slabtop`, `snice`,
     `sysctl`, `tload`, `top`, `uptime`, `vmstat`, `w`, `watch`, plus the
     shared `libproc2` runtime; use the canonical GitLab release and exclude
     optional systemd and SELinux integration.  Duplicate public names such as
     `kill` and `uptime` remain separately verified until the final dispatcher
     precedence decision.
   - [ ] Shadow 4.20.3 — `chage`, `chfn`, `chgpasswd`, `chpasswd`, `chsh`,
     `faillog`, `getsubids`, `gpasswd`, `groupadd`, `groupdel`, `groupmod`,
     `grpck`, `grpconv`, `grpunconv`, `lastlog`, `login`, `newgidmap`,
     `newgrp`, `newuidmap`, `newusers`, `nologin`, `passwd`, `pwck`, `pwconv`,
     `pwunconv`, `su`, `useradd`, `userdel`, `usermod`, `vipw`, and the
     installed `sg` and `vigr` compatibility links, plus `libshadow` and
     `libsubid`.  Use the canonical `shadow-maint/shadow` release with SELinux
     and systemd integration disabled; separately verify duplicate public
     names supplied by util-linux before choosing final dispatcher precedence.
   - [ ] IPRoute2 — `arpd`, `bridge`, `ctstat`, `dcb`, `devlink`, `genl`,
     `ifcfg`, `ifstat`, `ip`, `lnstat`, `nstat`, `rdma`, `routef`, `routel`,
     `rtacct`, `rtmon`, `rtpr`, `rtstat`, `ss`, `tc`, `tipc`, `vdpa`.
   - [ ] E2fsprogs — `badblocks`, `chattr`, `debugfs`, `dumpe2fs`,
     `e2freefrag`, `e2fsck`, `e2image`, `e2label`, `e2mmpstatus`, `e2scrub`,
     `e2scrub_all`, `e2undo`, `e4crypt`, `e4defrag`, `filefrag`, `findfs`,
     `fsck`, `fsck.ext2`, `fsck.ext3`, `fsck.ext4`, `fuse2fs`, `logsave`,
     `lsattr`, `mk_cmds`, `mke2fs`, `mkfs.ext2`, `mkfs.ext3`, `mkfs.ext4`,
     `mklost+found`, `resize2fs`, `tune2fs`; `compile_et` is included as the
     canonical build helper.

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

