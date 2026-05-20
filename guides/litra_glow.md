# Logitech Litra Glow — Home Assistant Integration
*Last updated: May 2026*

## Overview

This document describes how to integrate a Logitech Litra Glow key light with Home Assistant, exposing it as a native light entity with on/off, brightness, and color temperature control. The integration uses the `litra-rs` CLI tool on a Mac Mini, accessed via a dedicated SSH user account from Home Assistant over the local network.

---

## Architecture

```
Home Assistant
  ├── shell_command.litra_apply (SSH) ── commands (on/off/brightness/temp)
  └── sensor.litra_glow_status (SSH) ── status query (hourly + after each command)
        └── homeassistant@mac-mini
              └── litra_dispatch.sh (whitelist gatekeeper)
                    ├── litra apply [state=] [brightness=] [temperature=]
                    │     └── apply_composite: sequenced on → brightness → temp → off
                    └── litra devices --json
                          └── sudo -u <your_username> /opt/homebrew/bin/litra
                                └── Logitech Litra Glow (USB HID)
```

Key design decisions:

- A dedicated `homeassistant` macOS user handles SSH — no admin rights, key-only auth
- The SSH key is locked to a dispatch script via `restrict,command=` in `authorized_keys`
- The dispatch script whitelists only specific `litra` commands, rejecting everything else
- `litra` requires USB HID access, which is only available to the logged-in user (`<your_username>`), so a targeted `sudo` rule allows `homeassistant` to run `litra` as `<your_username>` only
- A `command_line` sensor (`sensor.litra_glow_status`) polls the device's actual state via `litra devices --json`, serving as the source of truth for the template light's `state`, `level`, and `temperature` templates — the light is no longer in optimistic mode. Each command handler also triggers an immediate sensor refresh so the UI stays in sync without waiting for the hourly poll.
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

The `apply_composite` function handles the composite `litra apply` pseudo-command, which accepts optional `state=`, `brightness=`, and `temperature=` arguments and sequences them in the correct order on the Mac side, all within one SSH session. A read-only `litra devices --json` case is also whitelisted for the state-tracking sensor added in Step 8.

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
    -o ConnectTimeout=5
    homeassistant@<mac-mini-ip> "litra apply {{ args }}"
```

### Template Light (`configuration.yaml`)

The template light is state-tracked rather than optimistic. A `command_line` sensor (`sensor.litra_glow_status`, defined below) polls the device's actual state and drives the `state`, `level`, and `temperature` templates. After each command handler runs, it triggers an immediate sensor refresh via `homeassistant.update_entity` so the UI reflects the new state within a second rather than waiting for the hourly poll.

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
        availability: "{{ states('sensor.litra_glow_status') != 'unavailable' }}"
        state: "{{ is_state('sensor.litra_glow_status', 'on') }}"
        level: >-
          {% set l = state_attr('sensor.litra_glow_status', 'brightness_in_lumen') %}
          {{ ((l | int - 20) / 230 * 255) | int if l is not none else none }}
        temperature: >-
          {% set k = state_attr('sensor.litra_glow_status', 'temperature_in_kelvin') %}
          {{ (1000000 / (k | int)) | int if k is not none else none }}
        turn_on:
          - alias: Turn on (and apply brightness/temp if supplied)
            action: shell_command.litra_apply
            data:
              args: "state=on{% if brightness is defined %} brightness={{ (brightness / 255 * 100) | int }}{% endif %}{% if color_temp is defined %} temperature={{ (1000000 / (color_temp | int)) | round(-2) | int }}{% endif %}"
          - alias: Refresh Litra status sensor
            action: homeassistant.update_entity
            target:
              entity_id: sensor.litra_glow_status
        turn_off:
          - alias: Turn off
            action: shell_command.litra_apply
            data:
              args: "state=off"
          - alias: Refresh Litra status sensor
            action: homeassistant.update_entity
            target:
              entity_id: sensor.litra_glow_status
        set_level:
          - alias: Brightness adjustment (also ensures light is on)
            action: shell_command.litra_apply
            data:
              args: "state=on brightness={{ (brightness / 255 * 100) | int }}"
          - alias: Refresh Litra status sensor
            action: homeassistant.update_entity
            target:
              entity_id: sensor.litra_glow_status
        set_temperature:
          - alias: Color temp adjustment (also ensures light is on, plus brightness if supplied)
            action: shell_command.litra_apply
            data:
              args: "state=on temperature={{ (1000000 / (color_temp | int)) | round(-2) | int }}{% if brightness is defined %} brightness={{ (brightness / 255 * 100) | int }}{% endif %}"
          - alias: Refresh Litra status sensor
            action: homeassistant.update_entity
            target:
              entity_id: sensor.litra_glow_status
```

