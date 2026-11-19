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
| GNU Coreutils 9.12 | 108 | 108 | 107 | 0 |
| util-linux 2.42.4 | 155 | 155 | 70 | 0 |

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
`evidence/coreutils-9.12-c2rust-small-23.json`.  All 107 applets in scope under
the no-SELinux policy have reached hybrid canonical parity.  An oracle-built
applet is not marked complete in the inventory below; completion is reserved for translated
Rust that has reached canonical behavioral parity through the multicall
interface.

The signed util-linux oracle is recorded in
`evidence/util-linux-2.42.4-oracle.json`.  Its 155 public names comprise 132
canonical executables and 23 upstream aliases.  The build explicitly excludes
SELinux, systemd, audit, udev, Python bindings, and PAM lastlog integration;
it retains the ordinary non-SELinux implementations, including `mkfifo`-like
filesystem functionality elsewhere in Rustbox.  `setpriv`, `lastlog2`, and the
legacy `raw` utility are deliberately enabled rather than silently omitted.
The paired Clang/GCC command inventory is recorded in
`evidence/util-linux-2.42.4-compdb.json`.  Translation, normalization,
hybrid-link, differential, upstream-test, and Valgrind evidence for the first
seven batches is in `evidence/util-linux-2.42.4-c2rust-small-01.json`,
`evidence/util-linux-2.42.4-c2rust-small-02.json`,
`evidence/util-linux-2.42.4-c2rust-small-03.json`, and
`evidence/util-linux-2.42.4-c2rust-small-04.json`,
`evidence/util-linux-2.42.4-c2rust-small-05.json`,
`evidence/util-linux-2.42.4-c2rust-small-06.json`, and
`evidence/util-linux-2.42.4-c2rust-small-07.json`.  Seventy util-linux applets
have reached hybrid canonical parity; final Rustbox integration remains
deliberately deferred until the applet batches are complete.

## Work queue after util-linux

No package in this queue starts until all in-scope util-linux applets reach
canonical parity and the completed Coreutils and util-linux translations are
linked and verified together as the single `rustbox` multicall executable.
This ordering is from lower to higher estimated translation and integration
complexity; build dependencies may be prepared earlier when a queued package
requires them.  Names include canonical installed aliases, but not examples or
test-only binaries.  The duplicate `gzip` request is represented once.

