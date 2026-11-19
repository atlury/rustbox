/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(symbol) extern int rustbox_##symbol##_main(int, char **)
APPLET(cal);
APPLET(dmesg);
APPLET(fsck_minix);
APPLET(hardlink);
APPLET(irqtop);
APPLET(lsipc);
APPLET(more);
APPLET(mount);
APPLET(pg);
APPLET(umount);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(name_, symbol_) \
	if (strcmp(name, name_) == 0) \
		return rustbox_##symbol_##_main(argc, argv)
	SELECT("cal", cal);
	SELECT("dmesg", dmesg);
	SELECT("fsck.minix", fsck_minix);
	SELECT("hardlink", hardlink);
	SELECT("irqtop", irqtop);
	SELECT("lsipc", lsipc);
	SELECT("more", more);
	SELECT("mount", mount);
	SELECT("pg", pg);
	SELECT("umount", umount);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-12") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-12 APPLET [ARGUMENT]...\n", stderr);
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
