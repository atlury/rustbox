/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standalone harness for one translated E2fsprogs program closure. */

#ifndef RUSTBOX_E2FSPROGS_ENTRY
#error "RUSTBOX_E2FSPROGS_ENTRY must name the translated entrypoint"
#endif

extern int RUSTBOX_E2FSPROGS_ENTRY(int, char **);

int
main(int argc, char **argv)
{
	return RUSTBOX_E2FSPROGS_ENTRY(argc, argv);
}
