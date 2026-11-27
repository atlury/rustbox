/* SPDX-License-Identifier: 0BSD */
#include "zstd_compress.c"
#include <stdio.h>

extern U32 rust_repeat_offset(U32 offset, U32 a, U32 b, U32 c, U32 ll0);

int main(void)
{
    const U32 values[] = {0, 1, 2, 3, 4, 7, 8, 15, 16, 255, 256,
                          65535, 65536, UINT32_MAX - 2, UINT32_MAX - 1, UINT32_MAX};
    unsigned total = 0;
    for (size_t a = 0; a < 16; ++a)
        for (size_t b = 0; b < 16; ++b)
            for (size_t c = 0; c < 16; ++c) {
                const U32 rep[] = {values[a], values[b], values[c]};
                for (size_t i = 0; i < 16; ++i)
                    for (U32 ll0 = 0; ll0 <= 1; ++ll0) {
                        U32 wanted = ZSTD_finalizeOffBase(values[i], rep, ll0);
                        if (rust_repeat_offset(values[i], rep[0], rep[1], rep[2], ll0) != wanted)
                            return 1;
                        ++total;
                    }
            }
    printf("%u\n", total);
    return 0;
}
