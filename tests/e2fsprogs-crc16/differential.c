/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "crc16.h"

extern crc16_t canonical_ext2fs_crc16(crc16_t, const void *, unsigned int);

static unsigned long cases;

static void check(unsigned seed, const unsigned char *bytes, unsigned len)
{
    unsigned expected = canonical_ext2fs_crc16(seed, bytes, len);
    unsigned actual = ext2fs_crc16(seed, bytes, len);
    if (actual != expected) {
        fprintf(stderr, "CRC mismatch in case %lu, seed %x length %u: %x != %x\n",
                cases, seed, len, actual, expected);
        exit(1);
    }
    ++cases;
}

int main(void)
{
    unsigned char bytes[4096];
    uint32_t state = 1;
    for (unsigned i = 0; i < sizeof(bytes); ++i) {
        state = state * UINT32_C(1664525) + UINT32_C(1013904223);
        bytes[i] = state >> 24;
    }
    for (unsigned seed = 0; seed <= UINT16_MAX; ++seed) {
        check(0xabba0000U | seed, NULL, 0);
        for (unsigned value = 0; value <= UINT8_MAX; ++value) {
            unsigned char byte = value;
            check(0xcafe0000U | seed, &byte, 1);
        }
    }
    for (unsigned offset = 0; offset < 32; ++offset) {
        for (unsigned len = 0; len <= sizeof(bytes) - offset; ++len)
            check(~0U, bytes + offset, len);
    }
    unsigned expected = canonical_ext2fs_crc16(~0U, bytes, sizeof(bytes));
    for (unsigned split = 0; split <= sizeof(bytes); ++split) {
        unsigned partial = ext2fs_crc16(~0U, bytes, split);
        if (ext2fs_crc16(partial, bytes + split, sizeof(bytes) - split) != expected)
            return EXIT_FAILURE;
        ++cases;
    }
    printf("%lu CRC comparisons passed\n", cases);
    return EXIT_SUCCESS;
}
