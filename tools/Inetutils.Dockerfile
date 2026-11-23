ARG BASE_IMAGE=rustbox-curl:2026-11-23
FROM ${BASE_IMAGE}

# GNU Inetutils 2.8 ships generated build machinery and uses only interfaces
# already present in the inherited translation/audit image for Rustbox's
# no-systemd, no-PAM canonical profile.  Readline and Ncurses remain enabled
# for the interactive canonical clients and will be isolated during applet
# integration.
