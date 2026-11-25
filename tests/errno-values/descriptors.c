/* SPDX-License-Identifier: 0BSD */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

extern int fd_safer(int);
extern int pipe_safer(int [2]);
extern void *rpl_reallocarray(void *, size_t, size_t);

int main(void)
{
    const int states[] = {INT_MIN, -7, 0, EACCES, INT_MAX};
    for (size_t i = 0; i < sizeof states / sizeof *states; ++i) {
        errno = states[i];
        if (fd_safer(-1) != -1 || errno != states[i])
            return 1;
        close(STDIN_FILENO);
        errno = states[i];
        if (fd_safer(STDIN_FILENO) != -1 || errno != EBADF)
            return 2;
        if (open("/dev/null", O_RDONLY) != STDIN_FILENO)
            return 3;
        errno = states[i];
        int safe = fd_safer(STDIN_FILENO);
        if (safe < 3 || errno != states[i])
            return 4;
        if (fcntl(STDIN_FILENO, F_GETFD) != -1 || errno != EBADF || close(safe))
            return 5;
        int fds[2];
        if (pipe_safer(fds) || fds[0] < 3 || fds[1] < 3)
            return 6;
        char byte;
        if (write(fds[1], "x", 1) != 1 || read(fds[0], &byte, 1) != 1 || byte != 'x')
            return 7;
        close(fds[0]);
        close(fds[1]);
        char *old = malloc(1);
        if (!old)
            return 8;
        *old = 'q';
        errno = states[i];
        if (rpl_reallocarray(old, SIZE_MAX, 2) || errno != ENOMEM || *old != 'q')
            return 9;
        free(old);
    }
    puts("5 errno states, 15 fd_safer calls, 5 pipes, 5 allocation failures");
    return 0;
}
