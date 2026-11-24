/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stdio.h>
#include <unistd.h>
#include "libnetlink.h"

extern int print_fdb(struct nlmsghdr *, void *);

/* The harness supplies a real Netlink socket on stdin. Exercise the same
 * listener and FDB printer as bridge monitor, ending at our control record. */
enum { finished = -77 };
static int dispatch(struct rtnl_ctrl_data *ctrl, struct nlmsghdr *msg, void *arg)
{
    (void)ctrl;
    switch (msg->nlmsg_type) {
    case NLMSG_DONE:
        return finished;
    case RTM_NEWNEIGH:
    case RTM_DELNEIGH:
        return print_fdb(msg, arg);
    default:
        return -1;
    }
}

int main(void)
{
    struct rtnl_handle receiver = { .fd = STDIN_FILENO };
    return rtnl_listen(&receiver, dispatch, stdout) == finished ? 0 : 1;
}
