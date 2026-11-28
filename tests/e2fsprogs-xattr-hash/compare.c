// SPDX-License-Identifier: LGPL-2.0-only
#include "ext2fs/ext2fs.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef __u32 hash_entry(struct ext2_ext_attr_entry *, void *);
extern hash_entry gcc_unsigned, gcc_signed, clang_unsigned, clang_signed;

struct fixture {
    struct ext2_ext_attr_entry header;
    unsigned char name[256];
};
_Static_assert(offsetof(struct fixture, name) == sizeof(struct ext2_ext_attr_entry), "name offset");

static uint64_t cases;
static uint64_t fingerprint = UINT64_C(14695981039346656037);

static void compare(struct fixture *f, void *value) {
    hash_entry *implementations[][3] = {
        {gcc_unsigned, clang_unsigned, ext2fs_ext_attr_hash_entry},
        {gcc_signed, clang_signed, ext2fs_ext_attr_hash_entry_signed},
    };
    for (size_t sign = 0; sign < 2; ++sign) {
        __u32 expected = 0;
        for (size_t which = 0; which < 3; ++which) {
            errno = ERANGE;
            __u32 hash = implementations[sign][which](&f->header, value);
            if (errno != ERANGE || (which && hash != expected)) {
                fprintf(stderr, "mismatch at case %" PRIu64 ", compiler %zu, signed %zu\n", cases, which, sign);
                exit(1);
            }
            expected = hash;
        }
        fingerprint = (fingerprint ^ expected) * UINT64_C(1099511628211);
        ++cases;
    }
}

int main(void) {
    struct fixture f = {0};
    __u32 words[33];
    unsigned char *bytes = (unsigned char *)words;
    for (unsigned int pattern = 0; pattern < 4; ++pattern) {
        for (size_t i = 0; i < sizeof(words); ++i)
            bytes[i] = (unsigned char)(i * 29 + pattern * 71);
        for (size_t i = 0; i < sizeof(f.name); ++i)
            f.name[i] = (unsigned char)(pattern == 0 ? i : pattern == 1 ? 255-i : pattern == 2 ? 128 : 0);
        for (unsigned int length = 0; length <= 255; ++length) {
            f.header.e_name_len = length;
            f.header.e_value_inum = 0;
            for (unsigned int size = 0; size <= sizeof(words); ++size) {
                f.header.e_value_size = size;
                compare(&f, size ? words : NULL);
            }
            // Upstream's unsigned round-to-word calculation wraps to zero.
            for (unsigned int n = 0; n < 3; ++n) {
                f.header.e_value_size = UINT32_MAX - n;
                compare(&f, NULL);
            }
            f.header.e_value_inum = 19;
            f.header.e_value_size = 67;
            compare(&f, NULL);
        }
    }
    printf("%" PRIu64 " hashes matched %016" PRIx64 "\n", cases, fingerprint);
    return 0;
}
