/* SPDX-License-Identifier: 0BSD */
#define ZSTD_STATIC_LINKING_ONLY
#include "zstd.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned char input[160000], frame[180000], decoded[160000];

static void fill(unsigned seed)
{
    uint32_t state = seed;
    const size_t distances[] = {1, 4, 8, 37, 64, 127, 512, 31, 7};
    for (size_t i = 0; i < sizeof input; ++i) {
        state = state * 1664525u + 1013904223u;
        size_t distance = distances[(i / 131 + seed) % (sizeof distances / sizeof distances[0])];
        input[i] = i < distance || i % 113 < (seed % 19) + 1
            ? (unsigned char)(state >> 24) : input[i - distance];
    }
}

static int compress_frame(ZSTD_CCtx *ctx, ZSTD_strategy strategy, int target_size)
{
    if (ZSTD_isError(ZSTD_CCtx_reset(ctx, ZSTD_reset_session_and_parameters)) ||
        ZSTD_isError(ZSTD_CCtx_setParameter(ctx, ZSTD_c_strategy, strategy)) ||
        ZSTD_isError(ZSTD_CCtx_setParameter(ctx, ZSTD_c_targetCBlockSize, target_size)))
        return 1;
    size_t n = ZSTD_compress2(ctx, frame, sizeof frame, input, sizeof input);
    if (ZSTD_isError(n) || ZSTD_decompress(decoded, sizeof decoded, frame, n) != sizeof input ||
        memcmp(input, decoded, sizeof input))
        return 1;
    uint32_t size = (uint32_t)n;
    return fwrite(&size, sizeof size, 1, stdout) != 1 || fwrite(frame, 1, n, stdout) != n;
}

int main(int argc, char **argv)
{
    int quick = argc == 2 && strcmp(argv[1], "--memcheck") == 0;
    if (argc != 1 && !quick) return 1;
    ZSTD_CCtx *ctx = ZSTD_createCCtx();
    if (!ctx) return 1;
    int failed = 0;
    for (unsigned seed = 0; seed < (quick ? 1u : 4u) && !failed; ++seed) {
        fill(19 * seed + 3);
        for (int s = quick ? ZSTD_btopt : ZSTD_fast; s <= ZSTD_btultra2 && !failed; ++s)
            for (unsigned t = 0; t < 2 && !failed; ++t)
                failed = compress_frame(ctx, (ZSTD_strategy)s, t ? 2048 : 0);
    }
    ZSTD_freeCCtx(ctx);
    return failed;
}
