/* SPDX-License-Identifier: 0BSD */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

#ifdef CANONICAL
static int read_errno(void) { return errno; }
static void write_errno(int value) { errno = value; }
#else
extern int read_errno(void);
extern void write_errno(int);
#endif

enum { workers = 4, rounds = 16 };
static pthread_barrier_t barrier;
static _Thread_local volatile sig_atomic_t handled;

static void signal_access(int sig)
{
    int saved = read_errno();
    if (sig == SIGUSR1 && saved == EAGAIN) {
        write_errno(EINTR);
        handled = errno == EINTR;
    }
    write_errno(saved);
}

static void *worker(void *arg)
{
    intptr_t id = (intptr_t)arg;
    int failed = 0;
    const int endpoints[] = {INT_MIN, -1, 0, INT_MAX};
    for (int round = 0; round < rounds; ++round) {
        int value = endpoints[(round + id) % 4];
        errno = value;
        pthread_barrier_wait(&barrier);
        failed |= read_errno() != value;
        write_errno((int)id + 256 * round);
        pthread_barrier_wait(&barrier);
        failed |= errno != (int)id + 256 * round;
        failed |= close(-1) != -1 || read_errno() != EBADF;
        write_errno(EAGAIN);
        handled = 0;
        failed |= raise(SIGUSR1) != 0 || !handled || read_errno() != EAGAIN;
    }
    return (void *)(intptr_t)failed;
}

int main(void)
{
    struct sigaction action = {0};
    action.sa_handler = signal_access;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGUSR1, &action, NULL) || pthread_barrier_init(&barrier, NULL, workers))
        return 2;
    pthread_t threads[workers];
    for (intptr_t i = 0; i < workers; ++i)
        if (pthread_create(&threads[i], NULL, worker, (void *)i))
            return 3;
    for (int i = 0; i < workers; ++i) {
        void *failed;
        if (pthread_join(threads[i], &failed) || failed)
            return 4;
    }
    if (pthread_barrier_destroy(&barrier))
        return 5;
    puts("4 threads, 64 errno and signal rounds");
    return 0;
}
