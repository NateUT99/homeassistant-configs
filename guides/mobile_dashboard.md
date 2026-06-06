# Mobile Dashboard 3.0

*Version 0.1 — Last updated: June 2026*

---

## Overview

Mobile 3.0 (`mobile-3`) is the primary mobile dashboard for the HA instance, built to replace Mobile 2.0 (which relied on Bubble Card). It targets the iOS Companion App and aims for an Apple Home-style clarity — enough ambient context at a glance, with a tap to drill into any room or device. The visual layer is Mushroom Cards throughout; no Bubble Card, no kiosk-mode. Adaptive Lighting manages all brightness and color temperature, so no brightness sliders appear anywhere.

Mobile 2.0 remains available as a fallback. Retirement is tracked separately, pending desktop dashboard completion.

---

## Architecture

```
mobile-3 (storage-mode dashboard, url_path: mobile-3)
│
├── Home (sections, max_columns=1)
│   │
│   ├── [chip strip section — no title]
│   │   │
│   │   ├── Strip 1: Environment    ← always 3 chips
│   │   │   ├── Weather [icon+temp]          dynamic MDI icon (mdi:weather-<state>); °F → more-info
│   │   │   ├── AQI [green/accent/red]       mdi:smog; green ≤100 / accent 101–125 / red ≥126 → more-info
│   │   │   └── Thermostat [grey/orange/blue] grey=idle, orange=heating, blue=cooling; current temp → /climate
│   │   │
│   │   ├── Strip 2: Status & Alerts  ← 4 chips always visible; alert chips append when active
│   │   │   ├── Alarm status [green]        normal state → Away/Night/Home/Off; hides during alert
│   │   │   │   Alarm alert [red/orange]    alert state → triggered/pending=red, arming=orange; mutually exclusive with status
│   │   │   ├── Vacuum [grey/orange/green/red]  grey=not run, orange=running, green=ran+clear, red=ran+maintenance due → /vacuum
│   │   │   ├── Garage [green]              closed → more-info; hides when open (alert chips take over)
│   │   │   │   Garage [red/orange]         open + sleeping/away=red, open + home/awake=orange → close w/ confirm
│   │   │   ├── Reminders OK [green]        hidden when any overdue; mutually exclusive with overdue count
│   │   │   │   Overdue reminders [red]     count > 0 → /reminders; count if 2+
│   │   │   ├── Water leak [red]            any of 4 sensors not off → /water-leaks; count if 2+
│   │   │   ├── Freezer open [red]          kitchen_freezer_door_contact not off → more-info
│   │   │   ├── Exterior door [red]         any of 3 doors open AND (sleeping OR away) → count if 2+
│   │   │   ├── Exterior door [orange]      any of 3 doors open AND home AND awake → count if 2+
│   │   │   ├── Garage open [red]           not closed AND (sleeping OR away) → tap closes w/ confirm
│   │   │   ├── Garage open [orange]        not closed AND home AND awake → tap closes w/ confirm
│   │   │   └── Trash pickup [red]          trash_pickup_pending on → icon-only
│   │   │
│   │   ├── Strip 3: Modes          ← conditional, all hidden when inactive
│   │   │   ├── Avery sleeping      (input_boolean.avery_sleeping, if not everyone sleeping)
│   │   │   ├── Everyone sleeping   (input_boolean.everyone_sleeping)
│   │   │   ├── Light sync          (sync box + TV both on)
│   │   │   ├── Movie mode          (TV on)
│   │   │   └── Quiet mode          (TV on)
│   │   │
│   │   └── Strip 4: Presence       ← always visible
│   │       ├── Nate                (person.nate, entity picture, shows location state)
│   │       └── Guest               (person.guest, hold-to-toggle input_boolean.guest_mode)
│   │
│   ├── Rooms     ← 2-col mushroom-light-card grid, tap=subview, hold=toggle
│   │   ├── Living Room     light.living_room_fan
│   │   ├── Master Bedroom  light.master_bedroom_fan
│   │   ├── Avery's Room    light.avery_room_ceiling
│   │   ├── Office          light.office_ceiling
│   │   ├── Kitchen         light.kitchen_ceiling
│   │   ├── Bathroom        light.bathroom_hallway_ceiling
│   │   ├── Garage          cover.garage_door (cover-card fallback)
│   │   └── Outside         sensor.outside_temperature (entity-card fallback)
│
├── Living Room   (subview — reference implementation)
│   ├── Lights    ceiling, movie posters, status lamp, tv lights
│   ├── Fan       fan.living_room_ceiling
│   ├── Climate   climate.living_room_thermostat
│   ├── Media     Apple TV + Sonos
│   └── Sensors   motion/occupancy
│
├── Water Leaks   (utility subview — tap target for water alert chip)
│   └── Sensors   2×2 grid: kitchen, bathroom, master bath, utility
│
├── Reminders     (utility subview)
│   └── Household        car, coffee grinder, dishwasher, disposal,
│                        razor, toothbrushes, washer, water filter
│
├── Vacuum        (utility subview)
│   ├── Map          conditional picture-entity (no section title)
│   ├── Controls     native tile with vacuum-commands feature (no section title; before Status)
│   ├── Status       state, battery, area, duration; Current Room when cleaning
│   ├── Mop Settings mop intensity, mode, water supply — section hidden when mop not attached
│   └── Consumables  filter, main brush, side brush, sensor (hours remaining; tap to reset w/ confirmation)
│
├── Climate       (utility subview — tap target for thermostat chip)
│   │             Badges: Inside temp+humidity (blue); tap shows per-room breakdown
│   ├── Controls  thermostat tile + comfort select (home/sleep/away) + clear hold
│   │             + HVAC Runtime subtitle + today's cooling/heating summary card
│   └── HVAC History  (collapsed by default) 28-day line chart (cooling + heating)
│
└── [pending subviews]
    Master Bedroom, Avery's Room, Office, Kitchen, Bathroom, Garage, Outside
```

