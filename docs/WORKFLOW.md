# Translation workflow

Rustbox minimizes repair burden rather than committing to a particular C-to-
Rust translator.  Canonical behavior is the judge; translator popularity,
safe-code percentage, and successful compilation are secondary measurements.

## Immutable stages

```text
signed release C
  -> configured canonical C oracle
  -> deterministic normalized C
  -> candidate Rust backends
  -> ABI-preserving mixed C/Rust executable
  -> Rustbox multicall applet
```

Canonical releases are downloaded and hash-checked by
`scripts/fetch_upstreams.py`.  Builds use separate directories.  Normalization
outputs, translation outputs, test evidence, and repair ledgers identify their
input digest and tool versions.

`scripts/verify_source_tree.py PACKAGE` byte-compares every extracted member
against the pinned release archive and rejects added, removed, or changed
members.  Coreutils' GCC multicall oracle is built out-of-tree by
`scripts/build_coreutils_oracle.sh` and tested by
`scripts/test_coreutils_oracle.sh`; its normally disabled `arch`, `hostname`,
`kill`, and `uptime` programs are explicitly enabled.

Oracle builds and tests live in the persistent `rustbox-coreutils-9.12` Docker
volume, not the macOS bind mount.  The byte-verified canonical source has its
own `rustbox-coreutils-source-9.12` volume and is mounted read-only during every
build, analysis, and test run.  This prevents container root or an analyzer
from silently changing the oracle.  The Linux volumes are also required for
genuine FIFO, inotify, sparse-file, permission, and deep-path behavior.  The
standard suite runs as a two-group unprivileged user by default; `root` and
`expensive` modes are separate, explicit passes.

## Normalization toolbox

Use the smallest ordered passes that make a translation unit explicit without
changing its behavior:

1. Clang parse and compilation-database validation.
2. Coccinelle semantic patches for repeated API and data-flow rewrites.
3. Clang-Tidy or custom LibTooling fixes for AST-safe mechanical changes.
4. Preprocessor specialization for declared target-platform macros.
5. Explicit prototypes, conversions, evaluation order, pointer/length pairs,
   ownership annotations, context structures, and narrow syscall wrappers.
6. Cppcheck, Clang Static Analyzer, GCC `-fanalyzer`, sanitizers, and canonical
   tests after every pass.

Do not combine algorithm changes with normalization.  If canonical and
normalized C differ, reject the pass.

Normalization is a gated experiment, not a one-way source rewrite.  For each
translation unit and each candidate pass:

1. Bear records the real compiler invocations; reject entries that Clang
   cannot replay without changing flags or generated headers.
2. Freeze the pre-pass source digest, preprocessed token stream, exported
   symbols, type layouts, call graph, diagnostics, and canonical behavior.
3. Apply exactly one versioned Coccinelle semantic patch or one exported
   Clang-Tidy/LibTooling replacement set to a disposable tree.
4. Rebuild with GCC and Clang.  Compare ABI with symbol tables and DWARF/type
   layout tools; compile-time equivalence is necessary but not sufficient.
5. Run Cppcheck, Sparse, Splint, Flawfinder, Clang Static Analyzer through
   CodeChecker, and GCC `-fanalyzer`.  New diagnostics reject the pass;
   existing findings stay in a baseline rather than being silently hidden.
6. Run ASan/UBSan, Valgrind, canonical tests, syscall-trace comparisons, and
   differential fuzzing.  Reject any changed exit status, signal, `errno`,
   output byte, filesystem effect, metadata, or resource lifetime.
7. Measure every translator again.  Keep the C pass only when it is behavior
   neutral and reduces holes, compiler errors, unsafe boundary complexity, or
   weighted repair score.

Warnings are evidence, not normalization instructions.  A static analyzer may
find a genuine upstream defect, but fixing that defect is a separate patch and
cannot be smuggled into the translation-friendly C.  Formatting-only churn is
excluded because it obscures semantic review without helping the translator.

