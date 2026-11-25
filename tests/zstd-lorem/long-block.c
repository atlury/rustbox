/* SPDX-License-Identifier: 0BSD */
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lorem.h"

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "assert-size") == 0) {
        (void)LOREM_genBlock(NULL, INT_MAX, 1, 0, 0);
        return 1;
    }
    if (LOREM_genBlock(NULL, 0, 0, -1, -7) != 0) return 1;
    LOREM_genBuffer(NULL, 0, 0);
    const size_t size = 10000000;
    unsigned char *bytes = malloc(size);
    if (!bytes) return 1;
    /* The caller has not initialized this storage. Only the returned prefix is readable. */
    size_t written = LOREM_genBlock(bytes, size, 42, -1, 0);
    if (!written || written >= size || fwrite(bytes, 1, written, stdout) != written) return 1;
    written = LOREM_genBlock(bytes, size, 0, -1, -7);
    if (written != size || fwrite(bytes, 1, size, stdout) != size) return 1;
    free(bytes);
    return 0;
}
