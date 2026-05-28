# Mac Mini Bluetooth Peripheral Battery Monitor

*Last updated: May 2026*

## Overview

A shell script running on the Mac Mini polls `ioreg` for the battery level of paired Bluetooth peripherals (keyboard and mouse), then POSTs the values to a Home Assistant webhook. HA stores the readings in two trigger-based template sensors — `sensor.mac_mini_keyboard_battery` and `sensor.mac_mini_mouse_battery` — with `device_class: battery` so they slot naturally into the Battery Alerts dashboard card and low-battery automations.

This integration was decommissioned in May 2026 when the keyboard and mouse were switched to USB connections (no battery to report). The guide is preserved for reuse if Bluetooth peripherals are reconnected.

---

## Architecture

```
Mac Mini
└── launchd (system daemon, runs hourly at boot)
    └── battery_monitor.sh
        └── ioreg -r -l -k "BatteryPercent"
            ├── ProductID 801 → keyboard battery %
            └── ProductID 803 → mouse battery %
                └── curl POST /api/webhook/<webhook-id>
                    └── Home Assistant
                        └── trigger-based template sensors
                            ├── sensor.mac_mini_keyboard_battery
                            └── sensor.mac_mini_mouse_battery
```

**Key design decisions:**

- Uses `ioreg` (IO Registry) rather than any third-party tool — no extra dependencies.
- A webhook trigger (not polling) means HA only updates when the Mac actually posts. Values persist across HA restarts via recorder.
- ProductID filtering (`grep -B 10 '"ProductID" = 801'`) is more reliable than product name matching, which can vary by firmware version.
- Running as a LaunchDaemon with `UserName` set keeps Bluetooth IO Registry access while starting before login. The original user-space LaunchAgent only ran while `natethompson` was logged in.

---

## Prerequisites

- Mac Mini on the same LAN as HA, with a static or DHCP-reserved IP
- Bluetooth keyboard and mouse paired with the Mac Mini
- HA webhook trigger configured (see step 3 below)
- `curl` available (ships with macOS)

---

## Steps

### Step 1 — Identify Bluetooth peripheral ProductIDs

The ProductIDs `801` (keyboard) and `803` (mouse) are Apple Magic Keyboard and Magic Mouse identifiers. Confirm yours before deploying:

```bash
ioreg -r -l -k "BatteryPercent" | grep -E '"ProductID"|"BatteryPercent"'
```

Each device block will show its `ProductID` followed by `BatteryPercent`. Update the grep arguments in the script if your IDs differ.

### Step 2 — Create the script

Place the script at a system-accessible path:

```bash
sudo mkdir -p /usr/local/bin
sudo nano /usr/local/bin/battery_monitor.sh
```

Script contents:

```bash
#!/bin/bash

IOREG_OUTPUT=$(ioreg -r -l -k "BatteryPercent")

KEYBOARD_BATTERY=$(echo "$IOREG_OUTPUT" | grep -B 10 '"ProductID" = 801' | grep '"BatteryPercent"' | awk -F' = ' '{print $2}')

MOUSE_BATTERY=$(echo "$IOREG_OUTPUT" | grep -A 50 '"ProductID" = 803' | grep '"BatteryPercent"' | head -1 | awk -F' = ' '{print $2}')

# Skip POST if either value is empty (devices not connected via Bluetooth)
if [[ -z "$KEYBOARD_BATTERY" || -z "$MOUSE_BATTERY" ]]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - One or more devices not found via ioreg, skipping POST"
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Keyboard: ${KEYBOARD_BATTERY}%, Mouse: ${MOUSE_BATTERY}%"

curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{\"keyboard_battery\": $KEYBOARD_BATTERY, \"mouse_battery\": $MOUSE_BATTERY}" \
    http://<ha-ip>:8123/api/webhook/-X_ghx69lXVTPYa3VyZP9_s_p
```

```bash
sudo chmod +x /usr/local/bin/battery_monitor.sh
```

> **Note:** The empty-value guard (`if [[ -z ... ]]`) is critical. Without it, the POST sends malformed JSON (`{"keyboard_battery": , "mouse_battery": }`) whenever a device is USB-connected or not found, which causes HA to log a JSON decode error for every hourly run.

