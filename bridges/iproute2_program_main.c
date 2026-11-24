/* SPDX-License-Identifier: GPL-2.0-or-later */

#ifndef RUSTBOX_IPROUTE2_ENTRY
#error "RUSTBOX_IPROUTE2_ENTRY must name one normalized IPRoute2 entrypoint"
#endif

extern int RUSTBOX_IPROUTE2_ENTRY(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	return RUSTBOX_IPROUTE2_ENTRY(argc, argv);
}
