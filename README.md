# homeassistant-configs

A collection of documentation for custom and non-standard Home Assistant integrations, automations, and configurations. These documents capture the full implementation details for integrations that required significant custom work — typically where no native HA integration exists or where a unique environment constraint required a non-obvious solution.

## Contents

| Document | Description |
|---|---|
| [Logitech Litra Glow Integration](litra-glow-ha-integration.md) | Exposes a Logitech Litra Glow key light as a native HA light entity via SSH and the `litra-rs` CLI tool |

## Scope

This repository contains documentation only — no actual HA configuration files, secrets, or environment-specific credentials. All documents use placeholder values (e.g. `<your_username>`, `<mac-mini-ip>`) where environment-specific values are required.

## Environment

- Home Assistant OS
- Mac Mini (macOS) running the HA companion app
- Zigbee devices via ZHA (Zigbee Home Automation)
