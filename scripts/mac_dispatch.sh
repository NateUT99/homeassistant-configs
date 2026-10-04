#!/bin/zsh
# mac_dispatch.sh
# SSH command gatekeeper for Mac Mini display sleep.
# Invoked exclusively via the restrict,command= directive on HA's
# id_ed25519_mac_mini key in /Users/homeassistant/.ssh/authorized_keys —
# never called directly. Whitelists specific commands; rejects everything
# else with exit 1. Takes no arguments from the caller.
# Security model and integration details: guides/mac_mini_remote_control.md

RUN_AS="<your_username>"

case "$SSH_ORIGINAL_COMMAND" in
  # pmset refuses display sleep from a non-console user (error 1004, exit 0),
  # so it runs as the console user. Display sleep locks the Mac when it
  # requires a password immediately after display sleep.
  "display sleep")
    sudo -u "$RUN_AS" /usr/bin/pmset displaysleepnow ;;
  *) echo "Unauthorized command" >&2; exit 1 ;;
esac
