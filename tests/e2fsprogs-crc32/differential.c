/* SPDX-License-Identifier: GPL-2.0-only */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef uint32_t crc_fn(uint32_t, const unsigned char *, size_t);
extern crc_fn ext2fs_crc32c_le, ext2fs_crc32_be, canonical_le, canonical_be;
static unsigned long cases;

static void compare(crc_fn *candidate, crc_fn *canonical, uint32_t seed,
                    const unsigned char *buf, size_t len)
{
    uint32_t actual = candidate(seed, buf, len);
    uint32_t expected = canonical(seed, buf, len);
    if (actual != expected) {
        fprintf(stderr, "case %lu length %zu seed %08x: %08x != %08x\n",
                cases, len, seed, actual, expected);
        exit(1);
    }
    ++cases;
}

static void both(uint32_t seed, const unsigned char *buf, size_t len)
{
    compare(ext2fs_crc32c_le, canonical_le, seed, buf, len);
    compare(ext2fs_crc32_be, canonical_be, seed, buf, len);
}

int main(void)
{
    unsigned char data[8192 + 32];
    uint32_t seed = 0xa5f0c26b;
    for (size_t i = 0; i < sizeof data; ++i) {
        seed = seed * 1664525u + 1013904223u;
        data[i] = seed >> 24;
    }
    both(0, NULL, 0);
    both(UINT32_MAX, NULL, 0);
    for (size_t start = 0; start < 32; ++start) {
        for (size_t len = 0; len <= 256; ++len) {
            for (unsigned bit = 0; bit < 32; ++bit)
                both(UINT32_C(1) << bit, data + start, len);
        }
        for (size_t len = 257; len <= 8192; len += 13) {
            seed = seed * 1664525u + 1013904223u;
            both(seed, data + start, len);
        }
    }
    printf("%lu CRC32 comparisons passed\n", cases);
    return 0;
}
