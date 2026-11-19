/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;

#define APPLET(symbol) extern int rustbox_##symbol##_main(int, char **)
APPLET(mkfs_bfs);
APPLET(write);
APPLET(getopt);
APPLET(fallocate);
APPLET(chrt);
APPLET(fincore);
APPLET(whereis);
APPLET(col);
APPLET(chmem);
APPLET(rfkill);

static int dispatch(const char *name, int argc, char **argv)
{
#define SELECT(name_, symbol_) \
	if (strcmp(name, name_) == 0) \
		return rustbox_##symbol_##_main(argc, argv)
	SELECT("mkfs.bfs", mkfs_bfs);
	SELECT("write", write);
	SELECT("getopt", getopt);
	SELECT("fallocate", fallocate);
	SELECT("chrt", chrt);
	SELECT("fincore", fincore);
	SELECT("whereis", whereis);
	SELECT("col", col);
	SELECT("chmem", chmem);
	SELECT("rfkill", rfkill);
#undef SELECT
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-07") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-07 APPLET [ARGUMENT]...\n", stderr);
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
