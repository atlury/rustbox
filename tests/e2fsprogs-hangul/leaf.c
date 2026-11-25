/* SPDX-License-Identifier: GPL-2.0-only */
/* The test compiler includes canonical nls_utf8.c before this file. */
extern const unsigned char *rust_leaf(const unsigned char *last, unsigned char *output);

int main(void)
{
    unsigned long cases = 0;
    const int offsets[] = {1, 4, 10, 20};
    for (unsigned int value = 0xac00; value <= 0xd7a3; ++value) {
        for (size_t i = 0; i < sizeof(offsets)/sizeof(offsets[0]); ++i) {
            unsigned char reference[32], actual[32];
            int start = offsets[i];
            memset(reference, 0xa5, sizeof(reference));
            reference[start] = 0xe0 | (value >> 12);
            reference[start + 1] = 0x80 | ((value >> 6) & 63);
            reference[start + 2] = 0x80 | (value & 63);
            memcpy(actual, reference, sizeof(actual));
            if (utf8hangul((const char *)(reference + start), reference + 3) != reference + 3 ||
                rust_leaf(actual + start + 2, actual + 3) != actual + 3 ||
                memcmp(actual, reference, sizeof(reference))) {
                fprintf(stderr, "Hangul leaf mismatch at U+%04x, input offset %d\n", value, start);
                return 1;
            }
            ++cases;
        }
    }
    printf("%lu canonical leaf buffer and alias comparisons passed\n", cases);
    return 0;
}
