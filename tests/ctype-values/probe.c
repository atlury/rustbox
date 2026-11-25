/* SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern int rust_classify(size_t, uint8_t);
static const unsigned short masks[] = {
    _ISupper, _ISlower, _ISalpha, _ISdigit, _ISxdigit, _ISspace,
    _ISprint, _ISgraph, _ISblank, _IScntrl, _ISpunct, _ISalnum
};

int main(int argc, char **argv) {
    static const int errors[] = {0, EINVAL, INT_MIN, INT_MAX};
    for (int n = 1; n < argc; ++n) {
        locale_t locale = newlocale(LC_CTYPE_MASK, argv[n], (locale_t)0);
        if (!locale) return 2;
        locale_t previous = uselocale(locale);
        if (!previous) return 3;
        for (unsigned int b = 0; b <= UINT8_MAX; ++b) {
            for (size_t i = 0; i < sizeof masks / sizeof masks[0]; ++i) {
                int sentinel = errors[(b + i) % (sizeof errors / sizeof errors[0])];
                errno = sentinel;
                int expected = (*__ctype_b_loc())[b] & masks[i];
                int seen = rust_classify(i, b);
                if (seen != expected || errno != sentinel) {
                    fprintf(stderr, "%s byte %u mask %zu canonical %d rust %d errno %d\n",
                            argv[n], b, i, expected, seen, errno);
                    return 4;
                }
                if (fwrite(&seen, sizeof seen, 1, stdout) != 1) return 5;
            }
        }
        if (!uselocale(previous)) return 6;
        freelocale(locale);
    }
    return fflush(stdout) != 0;
}
