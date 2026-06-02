#!/bin/bash
#
# battery_monitor.sh
# Polls ioreg for paired Bluetooth peripheral battery levels and POSTs to HA via webhook.
# Called by: LaunchDaemon com.user.batterymonitor (runs hourly at boot as natethompson)
# Prerequisites: curl; Bluetooth keyboard (ProductID 801) and mouse (ProductID 803) paired
# See: guides/mac_mini_bluetooth_battery.md for full deployment and security documentation
#
# NOTE: This integration was decommissioned in May 2026 when peripherals switched to USB.
# Guide is preserved for reuse if Bluetooth peripherals are reconnected.

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
    http://<ha-ip>:8123/api/webhook/<webhook-id>
