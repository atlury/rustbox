/* SPDX-License-Identifier: 0BSD */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lorem.h"

static unsigned cases;

static void check(size_t size, unsigned seed, int mode)
{
    unsigned char storage[16 + 8191 + 16];
    unsigned char *buffer = storage + 16;
    memset(storage, 0xa5, sizeof(storage));
    size_t length;
    if (mode == 4) {
        LOREM_genBuffer(buffer, size, seed);
        length = size;
    } else {
        length = LOREM_genBlock(buffer, size, seed, mode & 1, (mode >> 1) & 1);
    }
    if (length > size) abort();
    for (size_t i = 0; i < 16; ++i)
        if (storage[i] != 0xa5 || buffer[size + i] != 0xa5) abort();
    uint32_t count = (uint32_t)length;
    if (fwrite(&count, sizeof(count), 1, stdout) != 1 ||
        fwrite(buffer, 1, size, stdout) != size) abort();
    ++cases;
}

int main(void)
{
    const unsigned seeds[] = {0, 1, 2, 23, 0x1100, 0x7fffffffU, 0xffffffffU};
    const size_t larger[] = {127, 128, 255, 256, 511, 512, 1023, 1024, 4096, 8191};
    for (size_t s = 0; s < sizeof(seeds)/sizeof(*seeds); ++s) {
        for (int mode = 0; mode <= 4; ++mode) {
            for (size_t size = 0; size <= 64; ++size)
                check(size, seeds[s], mode);
            for (size_t i = 0; i < sizeof(larger)/sizeof(*larger); ++i)
                check(larger[i], seeds[s], mode);
        }
    }
    fprintf(stderr, "%u\n", cases);
    return 0;
}
