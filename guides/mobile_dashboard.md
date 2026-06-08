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
mobile-app (storage-mode dashboard, url_path: mobile-app)
│
├── Home (sections, max_columns=1)
│   │
│   ├── [chip strip section — no title]
│   │   ├── Strip 1: Controls      always visible: Weather, Alarm, Thermostat, Vacuum, Reminders
│   │   └── Strip 2: Status & Modes  2 anchored (AQI, Guest) + conditional alert chips
│   │
│   ├── [chip-driven inline sections — toggled by Strip 1 chip tap, no title]
│   │   ├── Thermostat controls    shown when input_boolean.mobile_show_thermostat_controls = on
│   │   └── Vacuum basic controls  shown when input_boolean.mobile_show_vacuum_controls = on
│   │
│   ├── [condition-triggered section — auto-show based on state, no title]
│   │   └── Vacuum status          shown when vacuum not docked OR input_select.vacuum_ran_today = Yes
│   │
│   ├── [Primary Lights — separator always visible; lights grid collapsible]
│   │   ├── Primary Lights separator  tap toggles input_boolean.mobile_show_primary_lights
│   │   └── Lights grid              shown when input_boolean.mobile_show_primary_lights = on (default on)
│   │
│   ├── [room tile section — separator heading "Primary Rooms"]
│   │   ├── Living Room     bubble-card button → #living-room popup (slider, read-only)
│   │   ├── [TV controls bar]  sub-buttons, visible when living_room_tv = on
│   │   ├── Kitchen         bubble-card button → #kitchen popup
│   │   ├── Master Bedroom  bubble-card button → #master-bedroom popup
│   │   ├── Avery's Room    bubble-card button → #averys-room popup
│   │   ├── Office          bubble-card button → #office popup
│   │   ├── Bathroom        bubble-card button → #bathroom popup
│   │   ├── Garage          bubble-card button → #garage popup
│   │   └── Outside         bubble-card button → #outside popup
│   │
│   └── [pop-up sections — hidden by default, triggered via URL hash]
│       ├── #water-leaks     Sensor grid  (pending migration to subview)
│       └── (room pop-ups pending build)
│
├── Reminders (subview, path: reminders)
│   ├── Trash Pickup         mushroom-template-card
│   └── Household Tasks      2-col grid of mushroom-template-cards
│
├── Vacuum (subview, path: vacuum)
│   ├── [map — conditional]  picture-entity when not docked or ran today
│   ├── Controls             tile card with vacuum-commands feature
│   ├── Status               2-col grid of tile cards
│   ├── Mop Settings         2-col grid of tile cards (section visibility: mop attached)
│   └── Consumables          2-col grid of mushroom-template-cards
│
└── Footer nav (native sections view footer — sticky)
    Living Room, Office, Avery's Room, Master Bedroom, Other
