/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

extern int rustbox_pilot_recvmsg(int, struct msghdr *, char **);

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; ++i) {
        const long expected = strtol(argv[i], NULL, 10);
        struct iovec iov = {0};
        struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1 };
        char *buf = NULL;
        int n = rustbox_pilot_recvmsg(STDIN_FILENO, &msg, &buf);
        if (n <= 0 || n != expected || !buf || buf != iov.iov_base ||
            iov.iov_len != (size_t)(n < 32768 ? 32768 : n))
            return 1;
        for (int k = 0; k < n; ++k)
            if ((unsigned char)buf[k] != 0xa5)
                return 1;
        size_t aligned = ((size_t)n + 3) & ~(size_t)3;
        for (size_t k = n; k < aligned + 2; ++k)
            if (buf[k] != 0)
                return 1;
        free(buf);
    }
    return 0;
}
