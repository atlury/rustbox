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
| GNU Coreutils 9.12 | 108 | 108 | 22 | 0 |
| util-linux 2.42.4 | 155 | 0 | 0 | 0 |

The Coreutils oracle and its local test evidence are recorded in
`evidence/coreutils-9.12-oracle.json`.  The complete canonical static-analysis
baseline is in `evidence/coreutils-9.12-static-analysis.json`; translation and
hybrid evidence for the first two ten-applet batches is in
`evidence/coreutils-9.12-c2rust-small-01.json` and
`evidence/coreutils-9.12-c2rust-small-02.json`.  An oracle-built applet is not
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
- [ ] `arch` — inventory
- [ ] `b2sum` — inventory
- [ ] `base32` — inventory
- [ ] `base64` — inventory
- [ ] `basename` — hybrid canonical parity
- [ ] `basenc` — inventory
- [ ] `cat` — inventory
- [ ] `chcon` — inventory
- [ ] `chgrp` — inventory
- [ ] `chmod` — inventory
- [ ] `chown` — inventory
- [ ] `chroot` — inventory
- [ ] `cksum` — inventory
- [ ] `comm` — inventory
- [ ] `cp` — inventory
- [ ] `csplit` — inventory
- [ ] `cut` — inventory
- [ ] `date` — inventory
- [ ] `dd` — inventory
- [ ] `df` — inventory
- [ ] `dir` — inventory
- [ ] `dircolors` — inventory
- [ ] `dirname` — hybrid canonical parity
- [ ] `du` — inventory
- [ ] `echo` — inventory
- [ ] `env` — inventory
- [ ] `expand` — inventory
- [ ] `expr` — inventory
- [ ] `factor` — inventory
- [ ] `false` — hybrid canonical parity
- [ ] `fmt` — inventory
- [ ] `fold` — inventory
- [ ] `groups` — inventory
- [ ] `head` — inventory
- [ ] `hostid` — hybrid canonical parity
- [ ] `hostname` — inventory
- [ ] `id` — inventory
- [ ] `install` — inventory
- [ ] `join` — inventory
- [ ] `kill` — inventory
- [ ] `link` — hybrid canonical parity
- [ ] `ln` — inventory
- [ ] `logname` — hybrid canonical parity
- [ ] `ls` — inventory
- [ ] `md5sum` — inventory
- [ ] `mkdir` — inventory
- [ ] `mkfifo` — inventory
- [ ] `mknod` — inventory
- [ ] `mktemp` — inventory
- [ ] `mv` — inventory
- [ ] `nice` — inventory
- [ ] `nl` — inventory
- [ ] `nohup` — inventory
- [ ] `nproc` — inventory
- [ ] `numfmt` — inventory
- [ ] `od` — inventory
- [ ] `paste` — inventory
- [ ] `pathchk` — inventory
- [ ] `pinky` — inventory
- [ ] `pr` — inventory
- [ ] `printenv` — hybrid canonical parity
- [ ] `printf` — inventory
- [ ] `ptx` — inventory
- [ ] `pwd` — inventory
- [ ] `readlink` — inventory
- [ ] `realpath` — inventory
- [ ] `rm` — inventory
- [ ] `rmdir` — inventory
- [ ] `runcon` — inventory
- [ ] `seq` — inventory
- [ ] `sha1sum` — inventory
- [ ] `sha224sum` — inventory
- [ ] `sha256sum` — inventory
- [ ] `sha384sum` — inventory
- [ ] `sha512sum` — inventory
- [ ] `shred` — inventory
- [ ] `shuf` — inventory
- [ ] `sleep` — inventory
- [ ] `sort` — inventory
- [ ] `split` — inventory
- [ ] `stat` — inventory
- [ ] `stdbuf` — inventory
- [ ] `stty` — inventory
- [ ] `sum` — inventory
- [ ] `sync` — inventory
- [ ] `tac` — inventory
- [ ] `tail` — inventory
- [ ] `tee` — inventory
- [ ] `test` — inventory
- [ ] `timeout` — inventory
- [ ] `touch` — inventory
- [ ] `tr` — inventory
- [ ] `true` — hybrid canonical parity
- [ ] `truncate` — inventory
- [ ] `tsort` — inventory
- [ ] `tty` — hybrid canonical parity
- [ ] `uname` — inventory
- [ ] `unexpand` — inventory
- [ ] `uniq` — inventory
- [ ] `unlink` — hybrid canonical parity
- [ ] `uptime` — inventory
- [ ] `users` — inventory
- [ ] `vdir` — inventory
- [ ] `wc` — inventory
- [ ] `who` — inventory
- [ ] `whoami` — hybrid canonical parity
- [ ] `yes` — hybrid canonical parity

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

