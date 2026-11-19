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
| GNU Coreutils 9.12 | 108 | 108 | 62 | 0 |
| util-linux 2.42.4 | 155 | 0 | 0 | 0 |

The Coreutils oracle and its local test evidence are recorded in
`evidence/coreutils-9.12-oracle.json`.  The complete canonical static-analysis
baseline is in `evidence/coreutils-9.12-static-analysis.json`; translation and
hybrid evidence for the first six ten-applet batches is in
`evidence/coreutils-9.12-c2rust-small-01.json`,
`evidence/coreutils-9.12-c2rust-small-02.json`, and
`evidence/coreutils-9.12-c2rust-small-03.json`,
`evidence/coreutils-9.12-c2rust-small-04.json`,
`evidence/coreutils-9.12-c2rust-small-05.json`, and
`evidence/coreutils-9.12-c2rust-small-06.json`.  An oracle-built applet is not
marked complete in the inventory below; completion is reserved for translated
Rust that has reached canonical behavioral parity through the multicall
interface.

## Applet inventory

This list is generated from the pinned upstream build definitions by
`scripts/generate_inventory.py`.  Keep it current as each applet advances from
inventory through normalization, translation, integration, and canonical-test
parity.

<!-- BEGIN APPLET INVENTORY -->

### GNU Coreutils 9.12 (108)

- [ ] `[` — inventory
- [x] `arch` — hybrid canonical parity; repair score 5
- [ ] `b2sum` — inventory
- [x] `base32` — hybrid canonical parity; repair score 7
- [x] `base64` — hybrid canonical parity; repair score 5
- [x] `basename` — hybrid canonical parity; repair score 5
- [ ] `basenc` — inventory
- [x] `cat` — hybrid canonical parity; repair score 5
- [ ] `chcon` — inventory
- [x] `chgrp` — hybrid canonical parity; repair score 5
- [ ] `chmod` — inventory
- [ ] `chown` — inventory
- [x] `chroot` — hybrid canonical parity; repair score 7
- [ ] `cksum` — inventory
- [x] `comm` — hybrid canonical parity; repair score 5
- [ ] `cp` — inventory
- [ ] `csplit` — inventory
- [ ] `cut` — inventory
- [ ] `date` — inventory
- [ ] `dd` — inventory
- [ ] `df` — inventory
- [x] `dir` — hybrid canonical parity; repair score 5
- [x] `dircolors` — hybrid canonical parity; repair score 5
- [x] `dirname` — hybrid canonical parity; repair score 5
- [ ] `du` — inventory
- [x] `echo` — hybrid canonical parity; repair score 5
- [ ] `env` — inventory
- [ ] `expand` — inventory
- [ ] `expr` — inventory
- [ ] `factor` — inventory
- [x] `false` — hybrid canonical parity; repair score 3
- [x] `fmt` — hybrid canonical parity; repair score 5
- [x] `fold` — hybrid canonical parity; repair score 7
- [x] `groups` — hybrid canonical parity; repair score 5
- [ ] `head` — inventory
- [x] `hostid` — hybrid canonical parity; repair score 5
- [x] `hostname` — hybrid canonical parity; repair score 5
- [ ] `id` — inventory
- [ ] `install` — inventory
- [ ] `join` — inventory
- [x] `kill` — hybrid canonical parity; repair score 7
- [x] `link` — hybrid canonical parity; repair score 5
- [ ] `ln` — inventory
- [x] `logname` — hybrid canonical parity; repair score 5
- [ ] `ls` — inventory
- [x] `md5sum` — hybrid canonical parity; repair score 5
- [ ] `mkdir` — inventory
- [ ] `mkfifo` — inventory
- [ ] `mknod` — inventory
- [x] `mktemp` — hybrid canonical parity; repair score 5
- [ ] `mv` — inventory
- [x] `nice` — hybrid canonical parity; repair score 5
- [x] `nl` — hybrid canonical parity; repair score 5
- [x] `nohup` — hybrid canonical parity; repair score 5
- [x] `nproc` — hybrid canonical parity; repair score 5
- [ ] `numfmt` — inventory
- [ ] `od` — inventory
- [x] `paste` — hybrid canonical parity; repair score 7
- [x] `pathchk` — hybrid canonical parity; repair score 5
- [x] `pinky` — hybrid canonical parity; repair score 5
- [ ] `pr` — inventory
- [x] `printenv` — hybrid canonical parity; repair score 5
- [ ] `printf` — inventory
- [ ] `ptx` — inventory
- [x] `pwd` — hybrid canonical parity; repair score 5
- [x] `readlink` — hybrid canonical parity; repair score 5
- [x] `realpath` — hybrid canonical parity; repair score 5
- [ ] `rm` — inventory
- [x] `rmdir` — hybrid canonical parity; repair score 7
- [x] `runcon` — hybrid canonical parity; repair score 5
- [ ] `seq` — inventory
- [x] `sha1sum` — hybrid canonical parity; repair score 5
- [x] `sha224sum` — hybrid canonical parity; repair score 5
- [x] `sha256sum` — hybrid canonical parity; repair score 5
- [x] `sha384sum` — hybrid canonical parity; repair score 5
- [x] `sha512sum` — hybrid canonical parity; repair score 5
- [ ] `shred` — inventory
- [x] `shuf` — hybrid canonical parity; repair score 5
- [x] `sleep` — hybrid canonical parity; repair score 5
- [ ] `sort` — inventory
- [ ] `split` — inventory
- [ ] `stat` — inventory
- [x] `stdbuf` — hybrid canonical parity; repair score 5
- [ ] `stty` — inventory
- [x] `sum` — hybrid canonical parity; repair score 7
- [x] `sync` — hybrid canonical parity; repair score 5
- [x] `tac` — hybrid canonical parity; repair score 5
- [ ] `tail` — inventory
- [x] `tee` — hybrid canonical parity; repair score 7
- [ ] `test` — inventory
- [x] `timeout` — hybrid canonical parity; repair score 5
- [x] `touch` — hybrid canonical parity; repair score 7
- [ ] `tr` — inventory
- [x] `true` — hybrid canonical parity; repair score 3
- [x] `truncate` — hybrid canonical parity; repair score 5
- [x] `tsort` — hybrid canonical parity; repair score 5
- [x] `tty` — hybrid canonical parity; repair score 5
- [x] `uname` — hybrid canonical parity; repair score 7
- [ ] `unexpand` — inventory
- [x] `uniq` — hybrid canonical parity; repair score 5
- [x] `unlink` — hybrid canonical parity; repair score 5
- [x] `uptime` — hybrid canonical parity; repair score 5
- [x] `users` — hybrid canonical parity; repair score 5
- [x] `vdir` — hybrid canonical parity; repair score 5
- [ ] `wc` — inventory
- [ ] `who` — inventory
- [x] `whoami` — hybrid canonical parity; repair score 5
- [x] `yes` — hybrid canonical parity; repair score 5