The chip strip section has no title. This is intentional: HA renders an empty section heading as zero-height when no title is set, so the block collapses cleanly when the house is quiet.

---

## Prerequisites

- Home Assistant 2025.9 or later (sections view, tile features)
- Mushroom Cards installed via HACS (`lovelace-mushroom`)
- card-mod installed via HACS (`lovelace-card-mod`)
- Adaptive Lighting integration active (justifies no-slider rule)

---

## Chip Strip Design

### Strip 1 — Environment

Always-visible ambient context strip. Three chips, always present; no conditional logic.

**Weather** — Dynamic icon using `mdi:weather-{{ states('weather.apartment') }}` (with a special-case for `partlycloudy` → `mdi:weather-partly-cloudy`). Content shows current temperature in °F from `state_attr('weather.apartment', 'temperature')`. Taps to `more-info` on `weather.apartment`.

**AQI** — `mdi:smog` with conditional `icon_color` driven by `sensor.toledo_ohio_usa_air_quality_index`: green ≤ 100, accent 101–125, red ≥ 126. Content shows the raw number only — the smog icon provides sufficient context. Taps to `more-info` on the sensor. Using a template chip (not an entity badge) lets `icon_color` be set via Jinja, which also fixes the gap in the old badge approach where AQI = 125 was uncovered.

**Thermostat** — `mdi:home-thermometer` with `icon_color` from `hvac_action`: blue = cooling, orange = heating, grey = idle. Content shows current indoor temperature. Taps to the Climate subview.

### Strip 2 — Status & Alerts

A single strip combining persistent status indicators with conditional alert chips. Four chips are always visible (the status anchors); alert chips append to the right when active. In a quiet house the strip shows four chips; in an alert state the count grows without disturbing the anchored positions.

**Ordering rationale:** status chips are fixed at positions 1–4 so the strip never looks empty. Alert chips occupy positions 5+ and only appear when needed.

**Alarm status / Alarm alert** — Position 1; mutually exclusive pair. Alarm status (green `mdi:shield-home`, "Away" / "Night" / "Home" / "Off") is always visible during normal operation. It hides when the alarm transitions to `triggered`, `pending`, or `arming`, at which point the alarm alert chip (`mdi:shield-alert`, red or orange) takes its place at position 1.

**Vacuum** — Position 2; always visible. Four states driven by two template fields (`icon` and `icon_color`): cleaning/returning/paused → orange `mdi:robot-vacuum`; ran today AND `binary_sensor.roborock_maintenance_required` on → red `mdi:robot-vacuum-alert`; not run today → grey `mdi:robot-vacuum-off`; ran today and all clear → green `mdi:robot-vacuum`. Taps to the Vacuum subview.

