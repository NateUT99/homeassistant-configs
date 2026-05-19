# homeassistant-configs

Version-controlled documentation, standards, and supporting scripts for a personal Home Assistant instance. The repository serves three purposes:

1. **Reference standards** — conventions that govern how the HA instance is structured
2. **Implementation guides** — full technical documentation for custom integrations and non-obvious configurations, written for reproducibility
3. **Supporting scripts** — shell scripts and templates that live outside HA's entity registry

## Contents

### Standards

| Document | Description |
|---|---|
| [Naming Standard](standards/naming.md) | Entity ID and friendly name conventions for all devices and helpers |

### Guides

| Document | Description |
|---|---|
| [Adaptive Lighting](guides/adaptive_lighting.md) | AL configuration, curve design, and MQTT-based pre-staging procedure for Zigbee bulbs |
| [Hue Sync & TV Bias Lighting](guides/hue_sync.md) | Living Room bias light and Hue Sync Box automation system |
| [Logitech Litra Glow](guides/litra_glow.md) | Key light exposed as a native HA light entity via SSH and the `litra-rs` CLI |
| [Reminder System](guides/reminders.md) | Recurring maintenance reminders with actionable iOS notifications and automatic completion loop |

### Scripts

`scripts/` is reserved for shell scripts invoked by HA's `shell_command` integration and other non-UI-editable artifacts. Currently empty.

## Scope

This repository is **not** a complete mirror of the HA instance. Automations, scripts, scenes, helpers, dashboards, and the entity and area registries all live in HA and are not duplicated here. Only artifacts touched as part of ongoing work are added.

Documents use placeholder values (e.g. `<your_username>`, `<mac-mini-ip>`) wherever environment-specific values are required.

## Environment

- Home Assistant OS on Home Assistant Green
- Mac Mini (macOS, always-on) running the HA Companion App; secondary MacBook Pro
- Zigbee devices via Zigbee2MQTT (Sonoff EFR32MG24 coordinator)
- Hue devices via Hue bridge (separate channel from Z2M)
