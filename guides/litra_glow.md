# Logitech Litra Glow — Home Assistant Integration
*Last updated: May 2026*

## Overview

This document describes how to integrate a Logitech Litra Glow key light with Home Assistant, exposing it as a native light entity with on/off, brightness, and color temperature control. The integration uses the `litra-rs` CLI tool on a Mac Mini, accessed via a dedicated SSH user account from Home Assistant over the local network.

---

## Architecture

```
Home Assistant
  └── shell_command (SSH)
        └── homeassistant@mac-mini
              └── litra_dispatch.sh (whitelist gatekeeper)
                    └── apply_composite (sequenced state → brightness → temperature)
                          └── sudo -u <your_username> /opt/homebrew/bin/litra
                                └── Logitech Litra Glow (USB HID)
```

Key design decisions:

- A dedicated `homeassistant` macOS user handles SSH — no admin rights, key-only auth
- The SSH key is locked to a dispatch script via `restrict,command=` in `authorized_keys`
- The dispatch script whitelists only specific `litra` commands, rejecting everything else
- `litra` requires USB HID access, which is only available to the logged-in user (`<your_username>`), so a targeted `sudo` rule allows `homeassistant` to run `litra` as `<your_username>` only
- The HA light entity runs in optimistic mode — state updates immediately on command without polling
- A composite `litra apply` command applies on/off, brightness, and temperature in a single SSH invocation, working around Home Assistant's template light convention where only one of `set_level` / `set_temperature` fires when both parameters are supplied to `light.turn_on`

---

## Prerequisites

- Home Assistant instance on the local network
- Logitech Litra Glow connected via USB to a Mac Mini
- Mac Mini running macOS with the Home Assistant companion app installed
- Homebrew installed on the Mac Mini

---

## Step 1: Install litra-rs on the Mac Mini

