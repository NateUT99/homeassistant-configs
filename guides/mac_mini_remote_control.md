# Mac Mini Remote Control — Display Sleep Lock
*Last updated: October 2026*

## Overview

Home Assistant locks the Mac Mini when everyone goes to sleep and when the last person leaves. It does this over SSH: a restricted key runs a whitelist dispatch script on the Mac that sleeps the display, and because the Mac requires a password immediately after display sleep, sleeping the display is what locks it.

---

## Architecture

```
Household: Sleep Mode ────────┐
Household: Last Leaves Home ──┴─► shell_command.mac_mini_display_sleep (SSH, key id_ed25519_mac_mini)
                                    └── homeassistant@mac-mini
                                          └── mac_dispatch.sh (whitelist gatekeeper)
                                                └── display sleep
                                                      └── sudo -u <your_username> /usr/bin/pmset displaysleepnow
```

Key design decisions:

- **Display sleep is the lock.** The Mac requires a password immediately after the display sleeps, so `pmset displaysleepnow` locks it without any GUI scripting. No supported command-line lock exists for a session the caller isn't logged in to.
- **Its own key and dispatch script.** This shares the `homeassistant` macOS account and sshd setup with the Litra Glow integration, but not its key or dispatch script. Each key can reach only its own whitelist, so a compromised Litra key can't touch the display, and vice versa.
- **Screen Sharing sessions are left alone.** A connected but idle session doesn't wake the display — only input sent through it does — and anyone connected sees the lock screen once the display sleeps. See the Screen Sharing entry in `LESSONS.md`.
- **Fire and forget.** Each caller sets `continue_on_error`, so an unreachable Mac never fails the rest of the routine.

---

## Prerequisites

- The `homeassistant` macOS user, sshd restrictions, and `/config/.ssh/known_hosts` from `guides/litra_glow.md` Steps 2, 3, and 6

---

## Step 1: Require a Password Immediately After Display Sleep

In **System Settings → Lock Screen**, set *Require password after screen saver begins or display is turned off* to **Immediately**. Confirm:

```bash
sysadminctl -screenLock status
# screenLock delay is immediate
```

> **Coordinated change:** this setting is what turns display sleep into a lock. If it changes, both callers still sleep the display but no longer lock the Mac.

---

## Step 2: Configure sudo

`pmset` refuses display sleep from a non-console user, so it runs as the console user, pinned to the exact command line:

```bash
echo 'homeassistant ALL=(<your_username>) NOPASSWD: /usr/bin/pmset displaysleepnow' > /tmp/hd
visudo -cf /tmp/hd && sudo install -o root -g wheel -m 440 /tmp/hd /etc/sudoers.d/homeassistant-display
```

`visudo -cf` validates the file before it is installed, so a typo can't break sudo. Verify with `sudo -l -U homeassistant`.

Run without `sudo -u`, `pmset displaysleepnow` prints `error 1004`, leaves the display on, and still exits `0` — see the `pmset displaysleepnow` entry in `LESSONS.md`.

---

## Step 3: Install the Dispatch Script

Install `scripts/mac_dispatch.sh` from this repo to `/usr/local/bin/mac_dispatch.sh`, substituting the console user's name (run this as that user):

```bash
sed "s/<your_username>/$USER/" scripts/mac_dispatch.sh > /tmp/mac_dispatch.sh
sudo install -o root -g wheel -m 755 /tmp/mac_dispatch.sh /usr/local/bin/mac_dispatch.sh
```

The script accepts exactly one command, `display sleep`, with no arguments. Anything else prints `Unauthorized command` and exits `1`.

---

## Step 4: Generate and Authorize the Key

On the HA host:

```bash
ssh-keygen -t ed25519 -N "" -C "homeassistant-mac-mini" -f /config/.ssh/id_ed25519_mac_mini
cat /config/.ssh/id_ed25519_mac_mini.pub
```

On the Mac, append the public key to the `homeassistant` user's `authorized_keys`, locked to the dispatch script:

