/* SPDX-License-Identifier: 0BSD */
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <locale.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern int rust_classify(size_t, uint8_t);
enum { lanes = 4, rounds = 32 };
static const char *names[lanes] = {"C", "fr_FR.iso88591", "C.utf8", "sv_SE.iso88591"};
static const unsigned short masks[] = {
    _ISupper, _ISlower, _ISalpha, _ISdigit, _ISxdigit, _ISspace,
    _ISprint, _ISgraph, _ISblank, _IScntrl, _ISpunct, _ISalnum
};
static locale_t locales[lanes];
static pthread_barrier_t ready;
struct result { unsigned lane, mismatches, extended_alpha, comparisons; };

static void *compare(void *arg) {
    struct result *r = arg;
    locale_t initial = uselocale((locale_t)0);
    if (!initial) abort();
    for (unsigned round = 0; round < rounds; ++round) {
        if (!uselocale(locales[(r->lane + round) % lanes])) abort();
        int status = pthread_barrier_wait(&ready);
        if (status && status != PTHREAD_BARRIER_SERIAL_THREAD) abort();
        for (unsigned b = 0; b < 256; ++b) {
            for (unsigned i = 0; i < sizeof masks / sizeof masks[0]; ++i) {
                int saved = (int)((r->lane + 1) * 1000 + round);
                errno = saved;
                int expected = (*__ctype_b_loc())[b] & masks[i];
                int actual = rust_classify(i, b);
                if (actual != expected || errno != saved) ++r->mismatches;
                if (i == 2 && b >= 128 && actual) ++r->extended_alpha;
                ++r->comparisons;
            }
        }
    }
    if (!uselocale(initial)) abort();
    return NULL;
}

int main(void) {
    pthread_t threads[lanes];
    struct result work[lanes] = {0};
    for (unsigned i = 0; i < lanes; ++i) {
        locales[i] = newlocale(LC_CTYPE_MASK, names[i], (locale_t)0);
        if (!locales[i]) return 2;
    }
    if (pthread_barrier_init(&ready, NULL, lanes)) return 3;
    for (unsigned i = 0; i < lanes; ++i) {
        work[i].lane = i;
        if (pthread_create(&threads[i], NULL, compare, &work[i])) abort();
    }
    for (unsigned i = 0; i < lanes; ++i) {
        if (pthread_join(threads[i], NULL)) abort();
        if (work[i].mismatches || !work[i].extended_alpha ||
            work[i].comparisons != rounds * 256 * 12 ||
            work[i].extended_alpha != work[0].extended_alpha) return 4;
        printf("%u %u %u\n", i, work[i].comparisons, work[i].extended_alpha);
    }
    if (pthread_barrier_destroy(&ready)) return 5;
    for (unsigned i = 0; i < lanes; ++i) freelocale(locales[i]);
    return 0;
}
