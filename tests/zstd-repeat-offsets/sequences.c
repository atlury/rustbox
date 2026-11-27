/* SPDX-License-Identifier: 0BSD */
#define ZSTD_STATIC_LINKING_ONLY
#include "zstd.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned char source[16384], literals[16384], frame[32768], decoded[16384];

static int run(unsigned seed, unsigned mode, ZSTD_paramSwitch_e resolution)
{
    static const unsigned distances[] = {1, 4, 8, 7, 4, 3, 9, 16, 15, 8, 1};
    ZSTD_Sequence seq[100] = {{0}};
    size_t pos = 0, lit = 0, count = 0;
    for (unsigned i = 0; i < 96; ++i) {
        unsigned length = i == 0 ? 48 : (i + seed) % 3;
        unsigned match = 40 + (i + seed) % 17;
        unsigned offset = distances[(i + seed) % (sizeof distances / sizeof distances[0])];
        for (unsigned j = 0; j < length; ++j)
            literals[lit++] = source[pos++] = (unsigned char)(31 * i + 17 * j + seed);
        seq[count++] = (ZSTD_Sequence){.litLength = length, .offset = offset, .matchLength = match};
        for (unsigned j = 0; j < match; ++j, ++pos)
            source[pos] = source[pos - offset];
        if (mode && (i == 47 || i == 95))
            seq[count++] = (ZSTD_Sequence){0};
    }

    ZSTD_CCtx *ctx = ZSTD_createCCtx();
    if (!ctx) return 1;
    int ok = 0;
    if (ZSTD_isError(ZSTD_CCtx_setParameter(ctx, ZSTD_c_blockDelimiters,
                                           mode ? ZSTD_sf_explicitBlockDelimiters : ZSTD_sf_noBlockDelimiters)) ||
        ZSTD_isError(ZSTD_CCtx_setParameter(ctx, ZSTD_c_repcodeResolution, resolution)) ||
        ZSTD_isError(ZSTD_CCtx_setParameter(ctx, ZSTD_c_validateSequences, mode != 2)))
        goto done;
    size_t n = mode == 2
        ? ZSTD_compressSequencesAndLiterals(ctx, frame, sizeof frame, seq, count, literals, lit, sizeof literals, pos)
        : ZSTD_compressSequences(ctx, frame, sizeof frame, seq, count, source, pos);
    if (ZSTD_isError(n)) {
        fprintf(stderr, "seed %u mode %u: %s\n", seed, mode, ZSTD_getErrorName(n));
        goto done;
    }
    if (ZSTD_decompress(decoded, sizeof decoded, frame, n) != pos || memcmp(decoded, source, pos))
        goto done;
    uint32_t size = (uint32_t)n;
    ok = fwrite(&size, sizeof size, 1, stdout) == 1 && fwrite(frame, 1, n, stdout) == n;
done:
    ZSTD_freeCCtx(ctx);
    return !ok;
}

int main(void)
{
    const ZSTD_paramSwitch_e modes[] = {ZSTD_ps_auto, ZSTD_ps_enable, ZSTD_ps_disable};
    for (unsigned seed = 0; seed < 8; ++seed)
        for (unsigned mode = 0; mode < 3; ++mode)
            for (unsigned i = 0; i < 3; ++i)
                if (run(seed, mode, modes[i])) return 1;
    return 0;
}
