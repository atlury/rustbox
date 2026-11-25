/* SPDX-License-Identifier: GPL-2.0-only */
#include "config.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ext2fs.h"
#include "ext2fsP.h"

extern const struct ext2fs_nls_table *canonical_load(int);
static const struct ext2fs_nls_table *oracle, *candidate;
static unsigned long cases;

static void require(int ok, const char *operation)
{
    if (!ok) {
        fprintf(stderr, "Hangul comparison %lu failed in %s\n", cases, operation);
        exit(1);
    }
    ++cases;
}

static void encode(unsigned char *buf, unsigned int value)
{
    buf[0] = 0xe0 | (value >> 12);
    buf[1] = 0x80 | ((value >> 6) & 63);
    buf[2] = 0x80 | (value & 63);
}

static void compare(const unsigned char *input, size_t length,
                    const unsigned char *other, size_t other_length, int expected_equal)
{
    char *pos1 = NULL, *pos2 = NULL;
    int a = oracle->ops->validate(oracle, (char *)input, length, &pos1);
    int b = candidate->ops->validate(candidate, (char *)input, length, &pos2);
    require(a == b && pos1 == pos2, "validate and error position");
    a = oracle->ops->casefold_cmp(oracle, input, length, other, other_length);
    b = candidate->ops->casefold_cmp(candidate, input, length, other, other_length);
    require(a == b && (!expected_equal || a == 0), "casefold comparison");
    for (size_t capacity = 0; capacity <= 14; ++capacity) {
        unsigned char left[24], right[24];
        memset(left, 0xa5, sizeof(left));
        memcpy(right, left, sizeof(right));
        a = oracle->ops->casefold(oracle, input, length, left + 2, capacity);
        b = candidate->ops->casefold(candidate, input, length, right + 2, capacity);
        require(a == b && !memcmp(left, right, sizeof(left)), "casefold bytes, guards and status");
        if (expected_equal && capacity > other_length)
            require(a == (int)other_length && !memcmp(left + 2, other, other_length + 1),
                    "decomposed Unicode spelling");
    }
}

int main(int argc, char **argv)
{
    unsigned int step = argc == 2 && !strcmp(argv[1], "--memcheck") ? 37 : 1;
    oracle = canonical_load(EXT4_ENC_UTF8_12_1);
    candidate = ext2fs_load_nls_table(EXT4_ENC_UTF8_12_1);
    require(oracle && candidate && oracle != candidate, "independent NLS tables");

    for (unsigned int index = 0; index < 11172; index += step) {
        unsigned char syllable[9] = {0}, decomposed[16] = {0};
        encode(syllable, 0xac00 + index);
        encode(decomposed, 0x1100 + index / 588);
        encode(decomposed + 3, 0x1161 + index % 588 / 28);
        size_t n = 6;
        if (index % 28) {
            encode(decomposed + n, 0x11a7 + index % 28);
            n += 3;
        }
        compare(syllable, 3, decomposed, n, 1);
        // A combining mark and a second syllable exercise the cursor's saved positions.
        syllable[3] = 0xcc; syllable[4] = 0x81;
        memcpy(syllable + 5, syllable, 3);
        compare(syllable, 8, decomposed, n, 0);
    }
    unsigned char invalid[][5] = {{0x80}, {0xea,0xb0}, {0xea,0xb0,0xff},
                                   {0xea,0xb0,0x80,0}, {0xed,0xa0,0x80}, {0xff}, {0}};
    for (size_t i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i)
        for (size_t n = 0; n <= 4; ++n)
            compare(invalid[i], n, invalid[0], 1, 0);
    printf("%lu canonical Hangul comparisons passed\n", cases);
    return 0;
}
