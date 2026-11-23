/* SPDX-License-Identifier: 0BSD */

extern int rustbox_kmod_main(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	return rustbox_kmod_main(argc, argv);
}
