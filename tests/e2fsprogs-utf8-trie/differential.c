/* SPDX-License-Identifier: GPL-2.0-only */
#define ext2fs_load_nls_table canonical_load
#define ext2fs_check_encoded_name canonical_validate
#define ext2fs_casefold_cmp canonical_compare
#include "nls_utf8.c"
#undef ext2fs_load_nls_table
#include <stddef.h>
#include <sys/mman.h>

extern const struct ext2fs_nls_table *ext2fs_load_nls_table(int);
extern ptrdiff_t trie_offset(const unsigned char *, size_t, size_t, const unsigned char *, size_t);
static const struct ext2fs_nls_table *oracle, *candidate;
static unsigned long leaves, public_cases;

static size_t encode(unsigned int cp, unsigned char out[5])
{
    if (cp < 128) { out[0] = cp; return 1; }
    size_t length = cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
    for (size_t i = length - 1; i; --i) {
        out[i] = 0x80 | (cp & 63);
        cp >>= 6;
    }
    out[0] = (length == 2 ? 0xc0 : length == 3 ? 0xe0 : 0xf0) | cp;
    return length;
}

static void lookup(const unsigned char *input, size_t n)
{
    const struct utf8data *tables[] = {utf8nfdicfdata, utf8nfdidata};
    for (size_t kind = 0; kind < 2; ++kind) {
        const struct utf8data *data = tables[kind];
        for (size_t i = 0; i < ARRAY_SIZE(utf8nfdicfdata); ++i) {
            if (i && data[i].offset == data[i - 1].offset) continue;
            unsigned char hangul[UTF8HANGULLEAF];
            const unsigned char *leaf = utf8nlookup(data + i, hangul, (const char *)input, n);
            ptrdiff_t c = !leaf ? -1 : leaf == hangul ? -2 : leaf - utf8data;
            ptrdiff_t rust = trie_offset(utf8data, sizeof(utf8data), data[i].offset, input, n);
            if (c != rust) {
                fprintf(stderr, "leaf %lu, root %u, length %zu: C %td Rust %td\n",
                        leaves, data[i].offset, n, c, rust);
                exit(1);
            }
            ++leaves;
        }
    }
}

static void interfaces(unsigned char *input, size_t n)
{
    unsigned char left[72], right[72];
    memset(left, 0xa5, sizeof(left));
    memcpy(right, left, sizeof(right));
    char *p = NULL, *q = NULL;
    int a = oracle->ops->validate(oracle, (char *)input, n, &p);
    int b = candidate->ops->validate(candidate, (char *)input, n, &q);
    int x = oracle->ops->casefold(oracle, input, n, left + 2, 64);
    int y = candidate->ops->casefold(candidate, input, n, right + 2, 64);
    if (a != b || p != q || x != y || memcmp(left, right, sizeof(left))) {
        fprintf(stderr, "NLS interface case %lu differed at length %zu\n", public_cases, n);
        exit(1);
    }
    ++public_cases;
}

int main(int argc, char **argv)
{
    oracle = canonical_load(EXT4_ENC_UTF8_12_1);
    candidate = ext2fs_load_nls_table(EXT4_ENC_UTF8_12_1);
    if (!oracle || !candidate || oracle == candidate) return 1;
    unsigned step = argc == 2 && !strcmp(argv[1], "--memcheck") ? 251 : 1;
    for (unsigned cp = 0; cp <= 0x10ffff; cp += step) {
        unsigned char input[5] = {0};
        size_t n = encode(cp, input);
        lookup(input, n);
        interfaces(input, n);
    }
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    unsigned char *base = mmap(NULL, page * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (base == MAP_FAILED || mprotect(base + page, page, PROT_NONE)) return 1;
    /* Place each prefix immediately before the inaccessible page. */
    static const unsigned char sequences[][4] = {
        {0xc2,0x80}, {0xe0,0xa0,0x80}, {0xea,0xb0,0x80}, {0xf4,0x8f,0xbf,0xbf},
        {0x80}, {0xff}, {0xc0,0xaf}, {0xed,0xa0,0x80}, {0xf4,0x90,0x80,0x80}, {0}
    };
    for (size_t i = 0; i < ARRAY_SIZE(sequences); ++i) {
        for (size_t n = 0; n <= 4; ++n) {
            unsigned char *input = base + page - n;
            if (n) memcpy(input, sequences[i], n);
            lookup(input, n);
            interfaces(input, n);
        }
    }
    munmap(base, page * 2);
    printf("%lu trie leaf selections and %lu public NLS cases matched canonical E2fsprogs\n",
           leaves, public_cases);
    return 0;
}
