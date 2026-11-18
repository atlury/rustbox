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

The pinned local tool image is described by `tools/versions.json` and built by
`scripts/build_tool_image.sh`.  `scripts/run_tool.sh rustbox-tool-report`
records the effective versions.  CodeChecker's complete Python dependency
graph is frozen in `tools/codechecker-requirements.lock`; C2Rust uses its
upstream locked Cargo graph.  GitHub-hosted workflows are intentionally not
part of this process.

## Candidate translation backends

The backend set is extensible.  Start with C2Rust, AST-guided generation, and a
minimal ABI-preserving direct port.  Add other reproducible translators when
they can run locally.  LLVM IR is useful as a comparison and analysis layer,
but is not the preferred maintainable source representation.

Each backend receives the same normalized C and test corpus.  Generated Rust
is retained unchanged first so its actual compilation and parity rate can be
measured.

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