```

**Design decisions:**
- **Card stack: stock HA + Mushroom only.** Bubble Card is being migrated out. Mushroom Cards (`mushroom-chips-card`, `mushroom-template-card`) are retained for chip strips and reminder/consumable cards where template-driven content is needed. Everything else uses native HA tile, heading, grid, and conditional cards.
- **Detail views are subviews, not pop-ups.** Reminders and Vacuum are full-page subviews (`subview: true`, navigated via `/mobile-app/<path>`). Room detail views will follow the same pattern. This eliminates Bubble Card `pop-up` dependency and produces a more native full-page interaction on mobile.
- Room tiles are grouped in a single section. Per-room sections were tried and rejected — the `sections` view type renders a large top margin on every section heading, making individual room sections visually noisy.
- Chip strips use Mushroom `mushroom-chips-card` (one per strip, stacked vertically). Two strips, organized by function: Strip 1 (Controls) — Weather, Alarm, Thermostat, Vacuum, Reminders. Strip 2 (Status & Modes) — AQI, Guest, plus conditional alert chips. Thermostat and Vacuum chips toggle inline sections on tap.
- The Home view uses two inline section patterns: **chip-driven** (user-initiated, Thermostat and Vacuum) and **condition-triggered** (auto-shown based on house state — vacuum not docked or ran today). Both sit between chip strips and room tiles.

---

## Prerequisites

- Home Assistant 2025.9 or later
- HACS frontend resources installed and active:
  - Mushroom Cards (`lovelace-mushroom`) — chip strips, template cards
  - card-mod (`lovelace-card-mod`) — chip strip centering styles; vacuum map transform
  - PHU icons (`lovelace-hue-icons`) — `phu:rooms-other` footer chip
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
| URL | `mobile-app` |
| Show in sidebar | On |
| Admin only | Off |

Select **Storage mode**. The dashboard URL becomes `/mobile-app`. Leave mobile-3 active — do not change the default dashboard yet.

Add a single view titled **Home**, type **Sections**, `max_columns: 1`.

### Step 3 — Build the chip strip section

Add one section with no title. Within it, add two Mushroom `mushroom-chips-card` cards stacked vertically (one per strip). Each uses `alignment: center` and a `card_mod` with a nested shadow DOM style (`$ mushroom-chip$ .container`) to set `--chip-height: 36px`, `--chip-padding: 0 6px`, `gap: 0`, and `justify-content: center` inside each chip's container (ensures icon centering on icon-only chips). See [Chip Strip Design](#chip-strip-design) below.

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

Each strip is a Mushroom `mushroom-chips-card` with `alignment: center` and a `card_mod` that sets `--chip-height: 36px` and `--chip-padding: 0 6px` at the `ha-card` level, plus a nested shadow DOM style piercing into each `mushroom-chip`'s shadow root to set `gap: 0; justify-content: center` on `.container` (ensures icon-only chips render centered). Chips use `type: conditional` wrappers for visibility. Bubble Card `sub-buttons-only` was evaluated and rejected for visual reasons.

### Strip 1 — Controls

Always visible (Weather, Alarm, Thermostat, Vacuum always shown; Reminders shows one chip at a time — green or red — based on overdue count). Every chip here is interactive.

**Weather** — Dynamic icon: `mdi:weather-{{ states('weather.apartment') }}`, with explicit overrides for `partlycloudy` → `mdi:weather-partly-cloudy` and `clear-night` → `mdi:weather-night` (`mdi:weather-clear-night` does not exist in MDI). Content: current temperature. Tap: `more-info` on `weather.apartment`.

**Alarm** — Single template chip, always visible. Icon and color driven by state: `mdi:shield-home` green when disarmed, `mdi:shield-lock` orange when any armed state (`armed_away`, `armed_home`, `armed_night`, `arming`), `mdi:shield-alert` red when `triggered` or `pending`. No content label — color alone communicates state. Tap: `more-info` on `alarm_control_panel.home_alarm`.

**Thermostat** — `mdi:home-thermometer`. Icon color from `hvac_action`: blue = cooling, orange = heating, grey = idle. Content: current indoor temperature. Tap: toggle `input_boolean.mobile_show_thermostat_controls` (inline thermostat section). Hold: none.

**Vacuum** — Five states via Jinja template, evaluated in priority order: `input_boolean.vacuum_routine_pause` on → orange `mdi:robot-vacuum-off`; cleaning/returning/paused → orange `mdi:robot-vacuum`; ran today AND `binary_sensor.roborock_maintenance_required` on → red `mdi:robot-vacuum-alert`; not run today → grey `mdi:robot-vacuum-off`; ran today, all clear → green `mdi:robot-vacuum`. Tap: toggle `input_boolean.mobile_show_vacuum_controls` (inline basic controls). Hold: toggle `input_boolean.vacuum_routine_pause` (skips auto-start on departure via Last Leaves Home and Vacuum Midday Prompt; cleared automatically by First Arrives Home).

**Reminders OK / Overdue reminders** — Mutually exclusive. Green `mdi:calendar-check` when `number.overdue_reminders_count` < 1 — tap navigates `#reminders` pop-up. Replaced by red `mdi:calendar-alert` with the overdue count (always shown, even when 1) when any task is overdue — tap and hold both navigate `#reminders` pop-up.

### Strip 2 — Status & Modes

Two always-visible anchored chips (AQI, Guest) followed by conditional alert chips. Conditional chips use `type: conditional` wrappers; all appear in the same strip and stack when multiple are active simultaneously.

**Alert chip coloring:** use explicit `icon_color` values (red, orange, green) — do not rely on entity-class default colors. `state_not: "off"` catches both active alerts and `unknown`/`unavailable` states (intentional: conservative default for safety sensors).

**AQI** — `mdi:smog`. Always visible. Icon color driven by `sensor.toledo_ohio_usa_air_quality_index`: green ≤ 100, accent 101–125, red ≥ 126. Content shows the raw value. Tap: `more-info`.

**Guest** — `mdi:account-child-circle`. Always visible. Icon color: green when `input_boolean.guest_mode` is on, grey when off. Hold: toggle `input_boolean.guest_mode`. Tap: none. (Hold-to-toggle prevents accidental activation on a crowded strip.) No content label.

