# Home Assistant Device & Entity Naming Standard
*Version 1.2 — May 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.2 | May 2026 | Display-name hybrid rule (§5.1–5.2): drop area prefix from primary entities; codify entity registry Name field override; update §6 group examples |
| 1.1 | May 2026 | Added Reminder Naming section (§9) |
| 1.0 | March 2026 | Initial release |

---

## 1. Purpose & Scope

This document defines the standard naming conventions for all devices and entities in the Home Assistant instance. It applies to all integrations including Zigbee (Z2M), Hue, Sonos, Matter, HomeKit, Meross, and others. Consistent naming enables reliable automations, clean dashboards, and easy voice assistant targeting.

> **Automation naming is out of scope here.** Automation entity IDs, friendly names, categories, labels, and area assignment are defined in `standards/automations.md`.

---

## 2. Core Principles

- No redundant prefixes or suffixes — the domain already says what it is
- Location first — entity IDs always start with the area
- No platform names in entity IDs (no `zigbee_`, `hue_`, `homekit_`, etc.)
- Every device must be assigned to an area — no exceptions
- Friendly names are Title Case; entity IDs are snake_case
- Abbreviations only for universally understood terms (e.g., `tv`, `led`)
- Apostrophes are dropped in entity IDs (`avery_room` not `avery_s_room`)

---

## 3. Area Registry

Areas represent physical rooms or zones. Area IDs must be lowercase snake_case with no abbreviations.

| Area ID | Friendly Name | Notes |
|---|---|---|
| `avery_room` | Avery's Room | Drop apostrophe in ID |
| `bathroom` | Bathroom | Hall bathroom |
| `entrance` | Entrance | Entry/foyer |
| `garage` | Garage | |
| `kitchen` | Kitchen | |
| `living_room` | Living Room | |
| `master_bedroom` | Master Bedroom | Rename from `bedroom`; includes master bathroom and master closet |
| `office` | Office | |
| `outside` | Outside | Exterior/patio/porch |
| `utility_room` | Utility Room | |

---

## 4. Device Naming

The device name is set at the integration level (in Z2M, Hue app, etc.) and becomes the basis for entity IDs. It should describe the physical object without redundant type words.

### 4.1 Format

```
[area]_[fixture_or_appliance]
[area]_[fixture_or_appliance]_[qualifier]   # if needed for disambiguation
```

### 4.2 Rules

- Use the area name as the prefix — always
- Describe the physical device, not its function (`ceiling` not `ceiling_lights`)
- For multi-bulb fixtures, the device is the bulb: `office_ceiling_bulb_1`
- Use `_left` / `_right` for physically oriented pairs (side-by-side cabinets, windows, nightstands) — perspective is always **facing the object**; position qualifier always comes **after** the object name (`window_left` not `left_window`, `nightstand_lamp_left` not `left_nightstand_lamp`)
- Use `_1` / `_2` / `_n` when orientation is irrelevant or there are more than two (bulbs in a fixture, accent bars)
- Plural the group name when grouping left/right or numbered siblings: `office_record_cabinets` groups `office_record_cabinet_left` + `office_record_cabinet_right`
- When two devices of the same type exist in a room, qualify by location within the room first (`nightstand`, `desk`, `bed`), then by type, then by number as a last resort
- Fix typos consistently: `humidifier` (not `humidifer`), `turntable` (not `turnable`)

### 4.3 Device Name Examples

| Current Device Name | Proposed Device Name | Reason |
|---|---|---|
| Avery's Room Ceiling Bulb 1 | `avery_room_ceiling_bulb_1` | Drop apostrophe |
| Bathroom Hallway Ceiling Bulb 1 | `bathroom_ceiling_bulb_1` | Remove redundant 'hallway' |
| Master Bedroom Humidifer Plug | `master_bedroom_humidifier_plug` | Fix typo |
| Office Turnable Lights Power Switch | `office_turntable_switch` | Fix typo + simplify |
| Living Room Movie Poster Lights | `living_room_movie_poster` | Drop 'lights' — redundant with domain |
| Master Bedroom Temperature Sensor | `master_bedroom_climate_sensor` | Consistent with mqtt device |
| Avery's Room Door Sensor | `avery_room_door` | Drop `_sensor` suffix |
| Kitchen Water Leak Sensor | `kitchen_leak_sensor` | Drop 'water' — all leak sensors are water |
| Avery's Room Climate Sensor (2nd in room) | `avery_room_climate_nightstand` | Qualify by location within room |