```bash
K='restrict,command="/usr/local/bin/mac_dispatch.sh" ssh-ed25519 AAAA...your-key... homeassistant-mac-mini'
echo "$K" | sudo tee -a /Users/homeassistant/.ssh/authorized_keys >/dev/null
```

Verify from the HA host that anything other than `display sleep` is rejected:

```bash
# Should print "Unauthorized command" and exit 1:
ssh -i /config/.ssh/id_ed25519_mac_mini -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/config/.ssh/known_hosts -o ConnectTimeout=5 \
  homeassistant@<mac-mini-hostname> "whoami"
```

---

## Step 5: Home Assistant Package

Deployed to `/config/packages/mac_mini.yaml`; source at `ha/packages/mac_mini.yaml`. Reload with `shell_command.reload`.

```yaml
shell_command:
  # Display sleep locks the Mac (password required immediately after display
  # sleep). pmset exits 0 even when it refuses, so a failure is not visible to HA.
  mac_mini_display_sleep: >-
    ssh -i /config/.ssh/id_ed25519_mac_mini
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    -o ConnectTimeout=5
    homeassistant@<mac-mini-hostname> "display sleep"
```

> **Coordinated change:** the Mac's hostname also appears in `guides/litra_glow.md` (its package and `known_hosts`). If the Mac Mini's address changes, update both packages.

---

## Step 6: Callers

- **Household: Sleep Mode (`automation.household_sleep_mode`)** — an arm of the night-prep parallel block.
- **Household: Last Leaves Home (`automation.household_last_leaves_home`)** — after the "No One Is Home" turn-offs, before the daytime vacuum step.

Because `pmset` exits `0` even when it refuses, HA traces can't show whether the display actually slept. Check on the Mac:

```bash
pmset -g log | grep "Display is turned"
```

Keep hands off any Screen Sharing viewer while testing — mouse movement over the viewer window wakes the display.

---

## Security Summary

| Layer | Detail |
| --- | --- |
| SSH user | Shared dedicated `homeassistant` account, Standard (non-admin) — see `guides/litra_glow.md` |
| Authentication | ED25519 key `id_ed25519_mac_mini`, separate from the Litra key; password auth disabled in `sshd_config` |
| Command restriction | `restrict,command="/usr/local/bin/mac_dispatch.sh"` in `authorized_keys` — this key can only invoke this script |
| Dispatch script | Whitelist of one fixed command string; no caller-supplied arguments reach any command |
| sudo scope | `pmset displaysleepnow` as `<your_username>`, pinned to that exact command line, nothing else |
| Worst case if the key leaks | An attacker on the LAN can blank (and therefore lock) the Mac's display. No shell, no file access, no other process control |

---

## Related HA Config

| Artifact | Entity ID | Type |
| --- | --- | --- |
| Mac Mini display sleep | `shell_command.mac_mini_display_sleep` | Shell command (package: `ha/packages/mac_mini.yaml`) |
| Household: Sleep Mode | `automation.household_sleep_mode` | Automation — caller; owned by the sleep routine |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation — caller; owned by presence tracking |

---

## Related Files

| File | Location | Purpose |
| --- | --- | --- |
| Package config | `ha/packages/mac_mini.yaml` in this repo; deployed to `/config/packages/mac_mini.yaml` on HA | `shell_command` definition |
| Dispatch script | `scripts/mac_dispatch.sh` in this repo; deployed to `/usr/local/bin/mac_dispatch.sh` on Mac Mini | Command whitelist gatekeeper |
| sudoers rule | `/etc/sudoers.d/homeassistant-display` | `pmset displaysleepnow` as `<your_username>` |
| SSH private key | `/config/.ssh/id_ed25519_mac_mini` | HA's key for this integration |
| authorized_keys | `/Users/homeassistant/.ssh/authorized_keys` | This key's entry, locked to `mac_dispatch.sh` |

---

## Related Documents

- `guides/litra_glow.md` — the `homeassistant` user, sshd configuration, and `known_hosts` this guide builds on
- `guides/presence_tracking.md` — Household: Last Leaves Home and its departure debounce