`scripts/capture_coreutils_compdb.sh` performs the canonical Clang build and
stores its validated database under ignored `work/analysis/`.  The validator
intentionally retains multiple commands for one source file: Coreutils builds
shared implementation files with different preprocessor definitions for
different applets, and deduplicating by filename would discard configurations.

The pinned local tool image is described by `tools/versions.json` and built by
`scripts/build_tool_image.sh`.  `scripts/run_tool.sh rustbox-tool-report`
records the effective versions.  CodeChecker's complete Python dependency
graph is frozen in `tools/codechecker-requirements.lock`; C2Rust uses its
upstream locked Cargo graph.  GitHub-hosted workflows are intentionally not
part of this process.

The separately versioned `rustbox-normalize:2026-11-19` image extends that
exact, ID-checked base with Libabigail/ABI Dumper, `pahole`, C-Vise, and
C-Reduce.  ABI and layout tools guard mechanical rewrites; reducers shrink
translator and analyzer failures into reviewable fixtures.  Set
`RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19` only for stages that need
them, leaving the recorded oracle environment unchanged.

The image also supplies canonical-suite fixtures (ACL/xattr/capability tools,
Perl Expect, and representative single-byte, multibyte, and UTF-8 locales).
A skip caused by an unavailable fixture is treated as a missing dependency,
not as evidence of correctness.

## Candidate translation backends

The backend set is extensible.  Start with C2Rust, AST-guided generation, and a
minimal ABI-preserving direct port.  Add other reproducible translators when
they can run locally.  LLVM IR is useful as a comparison and analysis layer,
but is not the preferred maintainable source representation.

Each backend receives the same normalized C and test corpus.  Generated Rust
is retained unchanged first so its actual compilation and parity rate can be
measured.

The initial raw-C baseline uses `--fail-on-error`, emits C-declaration maps,
and enables C2Rust's `--preserve-unused-functions`.  Therefore a successful
translation cannot improve its score by silently omitting an unused static
function.  `scripts/translate_coreutils_true_false.sh` is the first measured
slice; it keeps the exact captured compiler arguments for the shared `true`
implementation and the `false` wrapper.

`scripts/build_coreutils_true_false_hybrid.sh` performs the next gate without
editing generated Rust: it builds the static library, removes only the two C
archives from the canonical multicall dependency list, suppresses the C
wrapper's extra dependency on the C `true` archive, and emits a separate
hybrid binary.  It rejects duplicate or missing replacement symbols before
behavioral comparison.

`scripts/test_coreutils_true_false_hybrid.sh` then compares public dispatcher
and argv-zero invocation byte-for-byte across raw arguments and five locales,
including closed-output-pipe failures.  It also runs the upstream false-status
and help/version tests while a trap temporarily redirects only the `true` and
`false` symlinks to the hybrid; the canonical multicall binary is never
overwritten.  `scripts/check_coreutils_true_false_resources.sh` separately
runs Valgrind over normal, help, and version paths for both applets.

## Repair score

Repairs are changes to generated Rust, not proven C normalization passes.
Record each repair with its input digest, function, tool, reason, and tests.

| Weight | Repair class |
|---:|---|
| 0 | generated Rust accepted unchanged |
| 1 | formatting, import, or unambiguous syntax repair |
| 2 | mechanical type or lifetime spelling repair |
| 4 | ABI, layout, ownership, or allocation repair |
| 8 | control-flow or error-path repair |
| 16 | algorithm or observable semantic repair |

Prefer a zero-repair backend.  If every backend requires repair, first improve
normalization and rerun them.  Manual semantic repair is the last resort.

## Function substitution

Replace pure functions first and process, signal, locale, terminal, mount, and
privilege logic last.  Keep the canonical C function and Rust function callable
through the same narrow C ABI.  Compare them directly until canonical tests,
generated cases, fuzzing, analyzers, and sanitizer runs agree.  Remove the C
body only in a later commit.

## Applet completion

An applet is complete only after its complete canonical upstream test suite and
Rustbox-specific adversarial suite pass through the public multicall interface.
The ledger must cover all canonical source functions and observable branches;
unsupported behavior must remain explicit rather than being silently omitted.

