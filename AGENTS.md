# Rustbox working contract

## Authority and scope

- GNU Coreutils and util-linux release sources pinned in
  `upstream/releases.json` are the primary semantic oracles.
- Work through all Coreutils applets before beginning the util-linux tranche,
  except for shared infrastructure needed by both.
- Rustbox is one multicall executable.  Do not introduce final per-applet
  executables or duplicate shared runtimes.
- Preserve raw Unix argument and filename bytes.  Do not insert UTF-8
  assumptions into canonical byte-oriented paths.

## Transformation discipline

- Never edit extracted canonical source.
- Keep C normalization and C-to-Rust translation in separate commits.
- A normalization commit must compile both stages and prove canonical C versus
  normalized C equivalence before any Rust change.
- Prefer deterministic tools: Clang tooling, Coccinelle semantic patches,
  preprocessing, generated ABI adapters, and repeatable scripts.
- Run multiple translation backends where practical.  Select the candidate
  with the lowest repair score that clears every correctness gate.
- Do not hand-repair generated Rust when a further deterministic C
  normalization can eliminate the repair.
- Preserve public symbol names and C ABI during incremental substitution.
- Keep both implementations available until differential tests pass.

## Correctness gates

- Build canonical C, normalized C, and candidate Rust independently.
- Run canonical upstream tests against canonical and Rustbox implementations.
- Compare status, stdout, stderr, errno, signals, filesystem effects, metadata,
  resource ownership, locale behavior, and timing-sensitive state where
  applicable.
- Run compiler warnings, Clang Static Analyzer, GCC `-fanalyzer`, Cppcheck,
  sanitizers, and differential fuzzing in proportion to the utility surface.
- Compilation is necessary but is never evidence of semantic equivalence by
  itself.
- Record every generated-code repair in the repair ledger.  Zero repair is the
  preferred outcome.

## Commits

- Keep commits buildable, reviewable, and limited to one mechanical change or
  one verified function substitution.
- Commit and push verified progress frequently.  Never commit generated build
  directories, downloaded release trees, caches, or analyzer databases.