The `availability` template treats `unknown` as available so the entity remains usable while the sensor is refreshing — only `unavailable` (Mac unreachable) hides the light from the UI. The `level` and `temperature` templates return `none` when their source attributes are absent during initial sensor load, which tells HA to leave those values unset rather than silently writing a wrong value.

### Command-line Status Sensor (`configuration.yaml`)

This sensor polls the device state via SSH once per hour as a safety net, and is also refreshed immediately after every command handler runs. It is the source of truth for the template light's `state`, `level`, and `temperature` templates.

`litra devices --json` returns a JSON array. The first element contains the Litra Glow's state. `value_template` normalizes the boolean `is_on` field to the HA-idiomatic `'on'`/`'off'` string so downstream templates can use `is_state()`. `json_attributes_path: "$[0]"` extracts all attributes from the first device object.

```yaml
command_line:
  - sensor:
      name: "Litra Glow Status"
      unique_id: litra_glow_status
      command: >-
        ssh -i /config/.ssh/id_ed25519_litra
        -o StrictHostKeyChecking=yes
        -o UserKnownHostsFile=/config/.ssh/known_hosts
        -o ConnectTimeout=5
        homeassistant@<mac-mini-ip> "litra devices --json"
      command_timeout: 10
      value_template: "{{ 'on' if value_json[0].is_on else 'off' }}"
      json_attributes_path: "$[0]"
      json_attributes:
        - is_on
        - brightness_in_lumen
        - temperature_in_kelvin
        - minimum_brightness_in_lumen
        - maximum_brightness_in_lumen
        - minimum_temperature_in_kelvin
        - maximum_temperature_in_kelvin
      scan_interval: 3600
```

`ConnectTimeout=5` and `command_timeout: 10` prevent the sensor from hanging when the Mac is unreachable — a 75-second default SSH connect timeout would freeze HA's command_line integration worker thread for each failed poll. If the Mac is unreachable, the sensor goes `unavailable`, which propagates to the template light via the `availability` template.

### Startup Recovery Automation

On every HA restart, the command_line sensor would otherwise sit idle until its next scheduled poll (up to an hour away). This automation fires on `homeassistant.start` to refresh the sensor immediately, so state is accurate before the first user interaction.

```yaml
alias: Refresh Litra Glow status on HA start
description: >
  Forces sensor.litra_glow_status to poll the device immediately when HA starts up,
  so the template light reflects accurate state before the next scheduled scan_interval.
triggers:
  - alias: HA finished starting
    trigger: homeassistant
    event: start
conditions: []
actions:
  - alias: Refresh Litra status sensor
    action: homeassistant.update_entity
    target:
      entity_id: sensor.litra_glow_status
mode: single
```

### Why every command-sending handler asserts `state=on`

The Litra accepts brightness and temperature commands while off, but does not power up — it stores the settings silently and applies them on the next `litra on`. From the user's perspective, this looks like "HA shows the light at 50% / 5400K but the room is still dark."

To eliminate this footgun, `set_level` and `set_temperature` always include `state=on` in their composite args. On an already-on Litra this is a harmless no-op USB call (under 100ms, no visible flicker). On an off Litra it correctly powers up the light alongside the requested adjustment.

### Behavior matrix

The matrix below assumes the Litra starts in the off state. All cases physically power up the light and apply the requested parameters.

