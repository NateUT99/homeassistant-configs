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
- **A dedicated, locked-down service account.** HA connects as a non-admin `homeassistant` account that accepts key auth only. Its one key is forced through a whitelist dispatch script, so a leaked key can only sleep the display.
- **Screen Sharing sessions are left alone.** A connected but idle session doesn't wake the display — only input sent through it does — and anyone connected sees the lock screen once the display sleeps. See the Screen Sharing entry in `LESSONS.md`.
- **Fire and forget.** Each caller sets `continue_on_error`, so an unreachable Mac never fails the rest of the routine.

---

## Prerequisites

- Remote Login enabled on the Mac Mini (**System Settings → General → Sharing → Remote Login**)
- SSH access to the HA host (`ssh ha`)

---

## Step 1: Create the SSH Service Account

A dedicated Standard (non-admin) account isolates SSH access. Create it in **System Settings → Users & Groups → Add Account**:

- Account type: **Standard**
- Full name: `Home Assistant`
- Account name: `homeassistant`
- A strong password (password login is disabled for SSH in Step 2)

Hide it from the login screen, grant it SSH access, and create its `.ssh` directory:

```bash
sudo dscl . -create /Users/homeassistant IsHidden 1
sudo dseditgroup -o edit -t user -a homeassistant com.apple.access_ssh
sudo mkdir -p /Users/homeassistant/.ssh
sudo chmod 700 /Users/homeassistant/.ssh
sudo chown homeassistant:staff /Users/homeassistant/.ssh
```

---

## Step 2: Restrict sshd

Add to `/etc/ssh/sshd_config`:

```
AllowUsers homeassistant
PasswordAuthentication no
ChallengeResponseAuthentication no
```

Restart sshd:

```bash
sudo launchctl stop com.openssh.sshd
sudo launchctl start com.openssh.sshd
```

Even with Remote Login set to allow all users, only `homeassistant` can authenticate, and only with a key.

---

## Step 3: Require a Password Immediately After Display Sleep

In **System Settings → Lock Screen**, set *Require password after screen saver begins or display is turned off* to **Immediately**. Confirm:

```bash
sysadminctl -screenLock status
# screenLock delay is immediate
```

> **Coordinated change:** this setting is what turns display sleep into a lock. If it changes, both callers still sleep the display but no longer lock the Mac.

---

## Step 4: Configure sudo

`pmset` refuses display sleep from a non-console user, so it runs as the console user, pinned to the exact command line:

```bash
echo 'homeassistant ALL=(<your_username>) NOPASSWD: /usr/bin/pmset displaysleepnow' > /tmp/hd
visudo -cf /tmp/hd && sudo install -o root -g wheel -m 440 /tmp/hd /etc/sudoers.d/homeassistant-display
```

`visudo -cf` validates the file before it is installed, so a typo can't break sudo. Verify with `sudo -l -U homeassistant`.

Run without `sudo -u`, `pmset displaysleepnow` prints `error 1004`, leaves the display on, and still exits `0` — see the `pmset displaysleepnow` entry in `LESSONS.md`.

---

## Step 5: Install the Dispatch Script

Install `scripts/mac_dispatch.sh` from this repo to `/usr/local/bin/mac_dispatch.sh`, substituting the console user's name (run this as that user):

```bash
sed "s/<your_username>/$USER/" scripts/mac_dispatch.sh > /tmp/mac_dispatch.sh
sudo install -o root -g wheel -m 755 /tmp/mac_dispatch.sh /usr/local/bin/mac_dispatch.sh
```

The script accepts exactly one command, `display sleep`, with no arguments. Anything else prints `Unauthorized command` and exits `1`.

---

## Step 6: Generate and Authorize the Key

On the HA host:

```bash
mkdir -p /config/.ssh && chmod 700 /config/.ssh
ssh-keygen -t ed25519 -N "" -C "homeassistant-mac-mini" -f /config/.ssh/id_ed25519_mac_mini
ssh-keyscan -H <mac-mini-hostname> > /config/.ssh/known_hosts
cat /config/.ssh/id_ed25519_mac_mini.pub
```

Prefer the Mac's `.lan` hostname over a static IP if the router registers DHCP hostnames in local DNS; it follows the Mac's lease with no reservation to maintain. On a dual-stack LAN, `ssh-keyscan` can return nothing on the first attempt. Retry before concluding the host is unreachable; a plain `ssh` to the same name is unaffected.

On the Mac, append the public key to the `homeassistant` user's `authorized_keys`, locked to the dispatch script:

```bash
K='restrict,command="/usr/local/bin/mac_dispatch.sh" ssh-ed25519 AAAA...your-key... homeassistant-mac-mini'
echo "$K" | sudo tee -a /Users/homeassistant/.ssh/authorized_keys >/dev/null
```

Set its permissions:

```bash
sudo chmod 600 /Users/homeassistant/.ssh/authorized_keys
sudo chown homeassistant:staff /Users/homeassistant/.ssh/authorized_keys
```

Verify from the HA host that anything other than `display sleep` is rejected:

```bash
# Should print "Unauthorized command" and exit 1:
ssh -i /config/.ssh/id_ed25519_mac_mini -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/config/.ssh/known_hosts -o ConnectTimeout=5 \
  homeassistant@<mac-mini-hostname> "whoami"
```

---

## Step 7: Home Assistant Package

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

> **Coordinated change:** the Mac's hostname appears here and in the Step 6 `ssh-keyscan`. If the Mac Mini's address changes, update the package and regenerate `known_hosts`.

---

## Step 8: Callers

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
| SSH user | Dedicated `homeassistant` account, Standard (non-admin), hidden from the login screen |
| SSH access restriction | `AllowUsers homeassistant` in `sshd_config` + `com.apple.access_ssh` group membership |
| Authentication | ED25519 key `id_ed25519_mac_mini`; password and challenge-response auth disabled in `sshd_config` |
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
| sshd config | `/etc/ssh/sshd_config` on Mac Mini | `AllowUsers` and key-only auth |
| known_hosts | `/config/.ssh/known_hosts` | Mac Mini host key fingerprint |

---

## Related Documents

- `guides/presence_tracking.md` — Household: Last Leaves Home and its departure debounce
