/* SPDX-License-Identifier: 0BSD */
#include <stdio.h>
#include <string.h>

typedef int (*procps_main_fn)(int, char **);

extern int rustbox_procps_free_main(int, char **);
extern int rustbox_procps_hugetop_main(int, char **);
extern int rustbox_procps_kill_main(int, char **);
extern int rustbox_procps_pgrep_main(int, char **);
extern int rustbox_procps_pidof_main(int, char **);
extern int rustbox_procps_pmap_main(int, char **);
extern int rustbox_procps_ps_main(int, char **);
extern int rustbox_procps_pwdx_main(int, char **);
extern int rustbox_procps_skill_main(int, char **);
extern int rustbox_procps_slabtop_main(int, char **);
extern int rustbox_procps_sysctl_main(int, char **);
extern int rustbox_procps_tload_main(int, char **);
extern int rustbox_procps_top_main(int, char **);
extern int rustbox_procps_uptime_main(int, char **);
extern int rustbox_procps_vmstat_main(int, char **);
extern int rustbox_procps_w_main(int, char **);
extern int rustbox_procps_watch_main(int, char **);

struct procps_applet {
    const char *name;
    procps_main_fn main_fn;
};

static const struct procps_applet applets[] = {
    {"free", rustbox_procps_free_main},
    {"hugetop", rustbox_procps_hugetop_main},
    {"kill", rustbox_procps_kill_main},
    {"pgrep", rustbox_procps_pgrep_main},
    {"pidof", rustbox_procps_pidof_main},
    {"pidwait", rustbox_procps_pgrep_main},
    {"pkill", rustbox_procps_pgrep_main},
    {"pmap", rustbox_procps_pmap_main},
    {"ps", rustbox_procps_ps_main},
    {"pwdx", rustbox_procps_pwdx_main},
    {"skill", rustbox_procps_skill_main},
    {"slabtop", rustbox_procps_slabtop_main},
    {"snice", rustbox_procps_skill_main},
    {"sysctl", rustbox_procps_sysctl_main},
    {"tload", rustbox_procps_tload_main},
    {"top", rustbox_procps_top_main},
    {"uptime", rustbox_procps_uptime_main},
    {"vmstat", rustbox_procps_vmstat_main},
    {"w", rustbox_procps_w_main},
    {"watch", rustbox_procps_watch_main},
};

int main(int argc, char **argv)
{
    const char *name = strrchr(argv[0], '/');
    size_t i;

    name = name ? name + 1 : argv[0];
    for (i = 0; i < sizeof(applets) / sizeof(applets[0]); ++i) {
        if (strcmp(name, applets[i].name) == 0)
            return applets[i].main_fn(argc, argv);
    }
    fprintf(stderr, "procps: unknown applet: %s\n", name);
    return 127;
}
