# Mobile Dashboard

*Last updated: June 2026*

---

## Overview

`mobile` is the primary mobile dashboard for the HA instance, built on Bubble Card throughout. It targets the iOS Companion App and aims for an Apple Home-style clarity: chip strips for ambient status at a glance, room tiles with sub-buttons for quick control of key devices, and modal pop-ups for the full per-room control surface.

This dashboard replaces Mobile 3.0 (`mobile-3`, which used Mushroom + native tile cards) and revives the pop-up interaction model from Mobile 2.0 (the first Bubble Card dashboard). Adaptive Lighting manages all brightness and color temperature — no brightness sliders appear anywhere.

Mobile 3.0 remains in HA storage until `mobile` is feature-complete and a formal cutover is done.

---

## Architecture

```
mobile (storage-mode dashboard, url_path: mobile)
│
├── Home (sections, max_columns=1)
│   │
│   ├── [chip strip section — no title]
│   │   ├── Strip 1: Environment        always visible: Weather, AQI, Thermostat
│   │   ├── Strip 2: Status & Alerts    4 anchored + conditional alert chips
│   │   ├── Strip 3: Modes              all conditional (sleeping, movie, quiet, sync)
│   │   └── Strip 4: Presence           always visible: Nate, Guest
│   │
│   ├── [room tile sections — no section titles]
│   │   ├── Living Room     bubble-card button → #living-room popup
│   │   ├── Kitchen         bubble-card button → #kitchen popup
│   │   ├── Master Bedroom  bubble-card button → #master-bedroom popup
│   │   ├── Avery's Room    bubble-card button → #averys-room popup
│   │   ├── Office          bubble-card button → #office popup
│   │   ├── Bathroom        bubble-card button → #bathroom popup
│   │   ├── Garage          bubble-card button → #garage popup
│   │   └── Outside         bubble-card button → #outside popup
│   │
│   ├── [utility tile sections — no section titles]
│   │   ├── Reminders       bubble-card button → #reminders popup
│   │   ├── Vacuum          bubble-card button → #vacuum popup
│   │   ├── Climate         bubble-card button → #climate popup
│   │   └── Water Leaks     bubble-card button → #water-leaks popup
│   │
│   └── [pop-up sections — hidden by default, triggered via URL hash]
│       ├── #living-room     Lights / Fan / Climate / Media / Sensors
│       ├── #kitchen         Lights / Sensors
│       ├── #master-bedroom  Lights / Fan / Media / Sensors
│       ├── #averys-room     Lights / Fan / Media / Sensors
│       ├── #office          Lights / Sensors
│       ├── #bathroom        Lights / Sensors
│       ├── #garage          Cover / Lights / Sensors
│       ├── #outside         Lights / Sensors
│       ├── #reminders       Household task grid
│       ├── #vacuum          Map / Controls / Status / Mop Settings / Consumables
│       ├── #climate         Controls / HVAC History
│       └── #water-leaks     Sensor grid
```

**Design decisions:**
- Room tiles are single-card sections: one Bubble Card `button` per area. No separate section headings — the button card shows the room name and icon. Tap navigates to the area's pop-up; hold toggles the primary light; sub-buttons on the tile surface handle the most-used quick controls.
- Pop-up cards live in dedicated sections at the bottom of the Home view. HA renders no-title sections as zero-height, so pop-up sections are visually absent until triggered. Each pop-up card carries its content in a `cards` array.
- Chip strips use `sub-buttons-only` cards (one per strip) with sub-button `visibility` conditions — the same conditional logic as mobile-3's Mushroom chips, but in Bubble Card's sub-button system.

---

## Prerequisites

- Home Assistant 2025.9 or later
- HACS frontend resources installed and active:
  - Bubble Card (`lovelace-bubble-card`)
  - Bubble Card Tools (required for module backend)
  - Bubble Badges 2
  - Bubble Weather
  - Bubble Neon
  - card-mod (`lovelace-card-mod`) — retained for vacuum map transform
  - Mushroom Cards (`lovelace-mushroom`) — retained as fallback; do not remove until all fallback uses are migrated or confirmed unnecessary
- Adaptive Lighting integration active (justifies no-slider rule)

---

## Build Steps

### Step 1 — Install HACS resources

In the HA UI: **Settings → HACS → Frontend**. Install each resource listed in Prerequisites. Restart HA after all five Bubble Card resources are installed to ensure they register correctly.

Mushroom Cards and card-mod are already installed from mobile-3; no action needed.

### Step 2 — Create the `mobile` dashboard

In the HA UI: **Settings → Dashboards → Add Dashboard**. Set:

| Field | Value |
|---|---|
| Title | `Mobile` |
| Icon | `mdi:cellphone` |
| URL | `mobile` |
| Show in sidebar | On |
| Admin only | Off |

