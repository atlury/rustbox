/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(name) extern int rustbox_##name##_main(int, char **)
APPLET(coresched);
APPLET(chcpu);
APPLET(namei);
APPLET(wall);
APPLET(readprofile);
APPLET(scriptreplay);
APPLET(blkpr);
APPLET(ldattach);
APPLET(blockdev);
APPLET(flock);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(applet) \
	if (strcmp(name, #applet) == 0) \
		return rustbox_##applet##_main(argc, argv)
	SELECT(coresched);
	SELECT(chcpu);
	SELECT(namei);
	SELECT(wall);
	SELECT(readprofile);
	SELECT(scriptreplay);
	SELECT(blkpr);
	SELECT(ldattach);
	SELECT(blockdev);
	SELECT(flock);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-06") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-06 APPLET [ARGUMENT]...\n", stderr);
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