**Garage** — Position 3; three mutually exclusive states. Green `mdi:garage` when closed (taps to `more-info`). Replaced by `mdi:garage-open-variant` when open: red when sleeping or away (tap closes with confirmation), orange when home and awake (tap closes with confirmation). Hold always shows `more-info`.

**Reminders OK / Overdue reminders** — Position 4; mutually exclusive pair. Green `mdi:calendar-check` when `number.overdue_reminders_count` is below 1. Replaced by a red `mdi:calendar-alert` count chip (taps to `/mobile-3/reminders`) when any reminder is overdue. Count label shown only when 2 or more are overdue.

**Water leaks** — Conditional. A single chip replaces four individual sensors via OR condition (`state_not: "off"`). `state_not: "off"` is intentional: `unknown` (sensor offline) also triggers as a conservative default for water detection. Taps to the Water Leaks subview.

**Freezer door** — Conditional. No contextual gate — always alert-worthy regardless of time or presence.

**Exterior doors** — Two conditional chips, mutually exclusive. Red when any of three sensors is open AND (sleeping OR nobody home). Orange when any is open AND home AND awake (informational). Count shown when 2 or more are open. Sensors: `binary_sensor.garage_interior_door_contact`, `binary_sensor.entrance_front_door_contact`, `binary_sensor.office_sliding_door_contact`.

**Garage door** — Two conditional chips, mutually exclusive. Red when open AND (sleeping OR away). Orange when open AND home AND awake. Both use tap-to-close with confirmation; hold shows `more-info`.

**Trash pickup** — Conditional. Icon-only; `input_boolean.trash_pickup_pending` is the gate.

### Strip 3 — Modes

Contextual indicators for active household modes. All conditional; the strip may be entirely empty.

- **Avery sleeping** — visible when `input_boolean.avery_sleeping` is on AND `input_boolean.everyone_sleeping` is off (prevents duplicate when both fire)
- **Everyone sleeping** — `input_boolean.everyone_sleeping`
- **Light sync** — visible when both `switch.living_room_sync_box_power` and `media_player.living_room_tv` are on
- **Movie mode** — `input_boolean.movie_mode`, gated on TV being on
- **Quiet mode** — `input_boolean.sonos_night_mode`, gated on TV being on; uses yellow rather than green

### Strip 4 — Presence

Always visible. Nate's chip uses `use_entity_picture: true`. Guest chip disables tap (preventing accidental activation) and uses hold-to-toggle `input_boolean.guest_mode`.

---

## Room Tiles

Eight rooms in a 2-column grid. Primary entity is the main ceiling light for the room. No sliders — Adaptive Lighting owns brightness. Tap navigates to the room's subview; hold toggles the primary light.

| Room | Primary entity | Subview path |
|---|---|---|
| Living Room | `light.living_room_fan` | `living-room` |
| Master Bedroom | `light.master_bedroom_fan` | `master-bedroom` |
| Avery's Room | `light.avery_room_ceiling` | `averys-room` |
| Office | `light.office_ceiling` | `office` |
| Kitchen | `light.kitchen_ceiling` | `kitchen` |
| Bathroom | `light.bathroom_hallway_ceiling` | `bathroom` |
| Garage | `cover.garage_door` (cover-card fallback) | `garage` |
| Outside | `sensor.outside_temperature` (entity-card fallback) | `outside` |

> **Naming gap:** `light.living_room_fan` and `light.master_bedroom_fan` embed the device type (`fan`) rather than being location-first per `standards/naming.md`. These IDs are used as-is; a rename pass is tracked separately.

---

## Living Room Subview (Reference Implementation)

The Living Room subview is the reference pattern for all room subviews. It uses native `tile` cards throughout — Mushroom cards appear only in the Consumables and Climate runtime cards where Jinja `icon_color` is required (see Vacuum and Climate subviews). Five sections:

- **Lights** — 2-col grid of `tile` cards, one per light entity; no sliders
- **Fan** — `tile` with `fan-speed` feature
- **Climate** — `tile` with `climate-hvac-modes` and `target-temperature` features
- **Media** — Apple TV and Sonos, each a `tile` with `media-player-controls` feature (no explicit `controls` list — HA auto-detects supported controls per entity; specifying unsupported controls causes a configuration error badge)
- **Sensors** — `tile` per binary sensor (motion, occupancy, door, etc.)

Pending room subviews follow this same section structure, including only sections that apply.

---

## Water Leaks Subview

