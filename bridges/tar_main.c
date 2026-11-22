/* SPDX-License-Identifier: 0BSD */

#ifndef RUSTBOX_ENTRY
# error "RUSTBOX_ENTRY must name the translated GNU tar entrypoint"
#endif

extern int RUSTBOX_ENTRY (int, char **);

int
main (int argc, char **argv)
{
  return RUSTBOX_ENTRY (argc, argv);
}
