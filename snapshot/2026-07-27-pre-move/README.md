# Pre-Move HA Config Snapshot — 2026-07-27

This directory is a point-in-time export of the Home Assistant instance at the old
apartment, captured before the house move. It is a **frozen archive** — HA remains
the live source of truth for everything that was still running.

## Purpose

The primary rebuild reference for the new house. Automations and scripts can be
pasted back into a fresh HA instance and adjusted for new entity IDs and room names.
Infrastructure (radio stack, Matter Hub, presence logic) is documented in `guides/`.

## What's here

| Dir / file | Contents | Source |
|---|---|---|
| `automations/` | One YAML file per automation (83 total) | MCP export |
| `scripts/` | One YAML file per script (12 total) | MCP export |
| `scenes/` | One YAML file per scene (12 total) | MCP export |
| `dashboards/` | Lovelace dashboard configs | MCP export |
| `helpers.yaml` | All storage-based helpers (input_boolean, input_select, etc.) | MCP export |
| `labels.yaml` | All 22 labels with metadata | MCP export |
| `categories.yaml` | Automation categories | MCP export |
| `areas.yaml` | Area and floor registry | MCP export |
| `configuration.yaml` | Root HA config (not reachable via MCP) | SSH pull — TODO |
| `packages/` | Package YAML files including template sensors | SSH pull — TODO |

## Export progress (resume point if session interrupted)

- [x] Directory structure + README
- [ ] Automations (83)
- [ ] Scripts (12)
- [ ] Scenes (12)
- [ ] Helpers
- [ ] Dashboards
- [ ] Labels / categories / areas
- [ ] configuration.yaml + packages (SSH pull — separate step)

## Known changes from this snapshot at the new house

- **Areas:** New structure — two floors (Main, Basement). New areas: Dining Area,
  Master Bathroom, Pantry, Arcade (basement). "Bathroom" → two baths (Bathroom,
  Master Bathroom). Outside retained.
- **Smart bulbs → smart switches:** Ceiling fan rooms (Master Bedroom, Living Room,
  Office, Avery's Room) migrating to Inovelli switch + fan module. Other rooms TBD.
  Entity IDs will change; automations referencing old light entities need updating.
- **Hue Sync:** Decommissioned at move. Planned relocation to Arcade (basement) with
  new TV, PS5, and Hue gradient strip — rebuild from `guides/hue_sync.md`.
- **Laundry:** LG ThinQ washer/dryer moving with the house. Guide at
  `guides/laundry_automation.md` remains valid.

## Security note

`secrets.yaml` and any credential material are **not in this snapshot**. They live
only in the off-box full backup `.tar`. Do not commit secrets to this repo.
