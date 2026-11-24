/* SPDX-License-Identifier: 0BSD */
#include <stdio.h>
#include <string.h>

typedef int (*shadow_main_fn)(int, char **);

#define SHADOW_ENGINE(name) \
	extern int rustbox_shadow_##name##_main(int, char **)

SHADOW_ENGINE(chage);
SHADOW_ENGINE(chfn);
SHADOW_ENGINE(chgpasswd);
SHADOW_ENGINE(chpasswd);
SHADOW_ENGINE(chsh);
SHADOW_ENGINE(faillog);
SHADOW_ENGINE(getsubids);
SHADOW_ENGINE(gpasswd);
SHADOW_ENGINE(groupadd);
SHADOW_ENGINE(groupdel);
SHADOW_ENGINE(groupmod);
SHADOW_ENGINE(grpck);
SHADOW_ENGINE(grpconv);
SHADOW_ENGINE(grpunconv);
SHADOW_ENGINE(lastlog);
SHADOW_ENGINE(login);
SHADOW_ENGINE(newgidmap);
SHADOW_ENGINE(newgrp);
SHADOW_ENGINE(newuidmap);
SHADOW_ENGINE(newusers);
SHADOW_ENGINE(nologin);
SHADOW_ENGINE(passwd);
SHADOW_ENGINE(pwck);
SHADOW_ENGINE(pwconv);
SHADOW_ENGINE(pwunconv);
SHADOW_ENGINE(su);
SHADOW_ENGINE(useradd);
SHADOW_ENGINE(userdel);
SHADOW_ENGINE(usermod);
SHADOW_ENGINE(vipw);

struct shadow_applet {
	const char *name;
	shadow_main_fn main_fn;
};

#define SHADOW_APPLET(name) \
	{#name, rustbox_shadow_##name##_main}

static const struct shadow_applet applets[] = {
	SHADOW_APPLET(chage),
	SHADOW_APPLET(chfn),
	SHADOW_APPLET(chgpasswd),
	SHADOW_APPLET(chpasswd),
	SHADOW_APPLET(chsh),
	SHADOW_APPLET(faillog),
	SHADOW_APPLET(getsubids),
	SHADOW_APPLET(gpasswd),
	SHADOW_APPLET(groupadd),
	SHADOW_APPLET(groupdel),
	SHADOW_APPLET(groupmod),
	SHADOW_APPLET(grpck),
	SHADOW_APPLET(grpconv),
	SHADOW_APPLET(grpunconv),
	SHADOW_APPLET(lastlog),
	SHADOW_APPLET(login),
	SHADOW_APPLET(newgidmap),
	SHADOW_APPLET(newgrp),
	SHADOW_APPLET(newuidmap),
	SHADOW_APPLET(newusers),
	SHADOW_APPLET(nologin),
	SHADOW_APPLET(passwd),
	SHADOW_APPLET(pwck),
	SHADOW_APPLET(pwconv),
	SHADOW_APPLET(pwunconv),
	SHADOW_APPLET(su),
	SHADOW_APPLET(useradd),
	SHADOW_APPLET(userdel),
	SHADOW_APPLET(usermod),
	SHADOW_APPLET(vipw),
	{"sg", rustbox_shadow_newgrp_main},
	{"vigr", rustbox_shadow_vipw_main},
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
	fprintf(stderr, "shadow: unknown applet: %s\n", name);
	return 127;
}
