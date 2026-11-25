/* SPDX-License-Identifier: curl */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

extern int checkmonth(const char *, size_t);
extern int rustbox_test_month(uint8_t, uint8_t, uint8_t);

int main(void)
{
    unsigned accepted = 0;
    for (unsigned n = 0; n < (1u << 24); ++n) {
        uint8_t word[3] = {n >> 16, n >> 8, n};
        int expected = checkmonth((const char *)word, 3);
        if (rustbox_test_month(word[0], word[1], word[2]) != expected) {
            fprintf(stderr, "month mismatch at %06x\n", n);
            return 1;
        }
        accepted += expected >= 0;
    }
    if (accepted != 12 * 8 || checkmonth(NULL, 0) != -1 ||
        checkmonth(NULL, 1) != -1 || checkmonth(NULL, 2) != -1 ||
        checkmonth(NULL, 4) != -1 || checkmonth(NULL, SIZE_MAX) != -1)
        return 1;
    printf("16777216 words, %u accepted spellings\n", accepted);
    return 0;
}