### Step 3 — Configure HA (webhook + template sensors)

Add the following block to `configuration.yaml`. The webhook ID can be any string — use the one shown to match the existing curl command in the script, or generate a new one and update the script.

```yaml
template:
  - trigger:
      - platform: webhook
        webhook_id: "-X_ghx69lXVTPYa3VyZP9_s_p"
    sensor:
      - name: "Mac Mini Keyboard Battery"
        unique_id: mac_mini_keyboard_battery_level
        state: "{{ trigger.json.keyboard_battery }}"
        unit_of_measurement: "%"
        device_class: battery
        state_class: measurement

      - name: "Mac Mini Mouse Battery"
        unique_id: mac_mini_mouse_battery_level
        state: "{{ trigger.json.mouse_battery }}"
        unit_of_measurement: "%"
        device_class: battery
        state_class: measurement
```

Restart HA (or reload template configuration) after adding this block.

### Step 4 — Create the LaunchDaemon

```bash
sudo nano /Library/LaunchDaemons/com.user.batterymonitor.plist
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.batterymonitor</string>
    <key>UserName</key>
    <string>natethompson</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/battery_monitor.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/battery_monitor.out</string>
    <key>StandardErrorPath</key>
    <string>/var/log/battery_monitor.err</string>
</dict>
</plist>
```

```bash
sudo chown root:wheel /Library/LaunchDaemons/com.user.batterymonitor.plist
sudo chmod 644 /Library/LaunchDaemons/com.user.batterymonitor.plist
sudo launchctl load /Library/LaunchDaemons/com.user.batterymonitor.plist
```

> **`UserName: natethompson`:** Running under the named user (rather than root) preserves the Bluetooth IO Registry context that `ioreg` needs to see paired device battery levels. If readings come back empty as a daemon but work in a user terminal session, this is why — try adding `SessionCreate: true` to the plist as a fallback.

### Step 5 — Test

Trigger a manual run and check output:

```bash
sudo launchctl start com.user.batterymonitor
cat /var/log/battery_monitor.out
```

Confirm `sensor.mac_mini_keyboard_battery` and `sensor.mac_mini_mouse_battery` update in HA within a few seconds.

---

## Security Summary

| Control | Detail |
|---|---|
| Transport | Plain HTTP to LAN IP — acceptable for a trusted home network; use HTTPS with a valid cert if HA is exposed externally |
| Authentication | Webhook ID functions as a shared secret — keep it out of public repos |
| Least privilege | Script reads IO Registry (no elevated permissions needed); LaunchDaemon runs as `natethompson`, not root |
| Worst-case exposure | Attacker who obtains the webhook ID can POST arbitrary battery values — no device control is possible via this endpoint |

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Mac Mini Keyboard Battery | `sensor.mac_mini_keyboard_battery` | Template sensor (webhook-triggered) |
| Mac Mini Mouse Battery | `sensor.mac_mini_mouse_battery` | Template sensor (webhook-triggered) |

---

## Related Files

| File | Location | Purpose |
|---|---|---|
| `battery_monitor.sh` | `/usr/local/bin/battery_monitor.sh` on mac-mini | Polls ioreg and POSTs to HA |
| `com.user.batterymonitor.plist` | `/Library/LaunchDaemons/` on mac-mini | Schedules the script hourly at boot |
| `configuration.yaml` | HA `/config/configuration.yaml` | Defines the webhook trigger and template sensors |

---

## Troubleshooting

**`ioreg` returns empty for a device** — Confirm the device is Bluetooth-connected (not USB). Run `ioreg -r -l -k "BatteryPercent" | grep -E '"ProductID"|"BatteryPercent"'` in a terminal to verify the device appears and confirm its ProductID.

**Sensor stops updating after HA restart** — Trigger-based template sensors lose their state on restart and only update on the next POST. Force an immediate update with `sudo launchctl start com.user.batterymonitor`.

**LaunchDaemon finds no devices** — If `ioreg` battery reads require a logged-in GUI session, add `<key>SessionCreate</key><true/>` to the plist. This is uncommon for IOKit reads but can affect some macOS versions.
