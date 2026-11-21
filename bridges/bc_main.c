/* SPDX-License-Identifier: GPL-3.0-or-later */

#ifndef RUSTBOX_ENTRY
# error "RUSTBOX_ENTRY must name one translated GNU bc entrypoint"
#endif

extern int RUSTBOX_ENTRY(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	return RUSTBOX_ENTRY(argc, argv);
}
