/* SPDX-License-Identifier: curl */
#include <stdint.h>
#include <stdio.h>

extern unsigned int canonical(const char *);
extern unsigned int candidate(const uint8_t *);

int main(void)
{
    uint8_t word[9];
    unsigned long tested = 0;
    for (unsigned int mode = 0; mode < 010000; ++mode) {
        for (unsigned int c = 0; c < 3; ++c) {
            unsigned int mask = 0100 >> (3 * c);
            unsigned int special = 04000 >> c;
            word[3*c] = mode & (4*mask) ? 'r' : '-';
            word[3*c+1] = mode & (2*mask) ? 'w' : '-';
            word[3*c+2] = mode & special
                ? (c == 2 ? (mode & mask ? 't' : 'T') : (mode & mask ? 's' : 'S'))
                : (mode & mask ? 'x' : '-');
        }
        if (canonical((const char *)word) != mode || candidate(word) != mode)
            return 1;
        for (unsigned int pos = 0; pos < sizeof(word); ++pos) {
            uint8_t old = word[pos];
            for (unsigned int byte = 0; byte < 256; ++byte) {
                word[pos] = byte;
                if (candidate(word) != canonical((const char *)word)) {
                    fprintf(stderr, "different mode %04o, position %u, byte %u\n", mode, pos, byte);
                    return 1;
                }
                ++tested;
            }
            word[pos] = old;
        }
    }
    printf("%lu comparisons and 4096 known modes\n", tested);
    return 0;
}