[`litra-rs`](https://github.com/timrogers/litra-rs) is a Rust-based CLI tool that provides full control of Logitech Litra devices over USB.

```bash
brew install litra
```

Verify the installation and note the binary path:

```bash
which litra
# /opt/homebrew/bin/litra
```

### Device specifications (Litra Glow)

Retrieved via `litra devices --json`:

| Property | Value |
| --- | --- |
| Brightness range | 20–250 lumen |
| Temperature range | 2700–6500 kelvin |
| Temperature increment | Must be a multiple of 100 |

### Key CLI commands

| Command | Description |
| --- | --- |
| `litra on` | Turn the light on |
| `litra off` | Turn the light off |
| `litra toggle` | Toggle on/off |
| `litra brightness --value <n>` | Set brightness in lumens (20–250) |
| `litra brightness --percentage <n>` | Set brightness as a percentage |
| `litra brightness-up --value <n>` | Increase brightness by lumen value |
| `litra brightness-up --percentage <n>` | Increase brightness by percentage |
| `litra brightness-down --value <n>` | Decrease brightness by lumen value |
| `litra brightness-down --percentage <n>` | Decrease brightness by percentage |
| `litra temperature --value <n>` | Set color temperature in kelvin (2700–6500, multiples of 100) |
| `litra temperature-up --value <n>` | Increase temperature by kelvin value |
| `litra temperature-down --value <n>` | Decrease temperature by kelvin value |
| `litra devices --json` | Return full device state as JSON |

---

## Step 2: Create a Dedicated SSH User on the Mac Mini

A dedicated `homeassistant` user isolates SSH access. This user has no admin rights and can only authenticate via SSH key.

### Create the user via System Settings

**System Settings → Users & Groups → Add Account**

- Account type: **Standard**
- Full name: `Home Assistant`
- Account name: `homeassistant`
- Set a strong password (password login is disabled via SSH config)

### Hide from login screen

```bash
sudo dscl . -create /Users/homeassistant IsHidden 1
```

### Grant SSH access

macOS manages SSH access via a system group. Add the user to it:

```bash
sudo dseditgroup -o edit -t user -a homeassistant com.apple.access_ssh
```

### Set up the SSH directory

```bash
sudo mkdir -p /Users/homeassistant/.ssh
sudo chmod 700 /Users/homeassistant/.ssh
sudo chown homeassistant:staff /Users/homeassistant/.ssh
```

---

## Step 3: Configure sshd on the Mac Mini

Enable Remote Login in **System Settings → General → Sharing → Remote Login**.

Edit `/etc/ssh/sshd_config` and add the following to restrict access and disable password authentication:

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

Even with "Allow access for all users" enabled in Sharing, only the `homeassistant` account can authenticate, and only via SSH key.

---

## Step 4: Configure sudo for USB HID Access

The `litra` CLI requires USB HID access, which macOS restricts to the active logged-in user session (`<your_username>`). A targeted `sudo` rule allows `homeassistant` to run `litra` as `<your_username>` — and nothing else.

```bash
sudo visudo -f /etc/sudoers.d/homeassistant-litra
```

Add:

```
homeassistant ALL=(<your_username>) NOPASSWD: /opt/homebrew/bin/litra
```

---

## Step 5: Create the Dispatch Script

The dispatch script acts as a security gatekeeper. The SSH authorized key is locked to only execute this script via `restrict,command=`. The script whitelists specific `litra` commands and rejects everything else with a non-zero exit code.

The `apply_composite` function handles the composite `litra apply` pseudo-command, which accepts optional `state=`, `brightness=`, and `temperature=` arguments and sequences them in the correct order on the Mac side, all within one SSH session.

The script is maintained in this repository at `scripts/litra_dispatch.sh`. Before deploying, open it and replace `<your_username>` with your macOS username. Then copy it to the Mac Mini and make it executable:

```bash
sudo cp scripts/litra_dispatch.sh /usr/local/bin/litra_dispatch.sh
sudo chmod +x /usr/local/bin/litra_dispatch.sh
```

### Composite command examples

| Composite invocation | Resulting `litra` calls |
| --- | --- |
| `litra apply state=on` | `litra on` |
| `litra apply state=off` | `litra off` |
| `litra apply state=on brightness=50` | `litra on` → `litra brightness --percentage 50` |
| `litra apply state=on brightness=50 temperature=4500` | `litra on` → `litra brightness --percentage 50` → `litra temperature --value 4500` |
| `litra apply brightness=75 temperature=5500` | `litra brightness --percentage 75` → `litra temperature --value 5500` |

> **Important:** brightness or temperature applied to an off Litra is a silent no-op at the device — the device accepts the command but the LEDs are unlit. For this reason, the HA template light handlers in Step 8 always assert `state=on` whenever they send brightness or temperature, even when the user only changed one of them.

---

## Step 6: Generate SSH Key on Home Assistant

In the Home Assistant terminal:

```bash
mkdir -p /config/.ssh
chmod 700 /config/.ssh
ssh-keygen -t ed25519 -C "homeassistant-litra" -f /config/.ssh/id_ed25519_litra
```

Leave the passphrase empty — HA connects non-interactively.

Build the known_hosts file:

```bash
ssh-keyscan -H <mac-mini-ip> > /config/.ssh/known_hosts
```

---

## Step 7: Authorize the Key on the Mac Mini

Add the HA public key to the `homeassistant` user's `authorized_keys`, locked to the dispatch script:

```bash
sudo vi /Users/homeassistant/.ssh/authorized_keys
```

The entry must include the `restrict,command=` prefix:

```
restrict,command="/usr/local/bin/litra_dispatch.sh" ssh-ed25519 AAAA...your-key... homeassistant-litra
```

Set correct permissions:

```bash
sudo chmod 600 /Users/homeassistant/.ssh/authorized_keys
sudo chown homeassistant:staff /Users/homeassistant/.ssh/authorized_keys
```

The `restrict,command=` prefix means this key can only ever invoke the dispatch script. Even if the private key were compromised, an attacker could only toggle the light.

---

## Step 8: Home Assistant Configuration

### Shell Command (`configuration.yaml`)

A single composite `litra_apply` shell command handles all dispatch. The `{{ args }}` token is substituted with the composite argument string built by the template light handlers below.

```yaml
shell_command:
  litra_apply: >-
    ssh -i /config/.ssh/id_ed25519_litra
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    homeassistant@<mac-mini-ip> "litra apply {{ args }}"
```

### Template Light (`configuration.yaml`)

The light runs in optimistic mode — no `state` template is defined, so HA reflects commands in the UI immediately without waiting for device confirmation.

All four handlers (`turn_on`, `turn_off`, `set_level`, `set_temperature`) are defined for two reasons:

1. `set_level` and `set_temperature` must exist for HA to render the brightness and color-temperature sliders in the UI. The presence of these handlers is what tells HA the light supports those features. `supported_color_modes` is a Python LightEntity API concept and is not accepted by the template light YAML schema.
2. Each handler routes to the same composite `shell_command.litra_apply`, with arg strings built from whatever variables HA passes in.

The arg-string templates must be written on a single logical line. YAML's folded scalar (`>-`) does not collapse newlines that originate inside Jinja `{% if %}` blocks — the literal `\n` characters survive into the rendered string and truncate `SSH_ORIGINAL_COMMAND` at the first newline on the remote side, silently dropping everything after `state=on`. Inline Jinja with explicit spacing avoids this.

The brightness formula converts HA's 0–255 scale to a 0–100 percentage for `litra`. The temperature formula converts HA's mired scale (153–500) to kelvin (2700–6500), rounded to the nearest 100 as required by `litra-rs`. `color_temp | int` forces integer conversion before the formula runs.

```yaml
template:
  - light:
      - name: "Office Desk Key Light"
        unique_id: litra_glow
        turn_on:
          - alias: Turn on (and apply brightness/temp if supplied)
            action: shell_command.litra_apply
            data:
              args: "state=on{% if brightness is defined %} brightness={{ (brightness / 255 * 100) | int }}{% endif %}{% if color_temp is defined %} temperature={{ (((color_temp | int - 153) / (500 - 153)) * (2700 - 6500) + 6500) | int | round(-2) | int }}{% endif %}"
        turn_off:
          - alias: Turn off
            action: shell_command.litra_apply
            data:
              args: "state=off"
        set_level:
          - alias: Brightness adjustment (also ensures light is on)
            action: shell_command.litra_apply
            data:
              args: "state=on brightness={{ (brightness / 255 * 100) | int }}"
        set_temperature:
          - alias: Color temp adjustment (also ensures light is on, plus brightness if supplied)
            action: shell_command.litra_apply
            data:
              args: "state=on temperature={{ (((color_temp | int - 153) / (500 - 153)) * (2700 - 6500) + 6500) | int | round(-2) | int }}{% if brightness is defined %} brightness={{ (brightness / 255 * 100) | int }}{% endif %}"
```

### Why every command-sending handler asserts `state=on`

The Litra accepts brightness and temperature commands while off, but does not power up — it stores the settings silently and applies them on the next `litra on`. From the user's perspective, this looks like "HA shows the light at 50% / 5400K but the room is still dark," because HA's optimistic state model assumes the command succeeded.

To eliminate this footgun, `set_level` and `set_temperature` always include `state=on` in their composite args. On an already-on Litra this is a harmless no-op USB call (under 100ms, no visible flicker). On an off Litra it correctly powers up the light alongside the requested adjustment.

### Behavior matrix

The matrix below assumes the Litra starts in the off state. All cases physically power up the light and apply the requested parameters.

| HA call | Handler invoked | Composite args sent | Resulting actions on Litra |
|---|---|---|---|
| `light.turn_on` (no params) | `turn_on` | `state=on` | Light turns on |
| `light.turn_on` with `brightness=128` | `set_level` | `state=on brightness=50` | Light turns on, brightness set to 50% |
| `light.turn_on` with `color_temp=250` | `set_temperature` | `state=on temperature=5400` | Light turns on, color temp set to 5400K |
| `light.turn_on` with `brightness=128, color_temp=250` | `set_temperature` (with `brightness` as side variable) | `state=on temperature=5400 brightness=50` | Light turns on, brightness and temp both set |
| `light.turn_off` | `turn_off` | `state=off` | Light turns off |

HA accepts `brightness_pct: 50` as an alternative to `brightness: 128` in service calls. The template light receives the value normalized to the 0–255 `brightness` variable regardless of which form the caller used.

### Scale Conversions Reference

| Direction | Formula |
| --- | --- |
| HA brightness (0–255) → litra percentage (0–100) | `(brightness / 255 * 100) | int` |
| HA mireds (153–500) → kelvin (2700–6500) | `(((color_temp | int - 153) / (500 - 153)) * (2700 - 6500) + 6500) | int | round(-2) | int` |

---

## Step 9: Camera Automation

Automatically controls office lighting when the active camera on either Mac becomes the Studio Display Camera. When that camera turns on, ceiling lights and the screen bar are turned off and the Litra key light is enabled at a video-call preset (45% brightness, 4500K). When the camera has been off for 15 seconds, the key light is turned off and the screen bar is restored — but only if the user is currently active on a Mac with the Studio Display as their primary display.

Triggers fire on the camera-name sensors (`sensor.*_active_camera`), which report the active camera's display name as a string. This matches only Studio Display Camera sessions and ignores the built-in MacBook Pro FaceTime camera, since the goal is to optimize lighting specifically for the desk-mounted Studio Display setup.

### Automation

```yaml
alias: Control office lights when display camera is being used
description: >
  Turns off ceiling lights and activates camera lighting when the Studio Display
  Camera turns on. Restores monitor light (if Studio Display is active primary)
  and turns off camera lighting when the camera has been off for 15 seconds.
triggers:
  - trigger: state
    entity_id:
      - sensor.nates_mac_mini_active_camera
      - sensor.nates_macbook_pro_active_camera
    to: Studio Display Camera
    id: "on"
  - trigger: state
    entity_id:
      - sensor.nates_mac_mini_active_camera
      - sensor.nates_macbook_pro_active_camera
    from: Studio Display Camera
    id: "off"
    for:
      seconds: 15
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: "on"
        sequence:
          - action: light.turn_off
            target:
              entity_id:
                - light.office_ceiling
                - light.office_screen_bar
            data: {}
          - action: light.turn_on
            target:
              entity_id: light.office_desk_key_light
            data:
              brightness_pct: 45
              color_temp_kelvin: 4500
            enabled: true
      - conditions:
          - condition: trigger
            id: "off"
        sequence:
          - action: light.turn_off
            target:
              entity_id: light.office_desk_key_light
          - condition: or
            conditions:
              - condition: and
                conditions:
                  - condition: state
                    entity_id: binary_sensor.nates_mac_mini_active
                    state: "on"
                  - condition: state
                    entity_id: sensor.nates_mac_mini_primary_display_name
                    state: Studio Display
              - condition: and
                conditions:
                  - condition: state
                    entity_id: binary_sensor.nates_macbook_pro_active
                    state: "on"
                  - condition: state
                    entity_id: sensor.nates_macbook_pro_primary_display_name
                    state: Studio Display
          - action: light.turn_on
            target:
              entity_id:
                - light.office_screen_bar
            data: {}
mode: single
```

The `light.turn_on` call uses `brightness_pct` and `color_temp_kelvin`. HA normalizes both to the `brightness` (0–255) and `color_temp` (mireds) variables expected by the template light's `set_temperature` handler before invocation, so the integration applies them correctly without any template changes.

---

## Security Summary

| Layer | Detail |
| --- | --- |
| SSH user | Dedicated `homeassistant` account, Standard (non-admin) |
| Authentication | ED25519 key only — password auth disabled in `sshd_config` |
| SSH access restriction | `AllowUsers homeassistant` in `sshd_config` + `com.apple.access_ssh` group membership |
| Command restriction | `restrict,command=` in `authorized_keys` — key can only invoke the dispatch script |
| Dispatch script | Whitelist-based case statement — only explicit litra commands allowed, all others rejected with exit code 1 |
| Composite command validation | `apply_composite` rejects any unknown arg key; brightness/temperature values must match `^[0-9]+$` before being passed to `litra` |
| sudo scope | `homeassistant` can only run `/opt/homebrew/bin/litra` as `<your_username>`, no password required, nothing else permitted |

---

## File Reference

| File | Location | Purpose |
| --- | --- | --- |
| Dispatch script | `scripts/litra_dispatch.sh` in this repo; deployed to `/usr/local/bin/litra_dispatch.sh` on Mac Mini | Command whitelist gatekeeper; includes composite `apply_composite` handler |
| sudoers rule | `/etc/sudoers.d/homeassistant-litra` | Allows `homeassistant` to run `litra` as `<your_username>` |
| SSH private key | `/config/.ssh/id_ed25519_litra` | HA's private key for authenticating to Mac Mini |
| SSH public key | `/config/.ssh/id_ed25519_litra.pub` | Corresponding public key |
| known_hosts | `/config/.ssh/known_hosts` | Mac Mini host key fingerprint |
| authorized_keys | `/Users/homeassistant/.ssh/authorized_keys` | HA public key, locked to dispatch script |
| HA config | `/config/configuration.yaml` | Shell command and template light definition |
