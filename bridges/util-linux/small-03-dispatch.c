/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(name) extern int rustbox_##name##_main(int, char **)
APPLET(swaplabel);
APPLET(lsirq);
APPLET(newgrp);
APPLET(uuidgen);
APPLET(switch_root);
APPLET(raw);
APPLET(renice);
APPLET(ionice);
APPLET(fdformat);
APPLET(copyfilerange);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(applet) \
	if (strcmp(name, #applet) == 0) \
		return rustbox_##applet##_main(argc, argv)
	SELECT(swaplabel);
	SELECT(lsirq);
	SELECT(newgrp);
	SELECT(uuidgen);
	SELECT(switch_root);
	SELECT(raw);
	SELECT(renice);
	SELECT(ionice);
	SELECT(fdformat);
	SELECT(copyfilerange);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-03") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-03 APPLET [ARGUMENT]...\n", stderr);
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
