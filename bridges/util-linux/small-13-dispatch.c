/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(symbol) extern int rustbox_##symbol##_main(int, char **)
APPLET(chfn);
APPLET(fsck);
APPLET(hexdump);
APPLET(hwclock);
APPLET(lscpu);
APPLET(lslogins);
APPLET(lsns);
APPLET(script);
APPLET(swapon);
APPLET(unshare);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(name_, symbol_) \
	if (strcmp(name, name_) == 0) \
		return rustbox_##symbol_##_main(argc, argv)
	SELECT("chfn", chfn);
	SELECT("fsck", fsck);
	SELECT("hexdump", hexdump);
	SELECT("hwclock", hwclock);
	SELECT("lscpu", lscpu);
	SELECT("lslogins", lslogins);
	SELECT("lsns", lsns);
	SELECT("script", script);
	SELECT("swapon", swapon);
	SELECT("unshare", unshare);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-13") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-13 APPLET [ARGUMENT]...\n", stderr);
			return 127;
		}
		argc--;
		argv++;
		name = basename(argv[0]);
		program_invocation_name = argv[0];
		program_invocation_short_name = basename(argv[0]);
	}
	return dispatch(name, argc, argv);
}