1. Small libraries and single-purpose tools:
   - [ ] zlib — shared compression library; no installed applet (`minigzip` is
     an example/test helper).
   - [ ] pkg-config — `pkg-config`.
   - [ ] M4 — `m4`.
   - [ ] File — `file`.
   - [ ] patch — `patch`.
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
   - [ ] Readline — shared `readline` and `history` libraries; no canonical
     installed applet (`rlfe` remains an example).
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
- [x] `runcon` — hybrid canonical parity; repair score 5
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
- [ ] `agetty` — inventory
- [x] `bits` — hybrid canonical parity; repair score 3
- [x] `blkdiscard` — hybrid canonical parity; repair score 3
- [ ] `blkid` — inventory
- [x] `blkpr` — hybrid canonical parity; repair score 5
- [ ] `blkzone` — inventory
- [x] `blockdev` — hybrid canonical parity; repair score 5
- [ ] `cal` — inventory
- [ ] `cfdisk` — inventory
- [x] `chcpu` — hybrid canonical parity; repair score 5
- [ ] `chfn` — inventory
- [x] `chmem` — hybrid canonical parity; repair score 5
- [x] `choom` — hybrid canonical parity; repair score 3
- [x] `chrt` — hybrid canonical parity; repair score 5
- [x] `chsh` — hybrid canonical parity; repair score 3
- [x] `col` — hybrid canonical parity; repair score 5
- [x] `colcrt` — hybrid canonical parity; repair score 3
- [x] `colrm` — hybrid canonical parity; repair score 3
- [ ] `column` — inventory
- [x] `copyfilerange` — hybrid canonical parity; repair score 3
- [x] `coresched` — hybrid canonical parity; repair score 5
- [x] `ctrlaltdel` — hybrid canonical parity; repair score 3
- [x] `delpart` — hybrid canonical parity; repair score 5
- [ ] `dmesg` — inventory
- [ ] `eject` — inventory
- [ ] `enosys` — inventory
- [x] `exch` — hybrid canonical parity; repair score 3
- [x] `fadvise` — hybrid canonical parity; repair score 3
- [x] `fallocate` — hybrid canonical parity; repair score 5
- [x] `fdformat` — hybrid canonical parity; repair score 3
- [ ] `fdisk` — inventory
- [x] `fincore` — hybrid canonical parity; repair score 5
- [x] `findfs` — hybrid canonical parity; repair score 5
- [ ] `findmnt` — inventory
- [x] `flock` — hybrid canonical parity; repair score 5
- [ ] `fsck` — inventory
- [ ] `fsck.cramfs` — inventory
- [ ] `fsck.minix` — inventory
- [x] `fsfreeze` — hybrid canonical parity; repair score 5
- [ ] `fstrim` — inventory
- [x] `getino` — hybrid canonical parity; repair score 3
- [x] `getopt` — hybrid canonical parity; repair score 5
- [ ] `hardlink` — inventory
- [ ] `hexdump` — inventory
- [ ] `hwclock` — inventory
- [ ] `i386` — inventory
- [ ] `ia64` — inventory
- [x] `ionice` — hybrid canonical parity; repair score 3
- [x] `ipcmk` — hybrid canonical parity; repair score 3
- [ ] `ipcrm` — inventory
- [ ] `ipcs` — inventory
- [ ] `irqtop` — inventory
- [x] `isosize` — hybrid canonical parity; repair score 5
- [ ] `kill` — inventory
- [ ] `last` — inventory
- [ ] `lastb` — inventory
- [x] `lastlog2` — hybrid canonical parity; repair score 3
- [x] `ldattach` — hybrid canonical parity; repair score 5
- [x] `line` — hybrid canonical parity; repair score 3
- [ ] `linux32` — inventory
- [ ] `linux64` — inventory
- [ ] `logger` — inventory
- [ ] `login` — inventory
- [x] `look` — hybrid canonical parity; repair score 3
- [ ] `losetup` — inventory
- [ ] `lsblk` — inventory
- [ ] `lsclocks` — inventory
- [ ] `lscpu` — inventory
- [ ] `lsfd` — inventory
- [ ] `lsipc` — inventory
- [x] `lsirq` — hybrid canonical parity; repair score 3
- [ ] `lslocks` — inventory
- [ ] `lslogins` — inventory
- [ ] `lsmem` — inventory
- [ ] `lsns` — inventory
- [x] `mcookie` — hybrid canonical parity; repair score 3
- [x] `mesg` — hybrid canonical parity; repair score 5
- [ ] `mips` — inventory
- [ ] `mips32` — inventory
- [ ] `mips64` — inventory
- [x] `mkfs` — hybrid canonical parity; repair score 5
- [x] `mkfs.bfs` — hybrid canonical parity; repair score 5
- [ ] `mkfs.cramfs` — inventory
- [ ] `mkfs.minix` — inventory
- [ ] `mkswap` — inventory
- [ ] `more` — inventory
- [ ] `mount` — inventory
- [x] `mountpoint` — hybrid canonical parity; repair score 3
- [x] `namei` — hybrid canonical parity; repair score 5
- [x] `newgrp` — hybrid canonical parity; repair score 3
- [x] `nologin` — hybrid canonical parity; repair score 5
- [ ] `nsenter` — inventory
- [ ] `parisc` — inventory
- [ ] `parisc32` — inventory
- [ ] `parisc64` — inventory
- [ ] `partx` — inventory
- [ ] `pg` — inventory
- [x] `pipesz` — hybrid canonical parity; repair score 3
- [x] `pivot_root` — hybrid canonical parity; repair score 5
- [ ] `ppc` — inventory
- [ ] `ppc32` — inventory
- [ ] `ppc64` — inventory
- [ ] `prlimit` — inventory
- [x] `raw` — hybrid canonical parity; repair score 3
- [x] `readprofile` — hybrid canonical parity; repair score 5
- [x] `rename` — hybrid canonical parity; repair score 3
- [x] `renice` — hybrid canonical parity; repair score 3
- [x] `resizepart` — hybrid canonical parity; repair score 5
- [x] `rev` — hybrid canonical parity; repair score 3
- [x] `rfkill` — hybrid canonical parity; repair score 5
- [ ] `rtcwake` — inventory
- [ ] `runuser` — inventory
- [ ] `s390` — inventory
- [ ] `s390x` — inventory
- [ ] `script` — inventory
- [x] `scriptlive` — hybrid canonical parity; repair score 3
- [x] `scriptreplay` — hybrid canonical parity; repair score 5
- [ ] `setarch` — inventory
- [x] `setpgid` — hybrid canonical parity; repair score 3
- [ ] `setpriv` — inventory
- [x] `setsid` — hybrid canonical parity; repair score 3
- [ ] `setterm` — inventory
- [ ] `sfdisk` — inventory
- [ ] `sparc` — inventory
- [ ] `sparc32` — inventory
- [ ] `sparc32bash` — inventory
- [ ] `sparc64` — inventory
- [ ] `su` — inventory
- [ ] `sulogin` — inventory
- [x] `swaplabel` — hybrid canonical parity; repair score 3
- [x] `swapoff` — hybrid canonical parity; repair score 3
- [ ] `swapon` — inventory
- [x] `switch_root` — hybrid canonical parity; repair score 3
- [x] `taskset` — hybrid canonical parity; repair score 3
- [x] `tunelp` — hybrid canonical parity; repair score 3
- [x] `uclampset` — hybrid canonical parity; repair score 3
- [ ] `ul` — inventory
- [ ] `umount` — inventory
- [ ] `uname26` — inventory
- [ ] `unshare` — inventory
- [x] `utmpdump` — hybrid canonical parity; repair score 3
- [ ] `uuidd` — inventory
- [x] `uuidgen` — hybrid canonical parity; repair score 3
- [x] `uuidparse` — hybrid canonical parity; repair score 3
- [ ] `vigr` — inventory
- [x] `vipw` — hybrid canonical parity; repair score 3
- [x] `waitpid` — hybrid canonical parity; repair score 3
- [x] `wall` — hybrid canonical parity; repair score 5
- [ ] `wdctl` — inventory
- [x] `whereis` — hybrid canonical parity; repair score 5
- [ ] `wipefs` — inventory
- [x] `write` — hybrid canonical parity; repair score 5
- [ ] `x86_64` — inventory
- [ ] `zramctl` — inventory

**Total: 263 applet names.**

<!-- END APPLET INVENTORY -->

