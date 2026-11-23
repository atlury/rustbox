/* SPDX-License-Identifier: GPL-3.0-or-later */

#ifndef RUSTBOX_INETUTILS_ENTRY
#error "RUSTBOX_INETUTILS_ENTRY must name one normalized Inetutils entrypoint"
#endif

extern int RUSTBOX_INETUTILS_ENTRY(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	return RUSTBOX_INETUTILS_ENTRY(argc, argv);
}