---

## 5. Entity Naming

Entities are auto-generated from device names by HA/Z2M. Override friendly names only when the auto-generated result is wrong or redundant.

### 5.1 Friendly Name Rules

- Title Case for all friendly names
- The domain is **never** included in the friendly name (no `Light`, `Switch`, `Sensor` suffix on primary entities)
- **Default: drop the area prefix** from primary entities. Area context lives in the entity's area assignment, not the name. "Ceiling", not "Office Ceiling"; "Thermostat", not "Living Room Thermostat".
- **Keep a qualifier when bare would be ambiguous** — identical or generic objects that mean nothing alone, or area+object natural-compound phrases. `fan.living_room_ceiling` → "Ceiling Fan" (not "Ceiling", which would collide with a ceiling light entity); `cover.garage_door_garage` → "Garage Door" (natural compound — not just "Door").
- **Strip concatenation artifacts.** HA prepends the device name for `has_entity_name` entities, producing names like "Garage Door Garage" or "Interior Door Door". Override the Name field to correct them.
- Secondary entities (temperature, humidity, power) retain a disambiguating qualifier — bare "Temperature" is meaningless in flat contexts like notifications and logbook. "Motion Temperature", not "Temperature".
- Set display names via the entity registry **Name** field (**Settings → Entities**, pencil icon). This value overrides the entire `friendly_name` everywhere HA surfaces it — dashboards, voice, notifications, logbook, HomeKit — with no device or area name prepended. Area context is preserved by assigning the entity to its area, not by encoding it in the name.
- If the Name field is cleared, HA falls back to `original_name`. Blank is acceptable when `original_name` is already correct.

### 5.2 Primary Entity Suffixes by Domain

| Domain | Primary Entity | Friendly Name Pattern | Example |
|---|---|---|---|
| `light` | Main light | Object name | `Ceiling` |
| `switch` | Primary switch | Object name | `Humidifier` |
| `binary_sensor` (contact) | Door/window state | `[Object]` | `Freezer Door` |
| `binary_sensor` (motion) | Motion detection | `[Device] Motion` | `Night Lamp Motion` |
| `binary_sensor` (moisture) | Leak detection | `[Location] Leak` — keep area; omitting creates ambiguous notifications | `Kitchen Leak` |
| `sensor` (temperature) | Temperature reading | `[Device] Temperature` | `Motion Temperature` |
| `sensor` (humidity) | Humidity reading | `[Device] Humidity` | `Sensor Humidity` |
| `sensor` (battery) | Battery level | `[Device] Battery` | `Motion Battery` |
| `sensor` (power) | Power consumption | `[Device] Power` | `Coke Machine Power` |
| `media_player` | Speaker/TV/player | Object name | `Sonos` |
| `climate` | Thermostat | Object name | `Thermostat` |
| `fan` | Fan | Object name; add qualifier when ambiguous (see §5.1) | `Tower Fan` |
| `cover` | Garage door | Natural compound: keep area+object | `Garage Door` |

### 5.3 What to Suppress / Disable

Many integrations create diagnostic entities that pollute the entity list. These should be disabled (not deleted) in HA:

- LQI / RSSI sensors — useful for troubleshooting but not for daily use
- Device temperature sensors on plugs/bulbs — internal diagnostic, not room temp
- Start-up behavior / color temperature / current level — set once, then disable
- Binary input entities on smart plugs (unless actively used)
- Zigbee controller diagnostic counters (`APS_DATA_*`, `NWK_*`, `MAC_*`, etc.)
- Meross/manufacturer DnD light entities
- Signal strength / sensor protocol sensors from Meross

