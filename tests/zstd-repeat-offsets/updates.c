/* SPDX-License-Identifier: 0BSD */
#include "zstd_compress_internal.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern Repcodes_t rust_update(U32, U32, U32, U32, U32);
extern Repcodes_t rust_new(U32, U32, U32, U32, U32);

int main(void)
{
    const U32 values[] = {0, 1, 2, 3, 4, 7, 8, 15, 16, 255, 256,
                          65535, 65536, UINT32_MAX - 2, UINT32_MAX - 1, UINT32_MAX};
    const U32 offsets[] = {1, 2, 3, 4, 5, 7, 8, 15, 16, 255, 256,
                           65535, 65536, UINT32_MAX - 2, UINT32_MAX - 1, UINT32_MAX};
    unsigned total = 0;
    for (size_t a = 0; a < 16; ++a)
        for (size_t b = 0; b < 16; ++b)
            for (size_t c = 0; c < 16; ++c)
                for (size_t i = 0; i < 16; ++i)
                    for (U32 ll0 = 0; ll0 <= 1; ++ll0) {
                        U32 rep[] = {values[a], values[b], values[c]};
                        Repcodes_t expected = ZSTD_newRep(rep, offsets[i], ll0);
                        Repcodes_t created = rust_new(rep[0], rep[1], rep[2], offsets[i], ll0);
                        Repcodes_t updated = rust_update(rep[0], rep[1], rep[2], offsets[i], ll0);
                        ZSTD_updateRep(rep, offsets[i], ll0);
                        if (memcmp(rep, updated.rep, sizeof rep) ||
                            memcmp(expected.rep, created.rep, sizeof rep))
                            return 1;
                        ++total;
                    }
    printf("%u\n", total);
    return 0;
}
