# Logitech Litra Glow — Home Assistant Integration

## Overview

This document describes how to integrate a Logitech Litra Glow key light with Home Assistant, exposing it as a native light entity with on/off, brightness, and color temperature control. The integration uses the `litra-rs` CLI tool on a Mac Mini, accessed via a dedicated SSH user account from Home Assistant over the local network.

---

## Architecture

```
Home Assistant
  └── shell_command (SSH)
        └── homeassistant@mac-mini
              └── litra_dispatch.sh (whitelist gatekeeper)
                    └── sudo -u <your_username> /opt/homebrew/bin/litra
                          └── Logitech Litra Glow (USB HID)
```

Key design decisions:
- A dedicated `homeassistant` macOS user handles SSH — no admin rights, key-only auth
- The SSH key is locked to a dispatch script via `restrict,command=` in `authorized_keys`
- The dispatch script whitelists only specific `litra` commands, rejecting everything else
- `litra` requires USB HID access, which is only available to the logged-in user (`<your_username>`), so a targeted `sudo` rule allows `homeassistant` to run `litra` as `<your_username>` only
- The HA light entity runs in optimistic mode — state updates immediately on command without polling

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
|---|---|
| Brightness range | 20–250 lumen |
| Temperature range | 2700–6500 kelvin |
| Temperature increment | Must be a multiple of 100 |

### Key CLI commands

| Command | Description |
|---|---|
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

```bash
sudo nano /usr/local/bin/litra_dispatch.sh
```

```bash
#!/bin/zsh

case "$SSH_ORIGINAL_COMMAND" in
  "litra on")                   sudo -u <your_username> /opt/homebrew/bin/litra on ;;
  "litra off")                  sudo -u <your_username> /opt/homebrew/bin/litra off ;;
  "litra toggle")               sudo -u <your_username> /opt/homebrew/bin/litra toggle ;;
  "litra brightness --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness --value "$LEVEL" ;;
  "litra brightness --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness --percentage }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness --percentage "$PCT" ;;
  "litra brightness-up --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness-up --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness-up --value "$LEVEL" ;;
  "litra brightness-up --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness-up --percentage }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness-up --percentage "$PCT" ;;
  "litra brightness-down --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness-down --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness-down --value "$LEVEL" ;;
  "litra brightness-down --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness-down --percentage }"
    sudo -u <your_username> /opt/homebrew/bin/litra brightness-down --percentage "$PCT" ;;
  "litra temperature --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra temperature --value "$TEMP" ;;
  "litra temperature-up --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature-up --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra temperature-up --value "$TEMP" ;;
  "litra temperature-down --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature-down --value }"
    sudo -u <your_username> /opt/homebrew/bin/litra temperature-down --value "$TEMP" ;;
  *) echo "Unauthorized command" >&2; exit 1 ;;
esac
```

```bash
sudo chmod +x /usr/local/bin/litra_dispatch.sh
```

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
sudo nano /Users/homeassistant/.ssh/authorized_keys
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

### Shell Commands (`configuration.yaml`)

> **Note:** `shell_command` renders Jinja templates in the command string when variables are passed via `data` from a template light action. The `{{ value }}` token is substituted with the computed value before the command is executed.

```yaml
shell_command:
  litra_on: >-
    ssh -i /config/.ssh/id_ed25519_litra
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    homeassistant@<mac-mini-ip> "litra on"
  litra_off: >-
    ssh -i /config/.ssh/id_ed25519_litra
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    homeassistant@<mac-mini-ip> "litra off"
  litra_set_brightness_percentage: >-
    ssh -i /config/.ssh/id_ed25519_litra
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    homeassistant@<mac-mini-ip> "litra brightness --percentage {{ value }}"
  litra_set_temperature: >-
    ssh -i /config/.ssh/id_ed25519_litra
    -o StrictHostKeyChecking=yes
    -o UserKnownHostsFile=/config/.ssh/known_hosts
    homeassistant@<mac-mini-ip> "litra temperature --value {{ value }}"
```

### Template Light (`configuration.yaml`)

The light runs in optimistic mode — no `state` template is defined, so HA immediately reflects commands in the UI without waiting for device confirmation.

The brightness formula converts HA's 0–255 scale to a 0–100 percentage for `litra`. The temperature formula converts HA's mired scale (153–500) to kelvin (2700–6500), rounded to the nearest 100 as required by `litra-rs`. Note that `color_temp | int` is required to force integer conversion before the formula runs.

```yaml
template:
  - light:
      - name: "Office Desk Key Light"
        unique_id: litra_glow
        turn_on:
          - action: shell_command.litra_on
        turn_off:
          - action: shell_command.litra_off
        set_level:
          - action: shell_command.litra_set_brightness_percentage
            data:
              value: "{{ (brightness / 255 * 100) | int }}"
        set_temperature:
          - action: shell_command.litra_set_temperature
            data:
              value: "{{ (((color_temp | int - 153) / (500 - 153)) * (2700 - 6500) + 6500) | int | round(-2) | int }}"
```