---

## 6. Light Groups

HA Light Groups replace ZHA groups going forward. The group is the primary entity used in automations and dashboards. Individual bulbs are members only.

### 6.1 Group Entity ID Format

```
light.[area]_[fixture]
```

The group name omits `lights` and `bulbs` — the domain makes it implicit.

### 6.2 Member Entity ID Format

```
light.[area]_[fixture]_bulb_[n]
```

### 6.3 Numbered Member Examples

| Group Entity ID | Friendly Name | Members |
|---|---|---|
| `light.living_room_ceiling` | Ceiling | `living_room_ceiling_bulb_1`, `_2`, `_3` |
| `light.master_bedroom_fan` | Fan Light | `master_bedroom_fan_bulb_1` through `_4` |
| `light.avery_room_ceiling` | Ceiling | `avery_room_ceiling_bulb_1`, `_2` |
| `light.master_closet_ceiling` | Closet Ceiling | `master_closet_ceiling_bulb_1`, `_2` |
| `light.outside_porch` | Porch | `outside_porch_bulb_1`, `_2` |
| `light.bathroom_ceiling` | Ceiling | `bathroom_ceiling_bulb_1`, `_2` |
| `light.garage_ceiling` | Ceiling | `garage_ceiling_bulb_1`, `_2` |
| `light.utility_room_ceiling` | Ceiling | `utility_room_ceiling_bulb_1`, `_2` |
| `light.kitchen_cabinet_accent` | Cabinet Accent | `kitchen_cabinet_accent_bar_1` through `_4` |

### 6.4 Left/Right Member Examples

When devices are physically oriented (facing the object), use `_left` / `_right` for members and pluralize the group name.

| Group Entity ID | Friendly Name | Members |
|---|---|---|
| `light.office_record_cabinets` | Record Cabinets | `office_record_cabinet_left`, `office_record_cabinet_right` |
| `light.master_bedroom_nightstand_lamps` | Nightstand Lamps | `master_bedroom_nightstand_lamp_left`, `master_bedroom_nightstand_lamp_right` |

---

## 7. Special Cases

### 7.1 Devices Without a Fixed Room

- Exterior devices use `outside` as the area prefix: `outside_porch`, `outside_patio`
- Portable/roaming devices use a functional prefix: `portable_sonos`, `roborock_q8`

### 7.2 Manufacturer Entity IDs

Devices that were never renamed before pairing show manufacturer model strings as entity IDs (e.g., `signify_netherlands_b_v_lca003`, `lumi_lumi_sensor_magnet_aq2`). These must be re-paired or renamed in Z2M before migration is considered complete.

### 7.3 Non-Zigbee Integrations

For integrations that auto-generate entity IDs (Hue, Sonos, Ecobee, Roborock), rename at the device level within HA via Settings → Devices. Use entity IDs (not friendly names) in automations.

### 7.4 Hue-Managed Devices

Hue lights should be renamed in the Hue app first — HA will sync the name. Use the following rule to decide between a Hue zone and an HA Light Group:

- **Hue zone** — decorative lights where you want Hue-specific effects or entertainment sync (e.g., pinball cabinet accents, TV bias lighting). Hue zones are managed in the Hue app. Hue zones used primarily for scene access are exempt from the left/right split rule — the zone entity can remain as a single named group (e.g., `light.office_record_cabinet`) even if the underlying bulbs are named `_left` / `_right`.
- **HA Light Group** — functional lighting where you only need on/off/dim/color control (e.g., ceiling bulbs, lamps). HA groups are defined in `configuration.yaml` or via the UI.

### 7.5 Smart Plugs — Name After What's Plugged In

Always name a smart plug after the device connected to it, not the plug itself. The plug is infrastructure; the device is what you control.

- `switch.master_bedroom_humidifier` — not `switch.master_bedroom_smart_plug`
- `switch.avery_room_noise_machine` — not `switch.avery_room_plug_1`