Select **Storage mode**. The dashboard URL becomes `/mobile`. Leave mobile-3 active — do not change the default dashboard yet.

Add a single view titled **Home**, type **Sections**, `max_columns: 1`.

### Step 3 — Build the chip strip section

Add one section with no title. Within it, add four `sub-buttons-only` Bubble Card cards stacked vertically (one per strip). Sub-button visibility, tap actions, and icon color logic follow the same entity logic as mobile-3; see [Chip Strip Design](#chip-strip-design) below.

### Step 4 — Add room tile sections

Add one section per area with no title. Each section contains a single Bubble Card `button` card. See [Room Tiles](#room-tiles) below for per-room entity assignments and sub-button reference.

### Step 5 — Build the Living Room pop-up (reference)

Add a section with no title at the bottom of the Home view. Place a Bubble Card `pop-up` card with `hash: "#living-room"`. Build its `cards` array with the Lights / Fan / Climate / Media / Sensors sections. This pop-up is the reference pattern for all other rooms.

### Step 6 — Build remaining room pop-ups

Replicate the Living Room pop-up structure for: Kitchen, Master Bedroom, Avery's Room, Office, Bathroom, Garage, Outside. Include only the sections applicable to each room.

### Step 7 — Build utility pop-ups

Build pop-ups for: Reminders (`#reminders`), Vacuum (`#vacuum`), Climate (`#climate`), Water Leaks (`#water-leaks`). See [Utility Pop-ups](#utility-pop-ups) below.

### Step 8 — Apply Bubble Neon theming

Apply the Bubble Neon module and configure global Bubble Card CSS variable tokens (border radius, accent color, blur level, sub-button spacing). Document the chosen token values in `standards/dashboards.md` → Theming Tokens once finalized.

### Step 9 — Add utility tile sections

Add the four utility tile sections (Reminders, Vacuum, Climate, Water Leaks) between the room tiles and the pop-up sections. Each is a Bubble Card `button` with `tap_action: navigate #utility-hash` and status sub-buttons.

### Step 10 — Cutover

Once `mobile` is feature-complete:
1. In **Settings → Dashboards**, set `mobile` as the default dashboard if desired.
2. Confirm `mobile-3` is no longer referenced anywhere.
3. Delete `mobile-3` via `ha_config_delete_dashboard(url_path="mobile-3")` (requires explicit confirmation).
4. Update this guide's Overview and the Related HA Config table.
5. Update the memory index to reflect the cutover.

---

## Chip Strip Design

Each strip is a Bubble Card `sub-buttons-only` card. Sub-button `visibility` replaces the `type: conditional` wrapping used in mobile-3. The entity logic and ordering rules are identical to mobile-3.

### Strip 1 — Environment

Always visible. Three sub-buttons, no visibility conditions.

**Weather** — Dynamic icon: `mdi:weather-{{ states('weather.apartment') }}` (special-case `partlycloudy` → `mdi:weather-partly-cloudy`). Content shows current temperature from `state_attr('weather.apartment', 'temperature')`. Tap: `more-info` on `weather.apartment`.

**AQI** — `mdi:smog`. Icon color driven by `sensor.toledo_ohio_usa_air_quality_index`: green ≤ 100, accent 101–125, red ≥ 126. Content shows the raw value. Tap: `more-info` on the sensor. Use the JS template system for `icon_color` since Bubble Card sub-buttons support it.

**Thermostat** — `mdi:home-thermometer`. Icon color from `hvac_action`: blue = cooling, orange = heating, grey = idle. Content: current indoor temperature. Tap: navigate to `#climate` pop-up.

### Strip 2 — Status & Alerts

A mix of always-visible anchored sub-buttons (positions 1–4) and conditional alert sub-buttons (positions 5+). Conditional sub-buttons use Bubble Card's `visibility` field with entity state conditions.

**Alert sub-button coloring:** use explicit `icon_color` values (red, orange, green) — do not rely on entity-class default colors. `state_not: "off"` catches both active alerts and `unknown`/`unavailable` states (intentional: conservative default for safety sensors).

**Alarm status / Alarm alert** — Position 1; mutually exclusive. Alarm status (`mdi:shield-home`, green, always visible) hides when alarm transitions to `triggered`, `pending`, or `arming`. Alarm alert chip (`mdi:shield-alert`, red or orange) takes position 1 during those states.

**Vacuum** — Position 2; always visible. Four states via JS template: cleaning/returning/paused → orange `mdi:robot-vacuum`; ran today AND `binary_sensor.roborock_maintenance_required` on → red `mdi:robot-vacuum-alert`; not run today → grey `mdi:robot-vacuum-off`; ran today, all clear → green `mdi:robot-vacuum`. Tap: navigate `#vacuum`.

**Garage** — Position 3; three mutually exclusive states. Green `mdi:garage` when closed (tap: more-info). Replaced by `mdi:garage-open-variant` when open: red when sleeping or away (tap closes with confirmation), orange when home and awake (tap closes with confirmation). Hold: always more-info.

**Reminders OK / Overdue reminders** — Position 4; mutually exclusive. Green `mdi:calendar-check` when `number.overdue_reminders_count` < 1. Replaced by red `mdi:calendar-alert` showing count when any reminder is overdue (count label only when 2+). Tap: navigate `#reminders`.

**Water leaks** — Conditional (position 5+). Single sub-button covering all four sensors via OR condition. `state_not: "off"` is intentional. Tap: navigate `#water-leaks`.

**Freezer door** — Conditional. No contextual gate — always alert-worthy.

**Exterior doors** — Two mutually exclusive conditional sub-buttons. Red when any of three sensors is open AND (sleeping OR nobody home). Orange when open AND home AND awake. Count shown when 2+. Sensors: `binary_sensor.garage_interior_door_contact`, `binary_sensor.entrance_front_door_contact`, `binary_sensor.office_sliding_door_contact`.

**Garage door** — Two mutually exclusive conditional sub-buttons. Red when open AND (sleeping OR away). Orange when open AND home AND awake. Both: tap-to-close with confirmation; hold: more-info.

**Trash pickup** — Conditional. Icon-only; `input_boolean.trash_pickup_pending` is the gate.

> **Icon-only sub-buttons:** omit the `name` field entirely. Setting `name: ""` allocates an empty text area and shifts the icon off-center. Sub-buttons that conditionally show a count keep their `name` field since they render text when count ≥ 2.

> **Contextual gate for door and garage alerts:** only alert when the entity is open AND (sleeping OR nobody home). Template condition: `input_boolean.everyone_sleeping` is `on` OR `zone.home` count is below 1.

### Strip 3 — Modes

All conditional; the strip may be entirely empty. No `name` field on sub-buttons that are icon-only.

- **Avery sleeping** — `input_boolean.avery_sleeping` on AND `input_boolean.everyone_sleeping` off
- **Everyone sleeping** — `input_boolean.everyone_sleeping`
- **Light sync** — both `switch.living_room_sync_box_power` and `media_player.living_room_tv` on
- **Movie mode** — `input_boolean.movie_mode`, gated on TV being on
- **Quiet mode** — `input_boolean.sonos_night_mode`, gated on TV; yellow icon

### Strip 4 — Presence

Always visible. Nate's sub-button uses entity picture. Guest sub-button: tap disabled (prevents accidental activation); hold toggles `input_boolean.guest_mode`.

---

## Room Tiles

Each room is a Bubble Card `button` card in its own no-title section. Primary entity is the main light for the room (or cover/sensor for Garage/Outside). Tap opens the room's pop-up; hold toggles the primary light.

| Room | Primary entity | Hash | Sub-buttons (reference) |
|---|---|---|---|
| Living Room | `light.living_room_fan` | `#living-room` | Fan, Apple TV, Sonos |
| Kitchen | `light.kitchen_ceiling` | `#kitchen` | Sink light |
| Master Bedroom | `light.master_bedroom_fan` | `#master-bedroom` | Fan, Sonos, Apple TV |
| Avery's Room | `light.avery_room_ceiling` | `#averys-room` | Standing fan, HomePod Mini |
| Office | `light.office_ceiling` | `#office` | TBD during build |
| Bathroom | `light.bathroom_hallway_ceiling` | `#bathroom` | TBD during build |
| Garage | `cover.garage_door` | `#garage` | Garage door open/close |
| Outside | `sensor.outside_temperature` | `#outside` | Porch light, patio lights |

> **Sub-button selection:** the reference set above is a starting point. Finalize per room during build based on what's actually used most from the home view without opening the pop-up.

> **Naming gap:** `light.living_room_fan` and `light.master_bedroom_fan` embed the device type (`fan`) rather than being location-first per `standards/naming.md`. These IDs are used as-is; a rename pass is tracked separately.

---

## Living Room Pop-up (Reference)

`hash: "#living-room"` — the reference pattern for all room pop-ups. Five sections inside the pop-up's `cards` array:

- **Lights** — Bubble Card buttons for: main fan lamp (`light.living_room_fan`), ceiling lights (if separate), movie poster lights, status lamp, TV lights. No sliders.
- **Fan** — Bubble Card button for `fan.living_room_ceiling` with fan-speed sub-buttons.
- **Climate** — Bubble Card climate card for `climate.living_room_thermostat`. No hold-slider (Adaptive Lighting context; if Bubble Card climate card shows a slider, disable it).
- **Media** — Bubble Card media-player for Apple TV (`media_player.living_room_appletv`) and Sonos (`media_player.living_room_sonos`) with volume sub-buttons.
- **Sensors** — Read-only sub-buttons or state buttons for motion/occupancy sensors.

Pop-up header sub-buttons (visible in the pop-up title bar): current temperature and humidity from `sensor.living_room_thermostat_current_temperature` and `sensor.living_room_thermostat_current_humidity`.

Pending room pop-ups (Kitchen through Outside) follow this same section structure, including only sections that apply.

---

## Utility Pop-ups

### Water Leaks (`#water-leaks`)

Four water leak sensors in a 2×2 grid of Bubble Card buttons (state display). Tap: more-info on each sensor. Colors: red when `on`/`unknown`, green when `off`. Sensors: `binary_sensor.kitchen_leak_water_leak`, `binary_sensor.bathroom_leak_water_leak`, `binary_sensor.master_bathroom_leak_water_leak`, `binary_sensor.utility_room_leak_water_leak`.

### Reminders (`#reminders`)

**Household** — grid of Bubble Card buttons (or Mushroom `mushroom-template-card` fallback if JS template `icon_color` proves insufficient) for each tracked task. Each card:
- Icon red when overdue, green when not (JS template or Jinja `icon_color`)
- Secondary text: formatted due date via `strptime().strftime('%B %-d, %Y')`
- Tap: `more-info` on `input_datetime.<name>` (shows history, allows manual date edit)
- Hold: sets `input_datetime` to today (marks complete), with confirmation

Entity triplet per task: `input_datetime.<name>` (last done), `sensor.<name>_due` (computed due date), `binary_sensor.<name>_overdue` (boolean overdue flag).

Tasks: car, coffee grinder, dishwasher, disposal, razor, toothbrushes, washer, water filter.

### Vacuum (`#vacuum`)

Five sections:

- **Map** — `picture-entity` showing `image.roborock_q8_max_apartment`, conditionally visible when vacuum is not docked OR `input_select.vacuum_ran_today` is "Yes". No section title. card-mod corrects the excess black padding baked into the Roborock map image: `ha-card { padding: 0; overflow: hidden; }` / `hui-image { transform: scale(1.5) translateX(-3%) translateY(13%); transform-origin: center center; display: block; margin: -12% 0; }`. See `standards/dashboards.md` → card-mod Use Cases for technique details.
- **Controls** — Bubble Card button with vacuum command sub-buttons (start/pause, stop, return home). `color: green`. No section title. Appears before Status.
- **Status** — Bubble Card state buttons: vacuum state, battery, cleaning area, duration. Conditional: `sensor.roborock_q8_max_current_room` shown only when `binary_sensor.roborock_q8_max_cleaning` is on.
- **Mop Settings** — Section-level visibility gated on `binary_sensor.roborock_q8_max_mop_attached`. Contains: Mop Intensity, Mop Mode, Water Supply.
- **Consumables** — Bubble Card buttons (or Mushroom `mushroom-template-card` fallback) for filter, main brush, side brush, sensor. Icon: red when maintenance binary sensor is on, green otherwise. Secondary text: hours remaining. Tap: reset consumable via `button.press` with confirmation.

### Climate (`#climate`)

**Badges** (pop-up header sub-buttons) — `sensor.apartment_temperature` and `sensor.apartment_humidity`, both blue.

Two sections:

- **Controls** — Bubble Card climate card for `climate.living_room_thermostat`. Comfort Setting: `select.living_room_thermostat_current_mode` with select-options sub-buttons. Clear Hold: button for `button.living_room_thermostat_clear_hold`. HVAC Runtime: Bubble Card button (or Mushroom `mushroom-template-card` fallback) showing today's cooling/heating totals from `sensor.cooling_today` and `sensor.heating_today`. Icon color: blue = cooling, orange = heating, grey = neither.
- **HVAC History** (`collapsed: true`) — 28-day `statistics-graph` line chart (`chart_type: line`, `period: day`, `stat_types: [max]`, `days_to_show: 28`) for `sensor.cooling_today` and `sensor.heating_today`. Native HA card — no Bubble Card equivalent.

> **Note on grid options:** native `tile` and `statistics-graph` cards in a `sections` view default to half-width. Set `grid_options: {columns: 12}` or `columns: full` to make them span the full width inside a pop-up.

---

## Live Configuration

The dashboard configuration for `mobile` is stored in HA storage and is the authoritative source of truth for all layout, card order, and feature configuration. Do not maintain a YAML copy in this guide.

To read the current config:
- **MCP:** `ha_config_get_dashboard(url_path="mobile")`
- **UI:** Settings → Dashboards → Mobile → Edit dashboard

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Mobile dashboard | `mobile` | Lovelace dashboard |
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

- `standards/dashboards.md` — Governs all dashboard builds; defines card vocabulary, pop-up pattern, chip strip rules, and HACS policy
- `standards/naming.md` — Entity naming standard; flags naming gaps in current light entity IDs