Tap target for the grouped water alert chip on Strip 2. Displays all four water leak sensors in a 2×2 grid using native `tile` cards. The tile card handles the `moisture` device class natively, providing appropriate icons and state coloring.

---

## Reminders Subview

Two sections:

**Household** — 2-col grid of `mushroom-template-card` for each tracked household task. Each card:
- Shows the task name and formatted due date as secondary text (`strptime().strftime('%B %-d, %Y')`)
- Icon is red when overdue, green when not (Jinja template on `icon_color`)
- Tap opens `more-info` on the `input_datetime` (shows history, allows manual date edit)
- Hold sets `input_datetime` to today (marks complete), with confirmation

Entity triplet per task: `input_datetime.<name>` (last done), `sensor.<name>_due` (computed due date), `binary_sensor.<name>_overdue` (boolean overdue flag).


---

## Vacuum Subview

Five sections:

- **Map** — `picture-entity` showing `image.roborock_q8_max_apartment`, conditionally visible when vacuum is not docked OR `input_select.vacuum_ran_today` is "Yes". No section title; renders minimal gap when hidden.
- **Controls** — Native `tile` card with `vacuum-commands` feature (start/pause, stop, return home); `color: green`, `state_content: [state, area_name]`, `grid_options: {columns: full}`, `features_position: inline`. No section title. Appears before Status.
- **Status** — 2-col grid of native `tile` cards: vacuum state, battery, cleaning area, duration. A conditional `tile` for `sensor.roborock_q8_max_current_room` appears in the grid only when `binary_sensor.roborock_q8_max_cleaning` is on.
- **Mop Settings** — Section-level `visibility` gates the entire block on `binary_sensor.roborock_q8_max_mop_attached` being on. Contains: Mop Intensity (`select.roborock_q8_max_mop_intensity` + `select-options`), Mop Mode (`select.roborock_q8_max_mop_mode` + `select-options`), Water Supply (`binary_sensor.roborock_q8_max_water_shortage`).
- **Consumables** — 2-col grid of `mushroom-template-card` for filter, main brush, side brush, and sensor. Each card shows hours remaining as secondary text; icon color is red when the overdue binary sensor is on, green otherwise (`mushroom-template-card` used because native `tile` has no Jinja `icon_color` equivalent). Tap resets the consumable via `button.press` with confirmation. `number.overdue_reminders_count` does not include vacuum consumables — they are tracked independently here.

---

## Climate Subview

Tap target for the thermostat chip on strip 1 (Environment).

**Badges** — Two entity badges in the view header, both blue: `sensor.apartment_temperature` (`mdi:home-thermometer`, labeled "Inside") and `sensor.apartment_humidity` (`mdi:water-percent`, labeled "Inside"). Both are group sensors — tapping either opens more-info showing readings from all member room sensors. Outdoor AQI is accessible via the AQI chip on strip 1 (Home view).

Two sections:

- **Controls** — Thermostat tile (`climate.living_room_thermostat`, `grid_options: {columns: 6}`, `features_position: bottom`, HVAC modes + target temperature + fan modes, `state_content: [current_temperature, current_humidity]`). Comfort Setting tile (`select.living_room_thermostat_current_mode` with `select-options` feature — Home/Sleep/Away). Clear Hold tile (`button.living_room_thermostat_clear_hold`). Below these, an "HVAC Runtime" subtitle heading followed by a `mushroom-template-card` showing today's totals ("Cooling: X.X h · Heating: X.X h") from `sensor.cooling_today` and `sensor.heating_today`. Icon color reflects which mode ran today: blue = cooling, orange = heating, grey = neither.
- **HVAC History** (`collapsed: true`) — 28-day `statistics-graph` line chart (`chart_type: line`, `period: day`, `stat_types: [max]`, `days_to_show: 28`) for `sensor.cooling_today` and `sensor.heating_today`. Hidden by default; tap the section header to expand. Daily max equals daily total since both sensors reset at midnight.

> **Note on `grid_options`:** The `tile` card in a `sections` view defaults to a 1-column layout and renders at half-width unless you set `grid_options: {columns: 12}` (or `columns: full`). This is different from `grid` cards, which fill available width automatically.

---

## Live Configuration

The dashboard configuration for `mobile-3` is stored in HA storage and is the authoritative source of truth for all layout, card order, and feature configuration. Do not maintain a YAML copy in this guide.

