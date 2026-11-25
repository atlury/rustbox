// SPDX-License-Identifier: GPL-2.0-only
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef long hash_fn(int, const char *, int, const uint32_t *, uint32_t *, uint32_t *);
extern hash_fn reference_dirhash, ext2fs_dirhash;

static uint32_t state = 0x8d03112f;
static unsigned cases;

static uint32_t next_word(void)
{
    state ^= state << 13;
    state ^= state >> 17;
    state ^= state << 5;
    return state;
}

static void compare(int version, const char *bytes, int len, const uint32_t *seed)
{
    for (int mode = 0; mode < 3; ++mode) {
        uint32_t ref[2] = {0x12fedead, 0x9876fabc};
        uint32_t got[2];
        memcpy(got, ref, sizeof(ref));
        // Exercise a separate minor output, an omitted one, and aliased outputs.
        uint32_t *ref_minor = mode == 0 ? ref + 1 : mode == 1 ? NULL : ref;
        uint32_t *got_minor = mode == 0 ? got + 1 : mode == 1 ? NULL : got;
        long a = reference_dirhash(version, bytes, len, seed, ref, ref_minor);
        long b = ext2fs_dirhash(version, bytes, len, seed, got, got_minor);
        if (a != b || memcmp(got, ref, sizeof(ref)) != 0) {
            fprintf(stderr, "directory hash mismatch in case %u, version %d, length %d, mode %d\n",
                    cases, version, len, mode);
            exit(1);
        }
        ++cases;
    }
}

int main(int argc, char **argv)
{
    int quick = argc == 2 && strcmp(argv[1], "--memcheck") == 0;
    if (argc != 1 && !quick) return 2;
    // Leave room for the canonical C loop's final pointer increment and each alignment.
    char input[4096 + 64];
    const uint32_t zero[4] = {0};
    for (int pattern = 0; pattern < 4; ++pattern) {
        for (size_t i = 0; i < sizeof(input); ++i)
            input[i] = pattern == 0 ? 0 : pattern == 1 ? (char)0xff :
                       pattern == 2 ? (char)i : (char)next_word();
        for (int len = 0; len <= 256; ++len) {
            if (quick && len > 1 && len % 16 != 15 && len % 16 != 0 && len % 16 != 1) continue;
            uint32_t seed[4] = {next_word(), next_word(), next_word(), next_word()};
            for (int version = -1; version <= 6; ++version) {
                const char *name = len == 0 ? NULL : input + (len % 32);
                compare(version, name, len, NULL);
                compare(version, name, len, zero);
                compare(version, name, len, seed);
            }
        }
    }
    for (int trial = 0; trial < (quick ? 12 : 8192); ++trial) {
        uint32_t seed[4] = {next_word(), next_word(), next_word(), next_word()};
        int len = (int)(next_word() % 4097);
        int offset = (int)(next_word() % 32);
        compare(trial % 6, input + offset, len, seed);
    }
    printf("%u canonical directory hash comparisons passed\n", cases);
    return 0;
}