The only exception is a general-purpose outlet with no fixed device, which can be named by location: `switch.office_desk_outlet`.

### 7.6 Lights on Smart Plugs (switch_as_x)

When a light is connected via a smart plug, use the `switch_as_x` helper to expose it as a `light` entity instead of a `switch`. This ensures correct behavior in the UI, voice assistants, and light-based automations.

**Process:**
1. Name the device after what's plugged in (e.g., `Living Room Movie Poster`)
2. Z2M creates `switch.living_room_movie_poster`
3. In HA, create a `switch_as_x` helper to expose it as `light.living_room_movie_poster`
4. Disable the underlying `switch` entity — use the `light` entity everywhere

The entity ID remains the same, only the domain changes from `switch` to `light`. No special naming required — just follow the standard light naming rules.

---

## 8. Quick Reference

| Scenario | Pattern | Example |
|---|---|---|
| Single bulb in fixture | `light.[area]_[fixture]_bulb_[n]` | `light.office_ceiling_bulb_1` |
| Multi-bulb group | `light.[area]_[fixture]` | `light.office_ceiling` |
| Accent/strip light (single) | `light.[area]_[name]` | `light.office_turntable_cabinet_accent` |
| Accent/strip light (left/right pair) | `light.[area]_[name]_left` / `_right` | `light.office_record_cabinet_left` |
| Left/right group | `light.[area]_[name]s` (plural) | `light.office_record_cabinets` |
| Smart plug (non-light) | `switch.[area]_[appliance]` | `switch.master_bedroom_humidifier` |
| Smart plug (light) | `light.[area]_[name]` via switch_as_x | `light.living_room_movie_poster` |
| General purpose outlet | `switch.[area]_[location]_outlet` | `switch.office_desk_outlet` |
| Door sensor | `binary_sensor.[area]_[door_name]` | `binary_sensor.kitchen_freezer_door` |
| Window sensor | `binary_sensor.[area]_window_[side]` | `binary_sensor.master_bedroom_window_left` |
| Leak sensor | `binary_sensor.[area]_leak` | `binary_sensor.kitchen_leak` |
| Climate sensor (temp) | `sensor.[area]_[sensor]_temperature` | `sensor.office_sensor_temperature` |
| Motion sensor | `binary_sensor.[area]_[device]_motion` | `binary_sensor.bathroom_night_lamp_motion` |
| Media player | `media_player.[area]_[brand/type]` | `media_player.living_room_sonos` |
| Vacuum | `vacuum.[model_name]` | `vacuum.roborock_q8_max` |

---

## 9. Reminder Helpers

Reminders are conceptual tasks, not location-bound, so they carry no area prefix. The key is built from the object being acted on and the action performed.

### 9.1 Key Pattern

```
<object>_<action>
```

The key is shared across all helpers for a given reminder. For example, `accord_washed` is the key for all four helpers that track the car wash reminder.

### 9.2 Helper Entity ID Patterns

| Helper | Pattern | Example |
|---|---|---|
| Last-done date | `input_datetime.<key>` | `input_datetime.accord_washed` |
| Interval (days) | `input_number.<key>_offset` | `input_number.accord_washed_offset` |
| Due date | `sensor.<key>_due` | `sensor.accord_washed_due` |
| Overdue flag | `binary_sensor.<key>_overdue` | `binary_sensor.accord_washed_overdue` |

### 9.3 Rules

- **No area prefix** — reminders describe household tasks, not physical locations.
- **`_offset` suffix** on the interval helper — not `_interval` or `_days`. Consistent across all reminders.
- **`_due` suffix** on the due-date sensor — not `_next_due` or `_due_date`.
- **`_overdue` suffix** on the binary sensor — `device_class: problem`. This suffix drives the notification automation's tag and action ID derivation.
- **Object before action** in the key — `accord_washed` not `wash_accord`; `dishwasher_cleaned` not `clean_dishwasher`.
- **Past-tense action** in the key — `washed`, `cleaned`, `changed` — not imperative (`wash`, `clean`, `change`). The key names the event that marks completion.