To read the current config:
- **MCP:** `ha_config_get_dashboard(url_path="mobile-3")`
- **UI:** Settings → Dashboards → Mobile 3.0 → Edit dashboard

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Mobile 3.0 dashboard | `mobile-3` | Lovelace dashboard |
| Home alarm | `alarm_control_panel.home_alarm` | Entity |
| Living room thermostat | `climate.living_room_thermostat` | Entity |
| Apartment temperature | `sensor.apartment_temperature` | Entity |
| Apartment humidity | `sensor.apartment_humidity` | Entity |
| Apartment weather | `weather.apartment` | Entity |
| Cooling runtime today | `sensor.cooling_today` | Entity |
| Heating runtime today | `sensor.heating_today` | Entity |
| Thermostat comfort mode | `select.living_room_thermostat_current_mode` | Entity |
| Thermostat clear hold | `button.living_room_thermostat_clear_hold` | Entity |
| Roborock Q8 Max | `vacuum.roborock_q8_max` | Entity |
| Apartment map image | `image.roborock_q8_max_apartment` | Entity |
| Vacuum cleaning (binary) | `binary_sensor.roborock_q8_max_cleaning` | Entity |
| Maintenance required (aggregated) | `binary_sensor.roborock_maintenance_required` | Entity |
| Replace filter | `binary_sensor.roborock_replace_filter` | Entity |
| Replace main brush | `binary_sensor.roborock_replace_main_brush` | Entity |
| Replace side brush | `binary_sensor.roborock_replace_side_brush` | Entity |
| Clean sensor | `binary_sensor.roborock_clean_sensor` | Entity |
| Mop attached | `binary_sensor.roborock_q8_max_mop_attached` | Entity |
| Water shortage | `binary_sensor.roborock_q8_max_water_shortage` | Entity |
| Mop intensity | `select.roborock_q8_max_mop_intensity` | Entity |
| Mop mode | `select.roborock_q8_max_mop_mode` | Entity |
| Current room | `sensor.roborock_q8_max_current_room` | Entity |
| Filter time left | `sensor.roborock_q8_max_filter_time_left` | Entity |
| Main brush time left | `sensor.roborock_q8_max_main_brush_time_left` | Entity |
| Side brush time left | `sensor.roborock_q8_max_side_brush_time_left` | Entity |
| Sensor time left | `sensor.roborock_q8_max_sensor_time_left` | Entity |
| Reset filter | `button.roborock_q8_max_reset_air_filter_consumable` | Entity |
| Reset main brush | `button.roborock_q8_max_reset_main_brush_consumable` | Entity |
| Reset side brush | `button.roborock_q8_max_reset_side_brush_consumable` | Entity |
| Reset sensor | `button.roborock_q8_max_reset_sensor_consumable` | Entity |
| Kitchen water leak | `binary_sensor.kitchen_leak_water_leak` | Entity |
| Bathroom water leak | `binary_sensor.bathroom_leak_water_leak` | Entity |
| Master bath water leak | `binary_sensor.master_bathroom_leak_water_leak` | Entity |
| Utility room water leak | `binary_sensor.utility_room_leak_water_leak` | Entity |
| Kitchen freezer door | `binary_sensor.kitchen_freezer_door_contact` | Entity |
| Garage interior door | `binary_sensor.garage_interior_door_contact` | Entity |
| Front door | `binary_sensor.entrance_front_door_contact` | Entity |
| Office sliding door | `binary_sensor.office_sliding_door_contact` | Entity |
| Garage door | `cover.garage_door` | Entity |
| Outdoor AQI | `sensor.toledo_ohio_usa_air_quality_index` | Entity |
| Trash pickup pending | `input_boolean.trash_pickup_pending` | Helper |
| Trash pickup label | `input_text.trash_pickup_pending_label` | Helper |
| Vacuum ran today | `input_select.vacuum_ran_today` | Helper |
| Overdue reminders count | `number.overdue_reminders_count` | Helper |
| Everyone sleeping | `input_boolean.everyone_sleeping` | Helper |
| Avery sleeping | `input_boolean.avery_sleeping` | Helper |
| Guest mode | `input_boolean.guest_mode` | Helper |
| Movie mode | `input_boolean.movie_mode` | Helper |
| Sonos night mode | `input_boolean.sonos_night_mode` | Helper |

---

## Related Documents

- `standards/dashboards.md` — Governs all dashboard builds; explains the design decisions this guide implements
- `standards/naming.md` — Entity naming standard; flags naming gaps in current light entity IDs