### util-linux 2.42.4 (155)

- [ ] `addpart` — inventory
- [ ] `agetty` — inventory
- [ ] `bits` — inventory
- [ ] `blkdiscard` — inventory
- [ ] `blkid` — inventory
- [ ] `blkpr` — inventory
- [ ] `blkzone` — inventory
- [ ] `blockdev` — inventory
- [ ] `cal` — inventory
- [ ] `cfdisk` — inventory
- [ ] `chcpu` — inventory
- [ ] `chfn` — inventory
- [ ] `chmem` — inventory
- [ ] `choom` — inventory
- [ ] `chrt` — inventory
- [ ] `chsh` — inventory
- [ ] `col` — inventory
- [ ] `colcrt` — inventory
- [ ] `colrm` — inventory
- [ ] `column` — inventory
- [ ] `copyfilerange` — inventory
- [ ] `coresched` — inventory
- [ ] `ctrlaltdel` — inventory
- [ ] `delpart` — inventory
- [ ] `dmesg` — inventory
- [ ] `eject` — inventory
- [ ] `enosys` — inventory
- [ ] `exch` — inventory
- [ ] `fadvise` — inventory
- [ ] `fallocate` — inventory
- [ ] `fdformat` — inventory
- [ ] `fdisk` — inventory
- [ ] `fincore` — inventory
- [ ] `findfs` — inventory
- [ ] `findmnt` — inventory
- [ ] `flock` — inventory
- [ ] `fsck` — inventory
- [ ] `fsck.cramfs` — inventory
- [ ] `fsck.minix` — inventory
- [ ] `fsfreeze` — inventory
- [ ] `fstrim` — inventory
- [ ] `getino` — inventory
- [ ] `getopt` — inventory
- [ ] `hardlink` — inventory
- [ ] `hexdump` — inventory
- [ ] `hwclock` — inventory
- [ ] `i386` — inventory
- [ ] `ia64` — inventory
- [ ] `ionice` — inventory
- [ ] `ipcmk` — inventory
- [ ] `ipcrm` — inventory
- [ ] `ipcs` — inventory
- [ ] `irqtop` — inventory
- [ ] `isosize` — inventory
- [ ] `kill` — inventory
- [ ] `last` — inventory
- [ ] `lastb` — inventory
- [ ] `lastlog2` — inventory
- [ ] `ldattach` — inventory
- [ ] `line` — inventory
- [ ] `linux32` — inventory
- [ ] `linux64` — inventory
- [ ] `logger` — inventory
- [ ] `login` — inventory
- [ ] `look` — inventory
- [ ] `losetup` — inventory
- [ ] `lsblk` — inventory
- [ ] `lsclocks` — inventory
- [ ] `lscpu` — inventory
- [ ] `lsfd` — inventory
- [ ] `lsipc` — inventory
- [ ] `lsirq` — inventory
- [ ] `lslocks` — inventory
- [ ] `lslogins` — inventory
- [ ] `lsmem` — inventory
- [ ] `lsns` — inventory
- [ ] `mcookie` — inventory
- [ ] `mesg` — inventory
- [ ] `mips` — inventory
- [ ] `mips32` — inventory
- [ ] `mips64` — inventory
- [ ] `mkfs` — inventory
- [ ] `mkfs.bfs` — inventory
- [ ] `mkfs.cramfs` — inventory
- [ ] `mkfs.minix` — inventory
- [ ] `mkswap` — inventory
- [ ] `more` — inventory
- [ ] `mount` — inventory
- [ ] `mountpoint` — inventory
- [ ] `namei` — inventory
- [ ] `newgrp` — inventory
- [ ] `nologin` — inventory
- [ ] `nsenter` — inventory
- [ ] `parisc` — inventory
- [ ] `parisc32` — inventory
- [ ] `parisc64` — inventory
- [ ] `partx` — inventory
- [ ] `pg` — inventory
- [ ] `pipesz` — inventory
- [ ] `pivot_root` — inventory
- [ ] `ppc` — inventory
- [ ] `ppc32` — inventory
- [ ] `ppc64` — inventory
- [ ] `prlimit` — inventory
- [ ] `raw` — inventory
- [ ] `readprofile` — inventory
- [ ] `rename` — inventory
- [ ] `renice` — inventory
- [ ] `resizepart` — inventory
- [ ] `rev` — inventory
- [ ] `rfkill` — inventory
- [ ] `rtcwake` — inventory
- [ ] `runuser` — inventory
- [ ] `s390` — inventory
- [ ] `s390x` — inventory
- [ ] `script` — inventory
- [ ] `scriptlive` — inventory
- [ ] `scriptreplay` — inventory
- [ ] `setarch` — inventory
- [ ] `setpgid` — inventory
- [ ] `setpriv` — inventory
- [ ] `setsid` — inventory
- [ ] `setterm` — inventory
- [ ] `sfdisk` — inventory
- [ ] `sparc` — inventory
- [ ] `sparc32` — inventory
- [ ] `sparc32bash` — inventory
- [ ] `sparc64` — inventory
- [ ] `su` — inventory
- [ ] `sulogin` — inventory
- [ ] `swaplabel` — inventory
- [ ] `swapoff` — inventory
- [ ] `swapon` — inventory
- [ ] `switch_root` — inventory
- [ ] `taskset` — inventory
- [ ] `tunelp` — inventory
- [ ] `uclampset` — inventory
- [ ] `ul` — inventory
- [ ] `umount` — inventory
- [ ] `uname26` — inventory
- [ ] `unshare` — inventory
- [ ] `utmpdump` — inventory
- [ ] `uuidd` — inventory
- [ ] `uuidgen` — inventory
- [ ] `uuidparse` — inventory
- [ ] `vigr` — inventory
- [ ] `vipw` — inventory
- [ ] `waitpid` — inventory
- [ ] `wall` — inventory
- [ ] `wdctl` — inventory
- [ ] `whereis` — inventory
- [ ] `wipefs` — inventory
- [ ] `write` — inventory
- [ ] `x86_64` — inventory
- [ ] `zramctl` — inventory

**Total: 263 applet names.**

<!-- END APPLET INVENTORY -->

