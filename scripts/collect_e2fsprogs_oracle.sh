#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --interactive --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 python3 -B - <<'PY'
import hashlib, json, os, re, subprocess
from pathlib import Path

evidence = Path('/work/work/analysis/e2fsprogs-1.47.4/oracle')
expected_aliases = {
    'sbin/dumpe2fs': ['sbin/e2mmpstatus'],
    'sbin/e2fsck': ['sbin/fsck.ext2', 'sbin/fsck.ext3', 'sbin/fsck.ext4'],
    'sbin/mke2fs': ['sbin/mkfs.ext2', 'sbin/mkfs.ext3', 'sbin/mkfs.ext4'],
    'sbin/tune2fs': ['sbin/e2label'],
}
for compiler in ('gcc', 'clang-18'):
    stage = Path('/rustbox-e2fsprogs') / f'stage-{compiler}'
    inventory = [
        line for line in (evidence / f'{compiler}-installed-executables.txt').read_text().splitlines()
        if line
    ]
    records = []
    by_inode = {}
    for relative in inventory:
        path = stage / relative
        data = path.read_bytes()
        file_kind = subprocess.run(
            ['file', '-b', str(path)], check=True, text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        dependencies = []
        if file_kind.startswith('ELF '):
            dynamic = subprocess.run(
                ['readelf', '-d', str(path)], check=True, text=True,
                stdout=subprocess.PIPE,
            ).stdout
            dependencies = re.findall(r'Shared library: \[([^]]+)\]', dynamic)
        stat = path.stat()
        by_inode.setdefault((stat.st_dev, stat.st_ino), []).append(relative)
        records.append({
            'path': relative,
            'kind': 'elf' if file_kind.startswith('ELF ') else 'script',
            'file': file_kind,
            'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'dynamic_dependencies': dependencies,
        })
    actual_alias_groups = {frozenset(members) for members in by_inode.values() if len(members) > 1}
    expected_alias_groups = {
        frozenset((engine, *aliases)) for engine, aliases in expected_aliases.items()
    }
    if actual_alias_groups != expected_alias_groups:
        raise RuntimeError(f'E2fsprogs installed alias topology changed: {actual_alias_groups}')
    output = {
        'schema': 1,
        'compiler': compiler,
        'installed_names': len(records),
        'engines': len(by_inode),
        'hardlink_aliases': expected_aliases,
        'records': records,
    }
    (evidence / f'{compiler}-installed-metadata.json').write_text(
        json.dumps(output, indent=2, sort_keys=True) + '\n'
    )
os.system(f'chmod -R a+rwX {evidence}')
PY