| HA call | Handler invoked | Composite args sent | Resulting actions on Litra |
|---|---|---|---|
| `light.turn_on` (no params) | `turn_on` | `state=on` | Light turns on |
| `light.turn_on` with `brightness=128` | `set_level` | `state=on brightness=50` | Light turns on, brightness set to 50% |
| `light.turn_on` with `color_temp=250` | `set_temperature` | `state=on temperature=4000` | Light turns on, color temp set to 4000K |
| `light.turn_on` with `brightness=128, color_temp=250` | `set_temperature` (with `brightness` as side variable) | `state=on temperature=4000 brightness=50` | Light turns on, brightness and temp both set |
| `light.turn_off` | `turn_off` | `state=off` | Light turns off |

HA accepts `brightness_pct: 50` as an alternative to `brightness: 128` in service calls. The template light receives the value normalized to the 0–255 `brightness` variable regardless of which form the caller used.

### Scale Conversions Reference

| Direction | Formula |
| --- | --- |
| HA brightness (0–255) → litra percentage (0–100) | `(brightness / 255 * 100) \| int` |
| litra brightness_in_lumen (20–250) → HA brightness (0–255) | `((brightness_in_lumen \| int - 20) / 230 * 255) \| int` |
| HA mireds → device kelvin (rounded to nearest 100K) | `(1000000 / (color_temp \| int)) \| round(-2) \| int` |
| device kelvin → HA mireds | `(1000000 / (temperature_in_kelvin \| int)) \| int` |

The temperature conversions use the standard mireds formula (`1,000,000 / mireds = kelvin`). The Litra Glow's usable range is 2700–6500K (370–153 mireds). HA's default mired range extends beyond this, so the device silently clamps values outside its supported range — the conversion formulas are the only guard. Neither `min_mireds` nor `min_color_temp_kelvin` are valid properties in the template light YAML schema.

The forward conversions (HA → litra) live in the template light handlers. The reverse conversions (litra → HA) live in the `level` and `temperature` templates that read from the status sensor.

> **Coordinated change:** the forward and reverse conversion formulas must move together. If the Litra's brightness or temperature range changes (e.g., a device firmware update or a different model), update both the forward conversion in the template light handlers and the reverse conversion in the `level` / `temperature` templates simultaneously, or HA's reported and commanded values will drift apart.

The lumens-to-HA-brightness reverse conversion introduces a rounding asymmetry of up to ±1 out of 255 (< 0.4% of range) because `litra brightness --percentage` operates in percent while `litra devices --json` reports back in lumens. The drift is imperceptible and self-corrects on the next user adjustment.

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
| Status query | `litra devices --json` is whitelisted as a read-only operation; it returns device metadata including serial number — no write capability exposed |
| sudo scope | `homeassistant` can only run `/opt/homebrew/bin/litra` as `<your_username>`, no password required, nothing else permitted |

---

## Related HA Config

| Artifact | Entity ID | Type |
| --- | --- | --- |
| Office Desk Key Light | `light.office_desk_key_light` | Template light (`configuration.yaml`) |
| Litra Glow Status | `sensor.litra_glow_status` | Command-line sensor (`configuration.yaml`) |
| Control office lights when display camera is being used | `automation.control_office_lights_when_display_camera_is_being_used` | Automation |
| Refresh Litra Glow status on HA start | `automation.refresh_litra_glow_status_on_ha_start` | Automation |

---

## Related Files

| File | Location | Purpose |
| --- | --- | --- |
| Dispatch script | `scripts/litra_dispatch.sh` in this repo; deployed to `/usr/local/bin/litra_dispatch.sh` on Mac Mini | Command whitelist gatekeeper; includes composite `apply_composite` handler |
| sudoers rule | `/etc/sudoers.d/homeassistant-litra` | Allows `homeassistant` to run `litra` as `<your_username>` |
| SSH private key | `/config/.ssh/id_ed25519_litra` | HA's private key for authenticating to Mac Mini |
| SSH public key | `/config/.ssh/id_ed25519_litra.pub` | Corresponding public key |
| known_hosts | `/config/.ssh/known_hosts` | Mac Mini host key fingerprint |
| authorized_keys | `/Users/homeassistant/.ssh/authorized_keys` | HA public key, locked to dispatch script |
| HA config | `/config/configuration.yaml` | Shell command and template light definition |
