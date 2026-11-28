/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Expose the original file parser for the standalone Rust ABI test. */
#include "rt_names.c"
int rustbox_group_read(FILE *file, int *id, char *name);
int rustbox_group_read(FILE *file, int *id, char *name)
{
    return fread_id_name(file, id, name);
}
