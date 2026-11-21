/* SPDX-License-Identifier: GPL-3.0-or-later */

#include <string.h>

extern int rustbox_less_main(int argc, char *argv[]);
extern int rustbox_lessecho_main(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	const char *name = strrchr(argv[0], '/');
	name = name == NULL ? argv[0] : name + 1;
	if (strcmp(name, "lessecho") == 0)
		return rustbox_lessecho_main(argc, argv);
	return rustbox_less_main(argc, argv);
}