### Scale Conversions Reference

| Direction | Formula |
|---|---|
| HA brightness (0–255) → litra percentage (0–100) | `(brightness / 255 * 100) \| int` |
| HA mireds (153–500) → kelvin (2700–6500) | `(((color_temp \| int - 153) / (500 - 153)) * (2700 - 6500) + 6500) \| int \| round(-2) \| int` |

---

## Step 9: Camera Automation

Automatically controls office lighting when the Mac Mini or MacBook Pro camera becomes active. When the camera turns on, the key light is enabled and other office lights are turned off for better video quality. When the camera turns off, the original lighting state is restored.

### Helper

An `input_boolean` tracks whether the ceiling lights were on before the camera session started, so they are only restored if they were originally on.

**Settings → Devices & Services → Helpers → Create Helper → Toggle**

- Name: `office_ceiling_lights_on_before_camera`
- Entity ID: `input_boolean.office_ceiling_lights_on_before_camera`

### Automation

```yaml
alias: Control office lights when display camera is being used
description: ""
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.nates_mac_mini_camera_in_use
      - binary_sensor.nates_macbook_pro_camera_in_use
    to:
      - "on"
    id: "on"
    from:
      - "off"
  - trigger: state
    entity_id:
      - binary_sensor.nates_mac_mini_camera_in_use
      - binary_sensor.nates_macbook_pro_camera_in_use
    to:
      - "off"
    from:
      - "on"
    id: "off"
    for:
      hours: 0
      minutes: 0
      seconds: 15
conditions: []
actions:
  - choose:
      - conditions:
          - condition: trigger
            id:
              - "on"
        sequence:
          - alias: Record if office ceiling lights are on or off
            if:
              - condition: state
                entity_id: light.zigbee_controller_office_ceiling_lights
                state:
                  - "on"
            then:
              - action: input_boolean.turn_on
                metadata: {}
                target:
                  entity_id: input_boolean.office_ceiling_lights_on_before_camera
                data: {}
                alias: Mark ceiling lights as "on"
            else:
              - action: input_boolean.turn_off
                metadata: {}
                target:
                  entity_id: input_boolean.office_ceiling_lights_on_before_camera
                data: {}
          - action: light.turn_off
            metadata: {}
            target:
              entity_id:
                - light.office_monitor_light_switch
                - light.zigbee_controller_office_ceiling_lights
            data: {}
          - action: light.turn_on
            metadata: {}
            data: {}
            target:
              entity_id: light.office_desk_key_light
      - conditions:
          - condition: trigger
            id:
              - "off"
        sequence:
          - action: light.turn_off
            metadata: {}
            data: {}
            target:
              entity_id: light.office_desk_key_light
          - action: light.turn_on
            metadata: {}
            target:
              entity_id:
                - light.office_monitor_light_switch
            data: {}
          - if:
              - condition: state
                entity_id: input_boolean.office_ceiling_lights_on_before_camera
                state:
                  - "on"
            then:
              - action: light.turn_on
                metadata: {}
                data: {}
                target:
                  entity_id: light.zigbee_controller_office_ceiling_lights
            alias: Were office ceiling lights on before?
mode: single
```

---

## Security Summary

| Layer | Detail |
|---|---|
| SSH user | Dedicated `homeassistant` account, Standard (non-admin) |
| Authentication | ED25519 key only — password auth disabled in `sshd_config` |
| SSH access restriction | `AllowUsers homeassistant` in `sshd_config` + `com.apple.access_ssh` group membership |
| Command restriction | `restrict,command=` in `authorized_keys` — key can only invoke the dispatch script |
| Dispatch script | Whitelist-based case statement — only explicit litra commands allowed, all others rejected with exit code 1 |
| sudo scope | `homeassistant` can only run `/opt/homebrew/bin/litra` as `<your_username>`, no password required, nothing else permitted |

---

## File Reference

| File | Location | Purpose |
|---|---|---|
| Dispatch script | `/usr/local/bin/litra_dispatch.sh` | Command whitelist gatekeeper on Mac Mini |
| sudoers rule | `/etc/sudoers.d/homeassistant-litra` | Allows `homeassistant` to run `litra` as `<your_username>` |
| SSH private key | `/config/.ssh/id_ed25519_litra` | HA's private key for authenticating to Mac Mini |
| SSH public key | `/config/.ssh/id_ed25519_litra.pub` | Corresponding public key |
| known_hosts | `/config/.ssh/known_hosts` | Mac Mini host key fingerprint |
| authorized_keys | `/Users/homeassistant/.ssh/authorized_keys` | HA public key, locked to dispatch script |
| HA config | `/config/configuration.yaml` | Shell commands and template light definition |
