/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(symbol) extern int rustbox_##symbol##_main(int, char **)
APPLET(agetty);
APPLET(cfdisk);
APPLET(fdisk);
APPLET(findmnt);
APPLET(login);
APPLET(lsblk);
APPLET(lsfd);
APPLET(runuser);
APPLET(sfdisk);
APPLET(su);
APPLET(sulogin);
APPLET(vigr);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(name_, symbol_) \
	if (strcmp(name, name_) == 0) \
		return rustbox_##symbol_##_main(argc, argv)
	SELECT("agetty", agetty);
	SELECT("cfdisk", cfdisk);
	SELECT("fdisk", fdisk);
	SELECT("findmnt", findmnt);
	SELECT("login", login);
	SELECT("lsblk", lsblk);
	SELECT("lsfd", lsfd);
	SELECT("runuser", runuser);
	SELECT("sfdisk", sfdisk);
	SELECT("su", su);
	SELECT("sulogin", sulogin);
	SELECT("vigr", vigr);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-14") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-14 APPLET [ARGUMENT]...\n", stderr);
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
