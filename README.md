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
- [ ] `basename` — inventory
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
- [ ] `dirname` — inventory
- [ ] `du` — inventory
- [ ] `echo` — inventory
- [ ] `env` — inventory
- [ ] `expand` — inventory
- [ ] `expr` — inventory
- [ ] `factor` — inventory
- [ ] `false` — inventory
- [ ] `fmt` — inventory
- [ ] `fold` — inventory
- [ ] `groups` — inventory
- [ ] `head` — inventory
- [ ] `hostid` — inventory
- [ ] `hostname` — inventory
- [ ] `id` — inventory
- [ ] `install` — inventory
- [ ] `join` — inventory
- [ ] `kill` — inventory
- [ ] `link` — inventory
- [ ] `ln` — inventory
- [ ] `logname` — inventory
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
- [ ] `printenv` — inventory
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
- [ ] `true` — inventory
- [ ] `truncate` — inventory
- [ ] `tsort` — inventory
- [ ] `tty` — inventory
- [ ] `uname` — inventory
- [ ] `unexpand` — inventory
- [ ] `uniq` — inventory
- [ ] `unlink` — inventory
- [ ] `uptime` — inventory
- [ ] `users` — inventory
- [ ] `vdir` — inventory
- [ ] `wc` — inventory
- [ ] `who` — inventory
- [ ] `whoami` — inventory
- [ ] `yes` — inventory

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

