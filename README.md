# homeassistant-configs

Version-controlled documentation, standards, and supporting scripts for a personal Home Assistant instance. This repo is **not** a complete mirror of HA — see [Source of Truth](CLAUDE.md#source-of-truth) in `CLAUDE.md` for the full breakdown. It serves four purposes:

1. **Reference standards** — conventions that govern how the HA instance is structured
2. **Implementation guides** — architecture and design-decision documentation for custom integrations, written for reproducibility and community sharing
3. **Supporting scripts** — shell scripts and Python utilities that live outside HA's entity registry
4. **Living HA mirror** (`ha/`) — version-controlled copies of every automation, script, and HA package, kept in sync with HA each session

See `CLAUDE.md` for full project conventions (working preferences, commit discipline, HA access boundaries) and `LESSONS.md` for hard-won gotchas worth checking before troubleshooting something that looks "obviously" broken.

## Contents

### Standards

| Document | Description |
|---|---|
| [Automation](standards/automations.md) | Automation naming, categories, labels, area assignment, and YAML content requirements |
| [Naming](standards/naming.md) | Entity ID and friendly name conventions for all devices and helpers |
| [Dashboards](standards/dashboards.md) | Dashboard design standard — Bubble Card as primary, inline toggle patterns |
| [Documentation](standards/documentation.md) | How every document in this repo is structured and written — Reference Standards vs. Implementation Guides |

### Guides

| Document | Description |
|---|---|
| [Adaptive Lighting](guides/adaptive_lighting.md) | Two-instance AL setup for the Inovelli canopy ceiling-fan lights, with Matter `OnLevel` pre-staging for wall-paddle turn-ons |
| [Cable Modem Auto-Recovery](guides/cable_modem_recovery.md) | Power-cycles the cable modem via smart plug on sustained internet outage, with a capped retry count and a maintenance override |
| [Chime TTS](guides/chime_tts.md) | HACS-based chime-prefixed TTS via HomePod notify services; standard delivery mechanism for all TTS announcements |
| [Energy Monitoring](guides/energy_monitoring.md) | Whole-home electricity monitoring via Rainforest EAGLE-3 smart-meter HAN link, feeding the HA Energy Dashboard |
| [Generac Generator Monitoring](guides/generac.md) | Generac MobileLink cloud integration plus a trigger-based sensor tracking last-run time |
| [Home Alarm](guides/home_alarm.md) | Alarm perimeter detection, camera siren, contextual push notifications, and camera snapshot on person detection |
| [Hue Sync & TV Bias Lighting](guides/hue_sync.md) | Living Room bias light and Hue Sync Box automation system |
| [HVAC Daily Usage Tracking](guides/hvac_monitoring.md) | Derives daily HVAC runtime, cycle count, and average cycle length from thermostat `hvac_action` via a `history_stats` chain |
| [Inovelli Switches](guides/inovelli_switches.md) | Shared notification-LED bar pattern and the ceiling-fan-canopy device pattern for Matter-over-Thread Inovelli switches |
| [Laundry Automation](guides/laundry_automation.md) | LG ThinQ washer/dryer monitoring with per-appliance status state machine, repeating TTS alerts, acknowledge flow, and mobile dashboard chips |
| [Logitech Litra Glow](guides/litra_glow.md) | Key light exposed as a native, push-updated HA light via a macOS agent and the `litra` custom integration |
| [iOS Live Activities](guides/live_activities.md) | `script.household_live_activity`, the single dispatch point for Lock Screen / Dynamic Island cards across laundry and vacuum |
| [Mac Mini Bluetooth Peripheral Battery Monitor](guides/mac_mini_bluetooth_battery.md) | Shell script polling ioreg for Bluetooth peripheral battery levels, posted to HA via webhook (decommissioned) |
| [Mobile Dashboard](guides/mobile_dashboard.md) | `mobile-home` Bubble Card dashboard — chip strip, feature pop-ups, and room tile layout |
| [Outdoor Air Quality Alerting](guides/outdoor_air_quality_alerting.md) | WAQI-based AQI monitoring with TTS and push notification alerts for poor air quality and clearance announcements |
| [Presence Tracking](guides/presence_tracking.md) | HomeKit geofence-driven device trackers via Template Helper `device_tracker` entities, no MQTT required |
| [Reminder System](guides/reminders.md) | Recurring maintenance reminders with actionable iOS notifications and automatic completion loop |
| [Vacuum Cleaning Routine](guides/vacuum_cleaning_routine.md) | Scheduled and presence-driven cleaning/mopping passes for the Roborock Q8 Max Plus |

### Scripts

`scripts/` contains shell scripts invoked by HA's `shell_command` integration, Python utilities, and other non-UI-editable artifacts.

| Script | Purpose |
|---|---|
| [battery_monitor.sh](scripts/battery_monitor.sh) | Polls ioreg for Bluetooth peripheral battery levels and POSTs to HA webhook (decommissioned May 2026) |
| [matter_write_attribute.py](scripts/matter_write_attribute.py) | Reads or writes a single Matter attribute via the HA Matter Server WebSocket API, for attributes HA's Matter integration doesn't surface |

### HA Mirror (`ha/`)

`ha/automations/` and `ha/scripts/` are downstream, human-readable copies of every automation and script — HA remains authoritative, updated in the same session as any change, for recovery and diffing. `ha/packages/` runs the opposite direction: the repo is authoritative there, and each file is deployed to `/config/packages/` on the host via `scp`. See [ha/README.md](ha/README.md) for the full sync rule and file naming convention.

### Snapshot

`snapshot/2026-07-27-pre-move/` is a frozen, read-only export of the old apartment's HA instance captured before the 2026 house move. It's a rebuild reference — consult it freely when replicating prior functionality, but never write to it; entity IDs and area names are from the old house.

## Scope

Automations, scripts, and packages are mirrored in `ha/` once they're touched as part of ongoing work — this repo is not retroactively backfilled with everything already in HA. Helpers, scenes, dashboards, and the entity and area registries live in HA only and are not duplicated here (dashboards are documented in guides where relevant, e.g. [Mobile Dashboard](guides/mobile_dashboard.md)).

Documents use placeholder values (e.g. `<your_username>`, `<mac-mini-ip>`) wherever environment-specific values are required.

## Environment

- Home Assistant OS on Home Assistant Green
- Mac Mini (macOS, always-on) running the HA Companion App, referenced as `mac-mini`; secondary MacBook Pro (`work-laptop`)
- Zigbee devices managed via ZHA (USB coordinator)
- Thread network via the OpenThread Border Router core add-on, joined to the same Thread fabric as the Apple Thread network (HomePods) — Thread and Matter-over-Thread devices are reachable from both HA and Apple Home
- Matter support via the official Matter Server core add-on
