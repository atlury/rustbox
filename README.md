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

| Upstream | Inventory | Signed source oracle | Hybrid canonical parity | Integrated Rust applets |
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
recorded in `evidence/rustbox-multicall.json`.  One binary dispatches all 282
distinct public names (106 Coreutils, 155 util-linux applets, GNU M4, five
pkgconf names, File, GNU patch, GNU sed, four GNU Diffutils applets, and GNU
Grep's three public names, GNU bc and dc, plus attr, getfattr, and setfattr;
`kill` is shared and `util-linux-kill` remains available explicitly).  It passes all 564
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
and canonical allocation lifecycles through the same dispatcher.  The stripped
282-name executable is 6,717,616 bytes.  `chcon` and `runcon`
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