**Water leaks** — Conditional. Visibility gated on `binary_sensor.water_leak_detected` (group sensor — on when any of the four sensors is active). Count shown when 2+. Tap: navigate `#water-leaks`.

**Freezer door** — Conditional. No contextual gate — always alert-worthy.

**Exterior doors** — Two mutually exclusive conditional chips. Red when any of three sensors is open AND (sleeping OR nobody home). Orange when open AND home AND awake. Count shown when 2+. Sensors: `binary_sensor.garage_interior_door_contact`, `binary_sensor.entrance_front_door_contact`, `binary_sensor.office_sliding_door_contact`.

**Garage door** — Two mutually exclusive conditional chips, shown only when open. Red `mdi:garage-open-variant` when open AND (sleeping OR away) — tap closes with confirmation. Orange when open AND home AND awake — tap closes with confirmation. Hold on both: more-info. The green closed chip was removed — the absence of an open alert is sufficient indication that the garage is closed.

TV-related mode chips (Light Sync, Movie Mode, Quiet Mode) were removed from this strip — they are now surfaced in the [TV Controls Bar](#living-room-tv-controls-bar) below the Living Room tile, which auto-shows when the TV is on.

> **Icon-only chips:** for template chips, omit the `content` field entirely — do not set `content: ""`. An empty string still allocates a text slot in the chip's internal flex layout and shifts the icon off-center. For entity chips, use `content_info: none`. Chips that conditionally show a count keep their content field since they render text when count ≥ 2. The chip strip `card_mod` sets `gap: 0; justify-content: center` on `.container` via nested shadow DOM to reliably center icon-only chips. `justify-content: center` is the load-bearing rule — without it, icon-only chips render slightly left of center on desktop browsers (macOS Safari, macOS Companion App) even with `gap: 0`.

> **Contextual gate for door and garage alerts:** only alert when the entity is open AND (sleeping OR nobody home). Condition: `input_boolean.everyone_sleeping` is `on` OR `zone.home` count is below 1.

---

## Room Tiles

All rooms live in a single section with no title. A Bubble Card `separator` card ("Primary Rooms") sits at the top of the section as the visible heading — per-room sections were tried and rejected because the `sections` view type adds a large top margin to every section heading. Primary entity is the main light for the room (or cover/sensor for Garage/Outside). Tap opens the room's pop-up; hold toggles the primary light.

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

> **Living Room `button_type`:** Uses `button_type: slider` with `read_only_slider: true` rather than the standard `switch`. This shows a brightness bar as ambient state info. The slider is non-interactive — Adaptive Lighting owns brightness. All other room tiles use `switch`.

> **Naming gap:** `light.living_room_fan` and `light.master_bedroom_fan` embed the device type (`fan`) rather than being location-first per `standards/naming.md`. These IDs are used as-is; a rename pass is tracked separately.

---

## Living Room TV Controls Bar

A Bubble Card `card_type: sub-buttons` card sits immediately below the Living Room tile in the same section. Its `visibility` is gated on `media_player.living_room_tv` being `on` — it appears automatically when the TV is active and hides when the TV is off, with no chip or `input_boolean` toggle involved.

This is the state-triggered contextual controls pattern — see `standards/dashboards.md` → State-Triggered Contextual Controls.

**Controls (bottom sub-buttons):**

| Entity | Label | Icon | Action |
|---|---|---|---|
| `switch.living_room_sync_box_light_sync` | TV Light Sync | `mdi:television-ambient-light` | toggle |
| `input_boolean.movie_mode` | Movie Mode | `mdi:theater` | toggle |
| `input_boolean.sonos_night_mode` | Night Mode | `mdi:moon-waning-crescent` | toggle |
| `media_player.living_room_sonos` | Volume | `mdi:knob` | slider (`sub_button_type: slider`, `state_background: false`) |

These three controls were previously duplicated as conditional mode chips in Strip 2. They were moved here because all three are gated on the TV being on — the contextual bar provides cleaner colocation with the room tile they affect.

---

## Condition-Triggered Sections

One section on the Home view appears and disappears automatically based on house state — no chip, no `input_boolean`, no user action needed. Section-level `visibility` is set directly on the relevant entity state.

| Section | Visibility condition | Content |
|---|---|---|
| Vacuum controls | vacuum not docked OR `input_select.vacuum_ran_today` = Yes | Native `tile` card with vacuum state, battery, and vacuum-commands feature |

**Vacuum section** — the `or` condition matches any state where the vacuum is actively relevant: currently running/returning, or already ran today and the user might want to check status. The condition-triggered section gives a quick status tile without requiring the full `#vacuum` pop-up to open.

The section sits immediately below the chip strips and above the room tiles. Overdue reminders and trash are surfaced via the Strip 1 reminders chip (turns red, shows count) and push notifications — not an inline section.

---

## Chip-Driven Inline Sections

Two sections on the Home view are shown and hidden by the user via Strip 1 chip taps. Each is gated on an `input_boolean` toggle; the chip's tap action calls `input_boolean.toggle` on that helper.

| Section | Toggle helper | Chip / trigger | Content |
|---|---|---|---|
| Thermostat controls | `input_boolean.mobile_show_thermostat_controls` | Thermostat chip tap | Bubble Card `climate` card with HVAC mode select, Comfort Setting select, and Clear Hold button |
| Vacuum basic controls | `input_boolean.mobile_show_vacuum_controls` | Vacuum chip tap | Native `tile` card with vacuum-commands feature (start/pause, stop, return home); tap navigates to `#vacuum` pop-up for full detail |
| Primary Lights | `input_boolean.mobile_show_primary_lights` | Primary Lights separator tap | 2-column grid of 5 room light Bubble Card buttons. Defaults to `on` — lights visible on page load. |

The `#vacuum` pop-up (Map / Controls / Status / Mop Settings / Consumables) is preserved and remains accessible by tapping the tile card inside the inline section. The inline section provides quick start/stop access; the pop-up provides full operational detail.

> **Panel auto-close:** Thermostat and Vacuum panels close automatically after 5 minutes via `automation.mobile_panel_auto_close`. The `for: "00:05:00"` on the trigger means the timer resets if a panel is closed before 5 minutes elapse — the automation simply never fires. Primary Lights does not auto-close; it is a display preference, not a transient panel.

**Vacuum routine pause** — The Vacuum chip hold action toggles `input_boolean.vacuum_routine_pause`. When on, the chip shows orange `mdi:robot-vacuum-off` and both the Last Leaves Home and Vacuum Midday Prompt automations skip the auto-start. The First Arrives Home automation clears it when the first person walks in. This is a one-trip skip — it does not permanently disable auto-cleaning.

---

## Footer Navigation

The sections view `footer` property at the view level renders a sticky navigation bar at the bottom of the Home view. It uses `custom:mushroom-chips-card` with `type: action` chips.

> **Rendering quirk:** Chips in the outer mushroom-chips-card's `chips` array do not render in the footer context. The outer card must wrap a second mushroom-chips-card in a `card` property — the inner card's chips render normally. See `LESSONS.md` for details.

**Footer targets:**

| Name | Icon | Navigation |
|---|---|---|
| Living Room | `mdi:sofa` | `#living-room` |
| Office | `mdi:desktop-classic` | `#office` |
| Avery's Room | `mdi:teddy-bear` | `#averys-room` |
| Master Bedroom | `mdi:bed-king` | `#master-bedroom` |
| Other | `phu:rooms-other` | (TBD — expand as rooms are built) |

```yaml
footer:
  type: custom:mushroom-chips-card
  card:
    type: custom:mushroom-chips-card
    alignment: center
    chips:
      - type: action
        icon: mdi:sofa
        tap_action:
          action: navigate
          navigation_path: "#living-room"
      - type: action
        icon: mdi:desktop-classic
        tap_action:
          action: navigate
          navigation_path: "#office"
      - type: action
        icon: mdi:teddy-bear
        tap_action:
          action: navigate
          navigation_path: "#averys-room"
      - type: action
        icon: mdi:bed-king
        tap_action:
          action: navigate
          navigation_path: "#master-bedroom"
      - type: action
        icon: phu:rooms-other
        tap_action:
          action: none
```

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

Four water leak sensors in a 2×2 grid of tile cards. Tap: more-info on each sensor. Colors: red when `on`/`unknown`, green when `off`. Sensors: `binary_sensor.kitchen_leak_water_leak`, `binary_sensor.bathroom_leak_water_leak`, `binary_sensor.master_bathroom_leak_water_leak`, `binary_sensor.utility_room_leak_water_leak`.

`binary_sensor.water_leak_detected` (group binary sensor, any-on) aggregates all four sensors into a single entity used by the water leak chip visibility condition and any automations that need a single leak trigger.

### Reminders (`#reminders`)

Reminders are accessible via the `#reminders` pop-up — tap the reminders chip (red with count when any task is overdue or trash is pending). There is no inline overdue section on the Home view; the chip and push notifications handle attention.

**Full pop-up** — triggered by the reminders chip navigating to `#reminders`. Two sections inside: a "Trash Pickup" section (full-width card, always present, green/red based on `input_boolean.trash_pickup_pending`), then a "Reminders" section with all 8 interval tasks in a 2-column grid, sorted: overdue tasks first by due date, then upcoming tasks by due date. Each task card:
- Icon red when overdue, green when not (Jinja `icon_color` template)
- Secondary text: formatted due date via `strptime().strftime('%b %-d, %Y')` (abbreviated month, e.g. "Mar 6, 2026")
- Tap: `more-info` on `input_datetime.<name>` (shows history, allows manual date edit)
- Hold: calls `script.reminder_mark_complete` with `data.reminder_entity` set to the task's `input_datetime` entity — see `guides/reminders.md` for the script definition and why a direct service call doesn't work; confirmation dialog required

Entity triplet per task: `input_datetime.<name>` (last done), `sensor.<name>_due` (computed due date), `binary_sensor.<name>_overdue` (boolean overdue flag).

Tasks: car washed, coffee grinder cleaned, dishwasher cleaned, disposal cleaned, razor blade changed, toothbrushes changed, washer cleaned, water filter changed.

### Vacuum (`#vacuum`)

Five sections:

- **Map** — `picture-entity` showing `image.roborock_q8_max_apartment`, conditionally visible when vacuum is not docked OR `input_select.vacuum_ran_today` is "Yes". No section title. card-mod corrects the excess black padding baked into the Roborock map image: `ha-card { padding: 0; overflow: hidden; }` / `hui-image { transform: scale(1.5) translateX(-3%) translateY(13%); transform-origin: center center; display: block; margin: -12% 0; }`. See `standards/dashboards.md` → card-mod Use Cases for technique details.
- **Controls** — Bubble Card button with vacuum command sub-buttons (start/pause, stop, return home). `color: green`. No section title. Appears before Status.
- **Status** — Bubble Card state buttons: vacuum state, battery, cleaning area, duration. Conditional: `sensor.roborock_q8_max_current_room` shown only when `binary_sensor.roborock_q8_max_cleaning` is on.
- **Mop Settings** — Section-level visibility gated on `binary_sensor.roborock_q8_max_mop_attached`. Contains: Mop Intensity, Mop Mode, Water Supply.
- **Consumables** — Bubble Card buttons (or Mushroom `mushroom-template-card` fallback) for filter, main brush, side brush, sensor. Icon: red when maintenance binary sensor is on, green otherwise. Secondary text: hours remaining. Tap: reset consumable via `button.press` with confirmation.

---

## Live Configuration

The dashboard configuration for `mobile` is stored in HA storage and is the authoritative source of truth for all layout, card order, and feature configuration. Do not maintain a YAML copy in this guide.

To read the current config:
- **MCP:** `ha_config_get_dashboard(url_path="mobile-app")`
- **UI:** Settings → Dashboards → Mobile → Edit dashboard

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Mobile dashboard | `mobile-app` | Lovelace dashboard |
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
| Water leak detected (aggregate) | `binary_sensor.water_leak_detected` | Helper (group) |
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
| Vacuum routine pause | `input_boolean.vacuum_routine_pause` | Helper |
| Mobile show thermostat controls | `input_boolean.mobile_show_thermostat_controls` | Helper |
| Mobile show vacuum controls | `input_boolean.mobile_show_vacuum_controls` | Helper |
| Mobile show primary lights | `input_boolean.mobile_show_primary_lights` | Helper |
| Mobile panel auto-close | `automation.mobile_panel_auto_close` | Automation |
| AL Brightness Display | `sensor.al_brightness_display` | Helper (template) |
| AL Color Temp Display | `sensor.al_color_temp_display` | Helper (template) |
| Overdue reminders count | `number.overdue_reminders_count` | Helper |
| Everyone sleeping | `input_boolean.everyone_sleeping` | Helper |
| Avery sleeping | `input_boolean.avery_sleeping` | Helper |
| Guest mode | `input_boolean.guest_mode` | Helper |
| Movie mode | `input_boolean.movie_mode` | Helper |
| Sonos night mode | `input_boolean.sonos_night_mode` | Helper |
| Living room TV | `media_player.living_room_tv` | Entity |

---

## Related Documents

- `standards/dashboards.md` — Governs all dashboard builds; defines card vocabulary, pop-up pattern, chip strip rules, and HACS policy
- `standards/naming.md` — Entity naming standard; flags naming gaps in current light entity IDs
