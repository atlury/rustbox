#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/e2fsprogs-1.47.4"
base="$analysis/program-translations"
programs="badblocks chattr debugfs dumpe2fs e2freefrag e2fsck e2image e2initrd_helper e2undo e4crypt e4defrag filefrag fsck fuse2fs logsave lsattr mke2fs mklost_found resize2fs tune2fs"

test -f "$analysis/program-closures/summary.json"
mkdir -p "$base"
if test "${RUSTBOX_E2FS_SKIP_TRANSPILE:-0}" != 1; then
  for name in $programs; do
	  program="$base/$name"
	  audit="$program/$name-audit"
	  case "$audit" in
		  "$base"/*/*-audit) test ! -e "$audit" || rm -rf -- "$audit" ;;
		  *) exit 2 ;;
	  esac
	  mkdir -p "$program"
  done

  docker run --rm --platform linux/amd64 --interactive \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    base=/work/work/analysis/e2fsprogs-1.47.4/program-translations
    closures=/work/work/analysis/e2fsprogs-1.47.4/program-closures/engines
    export base closures
    printf "%s\n" badblocks chattr debugfs dumpe2fs e2freefrag e2fsck \
      e2image e2initrd_helper e2undo e4crypt e4defrag filefrag fsck fuse2fs \
      logsave lsattr mke2fs mklost_found resize2fs tune2fs |
      xargs -n 1 -P 8 sh -eu -c '\''
        name=$1
        output=$base/$name/$name-audit
        RAYON_NUM_THREADS=1 c2rust transpile \
          "$closures/$name/compile_commands.json" \
          --output-dir "$output" \
          --emit-build-files --fail-on-error --disable-rustfmt \
          --overwrite-existing --preserve-unused-functions \
          >"$base/$name/transpile.log" 2>&1
      '\'' sh
    chmod -R a+rwX "$base"
  '
fi

for name in $programs; do
	program="$base/$name"
	python3 -B "$root/scripts/finalize_e2fsprogs_stable.py" \
		--program "$name" --input "$program/$name-audit" \
		--output "$program/$name-final" >"$program/finalize.log"
done

exec docker run --rm --platform linux/amd64 --interactive \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    base=/work/work/analysis/e2fsprogs-1.47.4/program-translations
    export base
    printf "%s\n" badblocks chattr debugfs dumpe2fs e2freefrag e2fsck \
      e2image e2initrd_helper e2undo e4crypt e4defrag filefrag fsck fuse2fs \
      logsave lsattr mke2fs mklost_found resize2fs tune2fs |
      xargs -n 1 -P 8 sh -eu -c '\''
        name=$1
        crate=$base/$name/$name-final
        export CARGO_TARGET_DIR=$base/cargo-target/$name
        python3 /work/scripts/check_cargo_crate.py \
          --crate "$crate" --output "$crate/rustbox-cargo-check.json" \
          --toolchain nightly-2023-04-15 \
          >"$base/$name/cargo-check.log" 2>&1
        RUSTUP_TOOLCHAIN=nightly-2023-04-15 \
          cargo build --manifest-path "$crate/Cargo.toml" --release \
          >"$base/$name/cargo-build.log" 2>&1
      '\'' sh
    chmod -R a+rwX "$base"
  '
