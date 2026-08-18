# homeassistant-configs

Version-controlled documentation, standards, and supporting scripts for a personal Home Assistant instance. The repository serves three purposes:

1. **Reference standards** — conventions that govern how the HA instance is structured
2. **Implementation guides** — full technical documentation for custom integrations and non-obvious configurations, written for reproducibility
3. **Supporting scripts** — shell scripts and templates that live outside HA's entity registry

## Contents

### Standards

| Document | Description |
|---|---|
| [Automation](standards/automations.md) | Automation naming, categories, labels, area assignment, and YAML content requirements |
| [Naming](standards/naming.md) | Entity ID and friendly name conventions for all devices and helpers |

### Guides

| Document | Description |
|---|---|
| [Adaptive Lighting](guides/adaptive_lighting.md) | AL configuration, curve design, and MQTT-based pre-staging procedure for Zigbee bulbs |
| [Chime TTS](guides/chime_tts.md) | HACS-based chime-prefixed TTS via HomePod notify services; standard delivery mechanism for all TTS announcements |
| [Home Alarm](guides/home_alarm.md) | Alarm perimeter detection, camera siren, contextual push notifications, and camera snapshot on person detection |
| [Hue Sync & TV Bias Lighting](guides/hue_sync.md) | Living Room bias light and Hue Sync Box automation system |
| [Laundry Automation](guides/laundry_automation.md) | LG ThinQ washer/dryer monitoring with per-appliance status state machine, repeating TTS alerts, acknowledge flow, and mobile dashboard chips |
| [Logitech Litra Glow](guides/litra_glow.md) | Key light exposed as a native HA light entity via SSH and the `litra-rs` CLI |
| [Mac Mini Bluetooth Peripheral Battery Monitor](guides/mac_mini_bluetooth_battery.md) | Shell script polling ioreg for Bluetooth peripheral battery levels, posted to HA via webhook (decommissioned) |
| [Mobile Dashboard](guides/mobile_dashboard.md) | `mobile-home` Bubble Card dashboard — chip strip, feature pop-ups, and room tile layout |
| [Outdoor Air Quality Alerting](guides/outdoor_air_quality_alerting.md) | WAQI-based AQI monitoring with TTS and push notification alerts for poor air quality and clearance announcements |
| [Presence Tracking](guides/presence_tracking.md) | HomeKit geofence-driven device trackers via Template Helper `device_tracker` entities, no MQTT required |
| [Reminder System](guides/reminders.md) | Recurring maintenance reminders with actionable iOS notifications and automatic completion loop |

### Scripts

`scripts/` contains shell scripts invoked by HA's `shell_command` integration and other non-UI-editable artifacts.

| Script | Purpose |
|---|---|
| [battery_monitor.sh](scripts/battery_monitor.sh) | Polls ioreg for Bluetooth peripheral battery levels and POSTs to HA webhook (decommissioned May 2026) |
| [litra_dispatch.sh](scripts/litra_dispatch.sh) | SSH dispatch script for Litra Glow key light control via the `litra-rs` CLI |

## Scope

This repository is **not** a complete mirror of the HA instance. Automations, scripts, scenes, helpers, dashboards, and the entity and area registries all live in HA and are not duplicated here. Only artifacts touched as part of ongoing work are added.

Documents use placeholder values (e.g. `<your_username>`, `<mac-mini-ip>`) wherever environment-specific values are required.

## Environment

- Home Assistant OS on Home Assistant Green
- Mac Mini (macOS, always-on) running the HA Companion App; secondary MacBook Pro
- Zigbee devices via Zigbee2MQTT (Sonoff EFR32MG24 coordinator)
- Hue devices via Hue bridge (separate channel from Z2M)
- SkyConnect ZBT-1 (Thread firmware) as Thread border router, joined to the same Thread fabric as the Apple Thread network (HomePods)
- Matter/HomeKit bridging via Matter Hub (RiDDiX fork) add-on
