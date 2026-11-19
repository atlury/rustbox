/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(symbol) extern int rustbox_##symbol##_main(int, char **)
APPLET(blkid);
APPLET(column);
APPLET(eject);
APPLET(logger);
APPLET(losetup);
APPLET(nsenter);
APPLET(partx);
APPLET(setpriv);
APPLET(wipefs);
APPLET(zramctl);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(name_, symbol_) \
	if (strcmp(name, name_) == 0) \
		return rustbox_##symbol_##_main(argc, argv)
	SELECT("blkid", blkid);
	SELECT("column", column);
	SELECT("eject", eject);
	SELECT("logger", logger);
	SELECT("losetup", losetup);
	SELECT("nsenter", nsenter);
	SELECT("partx", partx);
	SELECT("setpriv", setpriv);
	SELECT("wipefs", wipefs);
	SELECT("zramctl", zramctl);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-11") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-11 APPLET [ARGUMENT]...\n", stderr);
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
