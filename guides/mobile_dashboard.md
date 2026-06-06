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
│   │   ├── Strip 2: Status & Alerts  ← 3 chips always visible; alert chips append when active
│   │   │   ├── Alarm status [green]        normal state → Away/Night/Home/Off; hides during alert
│   │   │   │   Alarm alert [red/orange]    alert state → triggered/pending=red, arming=orange; mutually exclusive with status
│   │   │   ├── Vacuum [grey/orange/green]  grey=docked+not run, orange=running, green=ran today → /vacuum
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
│   ├── Map         conditional picture-entity
│   ├── Status      state, battery, area, duration
│   ├── Controls    native tile with vacuum-commands feature
│   └── Consumables filter, main brush, sensor, side brush (hours remaining; tap to reset w/ confirmation)
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

A single strip combining persistent status indicators with conditional alert chips. Three chips are always visible (the status anchors); alert chips append to the right when active. In a quiet house the strip shows three chips; in an alert state the count grows without disturbing the anchored positions.

**Ordering rationale:** status chips are fixed at positions 1–3 so the strip never looks empty. Alert chips occupy positions 4+ and only appear when needed.

**Alarm status / Alarm alert** — Position 1; mutually exclusive pair. Alarm status (green `mdi:shield-home`, "Away" / "Night" / "Home" / "Off") is always visible during normal operation. It hides when the alarm transitions to `triggered`, `pending`, or `arming`, at which point the alarm alert chip (`mdi:shield-alert`, red or orange) takes its place at position 1.

**Vacuum** — Position 2; always visible. Three color states: orange when actively running, green when docked and ran today (`input_select.vacuum_ran_today` = Yes), grey otherwise. Taps to the Vacuum subview.

**Reminders OK / Overdue reminders** — Position 3; mutually exclusive pair. Green `mdi:calendar-check` when `number.overdue_reminders_count` is below 1. Replaced by a red `mdi:calendar-alert` count chip (taps to `/mobile-3/reminders`) when any reminder is overdue. Count label shown only when 2 or more are overdue.

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

The Living Room subview is the pattern for all room subviews. It has five sections:

- **Lights** — 2-col grid of all light entities in the area, no sliders
- **Fan** — `mushroom-fan-card` with speed percentage control
- **Climate** — `mushroom-climate-card` with temperature control
- **Media** — Apple TV (playback controls) and Sonos (volume controls)
- **Sensors** — motion/occupancy binary sensor

Pending room subviews follow this same section structure, including only sections that apply.

---

## Water Leaks Subview

Tap target for the grouped water alert chip on strip 1. Displays all four water leak sensors in a 2×2 grid using `mushroom-entity-card`. Mushroom's device-class awareness for `moisture` sensors provides appropriate icons and state coloring without additional configuration.

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

Four sections:

- **Map** — `picture-entity` showing `image.roborock_q8_max_apartment`, conditionally visible when vacuum is not docked OR `input_select.vacuum_ran_today` is "Yes"
- **Status** — 2-col grid: vacuum state, battery, cleaning area, duration
- **Controls** — Native `tile` card with `vacuum-commands` feature (start/pause, stop, return home); `color: green`, `state_content: [state, area_name]`, `grid_options: {columns: full}`, `features_position: inline`. Only place in this dashboard where a native tile card is used; Mushroom has no vacuum-specific card.
- **Consumables** — 2-col grid of `mushroom-template-card` for filter, main brush, side brush, and sensor. Each card shows hours remaining as secondary text and icon color (red when overdue binary sensor is on, green otherwise). Tap resets the consumable via `button.press` with confirmation. `number.overdue_reminders_count` does not include vacuum consumables — they are tracked independently here.

---

## Climate Subview

Tap target for the thermostat chip on strip 1 (Environment).

**Badges** — Two entity badges in the view header, both blue: `sensor.apartment_temperature` (`mdi:home-thermometer`, labeled "Inside") and `sensor.apartment_humidity` (`mdi:water-percent`, labeled "Inside"). Both are group sensors — tapping either opens more-info showing readings from all member room sensors. Outdoor AQI is accessible via the AQI chip on strip 1 (Home view).

Two sections:

- **Controls** — Thermostat tile (`climate.living_room_thermostat`, `grid_options: {columns: 6}`, `features_position: bottom`, HVAC modes + target temperature + fan modes, `state_content: [current_temperature, current_humidity]`). Comfort Setting tile (`select.living_room_thermostat_current_mode` with `select-options` feature — Home/Sleep/Away). Clear Hold tile (`button.living_room_thermostat_clear_hold`). Below these, an "HVAC Runtime" subtitle heading followed by a `mushroom-template-card` showing today's totals ("Cooling: X.X h · Heating: X.X h") from `sensor.cooling_today` and `sensor.heating_today`. Icon color reflects which mode ran today: blue = cooling, orange = heating, grey = neither.
- **HVAC History** (`collapsed: true`) — 28-day `statistics-graph` line chart (`chart_type: line`, `period: day`, `stat_types: [max]`, `days_to_show: 28`) for `sensor.cooling_today` and `sensor.heating_today`. Hidden by default; tap the section header to expand. Daily max equals daily total since both sensors reset at midnight.

> **Note on `grid_options`:** The `tile` card in a `sections` view defaults to a 1-column layout and renders at half-width unless you set `grid_options: {columns: 12}` (or `columns: full`). This is different from `grid` cards, which fill available width automatically.

---

## Full Dashboard YAML

Complete configuration for `mobile-3`. Apply via `ha_config_set_dashboard(url_path="mobile-3", config=...)` or use as a recovery artifact.

```yaml
# Dashboard metadata (set at creation, not part of view config):
#   url_path: mobile-3
#   title: Mobile 3.0
#   icon: mdi:cellphone
#   show_in_sidebar: true

views:

  # ── Home ──────────────────────────────────────────────────────────────────
  - title: Home
    type: sections
    max_columns: 1
    badges: []
    card_mod:
      style: ":host { --ha-view-sections-column-gap: 8px; } hui-sections-view { --ha-view-sections-column-gap: 8px; }"
    sections:

      # Chip strips — no section title so the block collapses when quiet
      - cards:

          # Strip 1 — Environment (always 3 chips)
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              # Weather — dynamic icon from state; partlycloudy handled specially (MDI naming mismatch)
              - type: template
                icon: "{% set w = states('weather.apartment') %}{% if w == 'partlycloudy' %}mdi:weather-partly-cloudy{% else %}mdi:weather-{{ w }}{% endif %}"
                content: "{{ state_attr('weather.apartment', 'temperature') | int }}°F"
                tap_action: {action: more-info, entity: weather.apartment}
                hold_action: {action: none}
                double_tap_action: {action: none}
              # AQI — template chip fixes the badge gap (125 now covered by accent); mdi:smog = outdoor context
              - type: template
                icon: mdi:smog
                icon_color: "{% set aqi = states('sensor.toledo_ohio_usa_air_quality_index') | int %}{% if aqi >= 126 %}red{% elif aqi >= 101 %}accent{% else %}green{% endif %}"
                content: "{{ states('sensor.toledo_ohio_usa_air_quality_index') }}"
                tap_action: {action: more-info, entity: sensor.toledo_ohio_usa_air_quality_index}
                hold_action: {action: none}
                double_tap_action: {action: none}
              # Thermostat — color = hvac_action; shows current indoor temp
              - type: template
                icon: mdi:home-thermometer
                icon_color: "{% set a = state_attr('climate.living_room_thermostat', 'hvac_action') %}{% if a == 'cooling' %}blue{% elif a == 'heating' %}orange{% else %}grey{% endif %}"
                content: "{{ state_attr('climate.living_room_thermostat', 'current_temperature') | int }}°"
                tap_action: {action: navigate, navigation_path: /mobile-3/climate}
                hold_action: {action: none}
                double_tap_action: {action: none}

          # Strip 2 — Status anchors (positions 1–3, always visible) + alert chips (conditional)
          # Quiet state: 3 chips. Alert chips append to the right without shifting anchors.
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              # Position 1: Alarm status (normal) / Alarm alert (alert) — mutually exclusive
              - type: conditional
                conditions:
                  - condition: state
                    entity: alarm_control_panel.home_alarm
                    state_not: triggered
                  - condition: state
                    entity: alarm_control_panel.home_alarm
                    state_not: pending
                  - condition: state
                    entity: alarm_control_panel.home_alarm
                    state_not: arming
                chip:
                  type: template
                  icon: mdi:shield-home
                  icon_color: green
                  content: "{{ 'Away' if is_state('alarm_control_panel.home_alarm', 'armed_away') else ('Night' if is_state('alarm_control_panel.home_alarm', 'armed_night') else ('Home' if is_state('alarm_control_panel.home_alarm', 'armed_home') else 'Off')) }}"
                  tap_action: {action: more-info, entity: alarm_control_panel.home_alarm}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: or
                    conditions:
                      - condition: state
                        entity: alarm_control_panel.home_alarm
                        state: triggered
                      - condition: state
                        entity: alarm_control_panel.home_alarm
                        state: pending
                      - condition: state
                        entity: alarm_control_panel.home_alarm
                        state: arming
                chip:
                  type: template
                  icon: mdi:shield-alert
                  icon_color: "{{ 'orange' if is_state('alarm_control_panel.home_alarm', 'arming') else 'red' }}"
                  content: ""
                  tap_action: {action: more-info, entity: alarm_control_panel.home_alarm}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Position 2: Vacuum — always visible
              - type: template
                icon: mdi:robot-vacuum
                icon_color: "{{ 'orange' if states('vacuum.roborock_q8_max') != 'docked' else ('green' if is_state('input_select.vacuum_ran_today', 'Yes') else 'grey') }}"
                content: ""
                tap_action: {action: navigate, navigation_path: /mobile-3/vacuum}
                hold_action: {action: none}
                double_tap_action: {action: none}
              # Position 3: Reminders OK (normal) / Overdue reminders (alert) — mutually exclusive
              - type: conditional
                conditions:
                  - condition: numeric_state
                    entity: number.overdue_reminders_count
                    below: 1
                chip:
                  type: entity
                  entity: number.overdue_reminders_count
                  icon: mdi:calendar-check
                  icon_color: green
                  content_info: none
                  tap_action: {action: navigate, navigation_path: /mobile-3/reminders}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: numeric_state
                    entity: number.overdue_reminders_count
                    above: 0
                chip:
                  type: template
                  icon: mdi:calendar-alert
                  icon_color: red
                  content: "{% set c = states('number.overdue_reminders_count') | int %}{{ c if c >= 2 else '' }}"
                  tap_action: {action: navigate, navigation_path: /mobile-3/reminders}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Water leaks — grouped: one chip for all 4 sensors
              - type: conditional
                conditions:
                  - condition: or
                    conditions:
                      - condition: state
                        entity: binary_sensor.kitchen_leak_water_leak
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.bathroom_leak_water_leak
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.master_bathroom_leak_water_leak
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.utility_room_leak_water_leak
                        state_not: "off"
                chip:
                  type: template
                  icon: mdi:water-alert
                  icon_color: red
                  content: >-
                    {% set c = [states('binary_sensor.kitchen_leak_water_leak'),
                    states('binary_sensor.bathroom_leak_water_leak'),
                    states('binary_sensor.master_bathroom_leak_water_leak'),
                    states('binary_sensor.utility_room_leak_water_leak')]
                    | select('ne', 'off') | list | count %}
                    {{ c if c >= 2 else '' }}
                  tap_action: {action: navigate, navigation_path: /mobile-3/water-leaks}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: state
                    entity: binary_sensor.kitchen_freezer_door_contact
                    state_not: "off"
                chip:
                  type: template
                  icon: mdi:fridge-alert
                  icon_color: red
                  content: ""
                  tap_action: {action: more-info, entity: binary_sensor.kitchen_freezer_door_contact}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Exterior doors (red) — any of 3 doors open AND (sleeping OR away)
              - type: conditional
                conditions:
                  - condition: or
                    conditions:
                      - condition: state
                        entity: binary_sensor.garage_interior_door_contact
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.entrance_front_door_contact
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.office_sliding_door_contact
                        state_not: "off"
                  - condition: or
                    conditions:
                      - condition: state
                        entity: input_boolean.everyone_sleeping
                        state: "on"
                      - condition: numeric_state
                        entity: zone.home
                        below: 1
                chip:
                  type: template
                  icon: mdi:door-open
                  icon_color: red
                  content: >-
                    {% set c = [states('binary_sensor.garage_interior_door_contact'),
                    states('binary_sensor.entrance_front_door_contact'),
                    states('binary_sensor.office_sliding_door_contact')]
                    | select('ne', 'off') | list | count %}
                    {{ c if c >= 2 else '' }}
                  tap_action: {action: none}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Exterior doors (orange) — any of 3 doors open AND home AND awake (informational)
              - type: conditional
                conditions:
                  - condition: or
                    conditions:
                      - condition: state
                        entity: binary_sensor.garage_interior_door_contact
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.entrance_front_door_contact
                        state_not: "off"
                      - condition: state
                        entity: binary_sensor.office_sliding_door_contact
                        state_not: "off"
                  - condition: state
                    entity: input_boolean.everyone_sleeping
                    state: "off"
                  - condition: numeric_state
                    entity: zone.home
                    above: 0
                chip:
                  type: template
                  icon: mdi:door-open
                  icon_color: orange
                  content: >-
                    {% set c = [states('binary_sensor.garage_interior_door_contact'),
                    states('binary_sensor.entrance_front_door_contact'),
                    states('binary_sensor.office_sliding_door_contact')]
                    | select('ne', 'off') | list | count %}
                    {{ c if c >= 2 else '' }}
                  tap_action: {action: none}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Garage (red) — open AND (sleeping OR away); tap closes with confirmation
              - type: conditional
                conditions:
                  - condition: and
                    conditions:
                      - condition: state
                        entity: cover.garage_door
                        state_not: closed
                      - condition: or
                        conditions:
                          - condition: state
                            entity: input_boolean.everyone_sleeping
                            state: "on"
                          - condition: numeric_state
                            entity: zone.home
                            below: 1
                chip:
                  type: template
                  icon: mdi:garage-open-variant
                  icon_color: red
                  content: ""
                  tap_action:
                    action: perform-action
                    perform_action: cover.close_cover
                    target: {entity_id: cover.garage_door}
                    confirmation: true
                  hold_action: {action: more-info, entity: cover.garage_door}
                  double_tap_action: {action: none}
              # Garage (orange) — open AND home AND awake (informational); tap closes with confirmation
              - type: conditional
                conditions:
                  - condition: state
                    entity: cover.garage_door
                    state_not: closed
                  - condition: state
                    entity: input_boolean.everyone_sleeping
                    state: "off"
                  - condition: numeric_state
                    entity: zone.home
                    above: 0
                chip:
                  type: template
                  icon: mdi:garage-open-variant
                  icon_color: orange
                  content: ""
                  tap_action:
                    action: perform-action
                    perform_action: cover.close_cover
                    target: {entity_id: cover.garage_door}
                    confirmation: true
                  hold_action: {action: more-info, entity: cover.garage_door}
                  double_tap_action: {action: none}
              # Trash — icon-only
              - type: conditional
                conditions:
                  - condition: state
                    entity: input_boolean.trash_pickup_pending
                    state: "on"
                chip:
                  type: template
                  icon: mdi:trash-can
                  icon_color: red
                  content: ""
                  tap_action: {action: more-info, entity: input_boolean.trash_pickup_pending}
                  hold_action: {action: none}
                  double_tap_action: {action: none}

          # Strip 3 — Modes (all conditional)
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              - type: conditional
                conditions:
                  - condition: state
                    entity: input_boolean.avery_sleeping
                    state: "on"
                  - condition: state
                    entity: input_boolean.everyone_sleeping
                    state: "off"
                chip:
                  type: entity
                  entity: input_boolean.avery_sleeping
                  content_info: name
                  icon_color: green
                  tap_action: {action: toggle, confirmation: true}
                  hold_action: {action: more-info}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: state
                    entity: input_boolean.everyone_sleeping
                    state: "on"
                chip:
                  type: entity
                  entity: input_boolean.everyone_sleeping
                  name: Everyone Sleeping
                  content_info: name
                  icon_color: green
                  tap_action: {action: toggle, confirmation: true}
                  hold_action: {action: more-info}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: state
                    entity: switch.living_room_sync_box_power
                    state: "on"
                  - condition: state
                    entity: media_player.living_room_tv
                    state: "on"
                chip:
                  type: entity
                  entity: switch.living_room_sync_box_light_sync
                  name: Light Sync
                  content_info: name
                  icon_color: green
                  tap_action: {action: toggle}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: state
                    entity: media_player.living_room_tv
                    state: "on"
                chip:
                  type: entity
                  entity: input_boolean.movie_mode
                  name: Movie Mode
                  content_info: name
                  icon_color: green
                  tap_action: {action: toggle}
                  hold_action: {action: more-info}
                  double_tap_action: {action: none}
              - type: conditional
                conditions:
                  - condition: state
                    entity: media_player.living_room_tv
                    state: "on"
                chip:
                  type: entity
                  entity: input_boolean.sonos_night_mode
                  name: Quiet Mode
                  icon: mdi:weather-night
                  content_info: name
                  icon_color: yellow
                  tap_action: {action: toggle}
                  hold_action: {action: none}
                  double_tap_action: {action: none}

          # Strip 4 — Presence (always visible)
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              - type: entity
                entity: person.nate
                use_entity_picture: true
                content_info: state
                tap_action: {action: more-info}
                hold_action: {action: none}
                double_tap_action: {action: none}
              - type: entity
                entity: person.guest
                icon: mdi:alpha-g-circle
                icon_color: green
                content_info: state
                tap_action: {action: none}
                hold_action:
                  action: perform-action
                  perform_action: input_boolean.toggle
                  target: {entity_id: input_boolean.guest_mode}
                double_tap_action: {action: none}

      # Rooms
      - title: Rooms
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-light-card
                entity: light.living_room_fan
                name: Living Room
                icon: mdi:sofa
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/living-room}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-light-card
                entity: light.master_bedroom_fan
                name: Master Bedroom
                icon: mdi:bed-king
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/master-bedroom}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-light-card
                entity: light.avery_room_ceiling
                name: Avery's Room
                icon: mdi:teddy-bear
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/averys-room}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-light-card
                entity: light.office_ceiling
                name: Office
                icon: mdi:desktop-classic
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/office}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-light-card
                entity: light.kitchen_ceiling
                name: Kitchen
                icon: mdi:countertop
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/kitchen}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-light-card
                entity: light.bathroom_hallway_ceiling
                name: Bathroom
                icon: mdi:toilet
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
                tap_action: {action: navigate, navigation_path: /mobile-3/bathroom}
                hold_action: {action: toggle}
                double_tap_action: {action: none}
              - type: custom:mushroom-cover-card
                entity: cover.garage_door
                name: Garage
                icon: mdi:car
                show_buttons_control: true
                tap_action: {action: navigate, navigation_path: /mobile-3/garage}
                hold_action: {action: more-info}
                double_tap_action: {action: none}
              - type: custom:mushroom-entity-card
                entity: sensor.outside_temperature
                name: Outside
                icon: mdi:tree
                tap_action: {action: navigate, navigation_path: /mobile-3/outside}
                hold_action: {action: none}
                double_tap_action: {action: none}


  # ── Living Room (subview — reference implementation) ──────────────────────
  - title: Living Room
    path: living-room
    type: sections
    subview: true
    max_columns: 1
    sections:
      - title: Lights
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-light-card
                entity: light.living_room_fan
                name: Ceiling
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
              - type: custom:mushroom-light-card
                entity: light.living_room_movie_posters
                name: Movie Posters
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
              - type: custom:mushroom-light-card
                entity: light.living_room_status_lamp
                name: Status Lamp
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
              - type: custom:mushroom-light-card
                entity: light.living_room_tv_lights
                name: TV Lights
                use_light_color: true
                show_brightness_control: false
                show_color_temp_control: false
                show_color_control: false
      - title: Fan
        cards:
          - type: custom:mushroom-fan-card
            entity: fan.living_room_ceiling
            name: Ceiling Fan
            show_percentage_control: true
            show_oscillate_control: false
      - title: Climate
        cards:
          - type: custom:mushroom-climate-card
            entity: climate.living_room_thermostat
            show_temperature_control: true
      - title: Media
        cards:
          - type: custom:mushroom-media-player-card
            entity: media_player.living_room_appletv
            name: Apple TV
            use_media_info: true
            show_volume_level: true
            media_controls: [play_pause_stop, previous, next]
          - type: custom:mushroom-media-player-card
            entity: media_player.living_room_sonos
            name: Sonos
            use_media_info: true
            show_volume_level: true
            volume_controls: [volume_set, volume_mute]
      - title: Sensors
        cards:
          - type: custom:mushroom-entity-card
            entity: binary_sensor.living_room_motion_occupancy
            name: Motion

  # ── Climate (utility subview) ────────────────────────────────────────────
  - title: Climate
    path: climate
    type: sections
    subview: true
    max_columns: 1
    badges:
      # Both blue; both are group sensors — tap opens per-room breakdown via more-info
      - type: entity
        entity: sensor.apartment_temperature
        name: Inside
        icon: mdi:home-thermometer
        color: blue
      - type: entity
        entity: sensor.apartment_humidity
        name: Inside
        icon: mdi:water-percent
        color: blue
    sections:
      - cards:
          - type: heading
            heading: Controls
          - type: tile
            grid_options:
              columns: 6
            entity: climate.living_room_thermostat
            name: Thermostat
            state_content: [current_temperature, current_humidity]
            features:
              - type: climate-hvac-modes
                hvac_modes: [off, heat, cool, heat_cool]
              - type: target-temperature
              - type: climate-fan-modes
                fan_modes: [auto, on]
            features_position: bottom
          # Comfort setting — Home/Sleep/Away buttons
          - type: tile
            entity: select.living_room_thermostat_current_mode
            name: Comfort Setting
            features:
              - type: select-options
          # Clear Hold — removes any active thermostat hold
          - type: tile
            entity: button.living_room_thermostat_clear_hold
            name: Clear Hold
          - type: heading
            heading: HVAC Runtime
            heading_style: subtitle
          # icon_color: blue=cooling ran today, orange=heating ran today, grey=neither
          - type: custom:mushroom-template-card
            primary: Today
            secondary: "Cooling: {{ states('sensor.cooling_today') | float | round(1) }} h · Heating: {{ states('sensor.heating_today') | float | round(1) }} h"
            icon: mdi:heat-pump
            icon_color: "{{ 'blue' if states('sensor.cooling_today') | float > 0 else ('orange' if states('sensor.heating_today') | float > 0 else 'grey') }}"
            tap_action: {action: none}
            hold_action: {action: none}
            double_tap_action: {action: none}

      # Collapsed by default — tap section header to expand
      - title: HVAC History
        collapsed: true
        cards:
          # daily max = daily total since sensors reset at midnight
          - type: statistics-graph
            grid_options:
              columns: full
              rows: auto
            entities:
              - entity: sensor.cooling_today
                name: Cooling
              - entity: sensor.heating_today
                name: Heating
            stat_types: [max]
            period: day
            days_to_show: 28
            chart_type: line

  # ── Water Leaks (utility subview) ─────────────────────────────────────────
  - title: Water Leaks
    path: water-leaks
    type: sections
    subview: true
    max_columns: 1
    sections:
      - title: Sensors
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-entity-card
                entity: binary_sensor.kitchen_leak_water_leak
                name: Kitchen
              - type: custom:mushroom-entity-card
                entity: binary_sensor.bathroom_leak_water_leak
                name: Bathroom
              - type: custom:mushroom-entity-card
                entity: binary_sensor.master_bathroom_leak_water_leak
                name: Master Bath
              - type: custom:mushroom-entity-card
                entity: binary_sensor.utility_room_leak_water_leak
                name: Utility

  # ── Reminders (utility subview) ──────────────────────────────────────────
  - title: Reminders
    path: reminders
    type: sections
    subview: true
    max_columns: 1
    sections:
      - title: Household
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              # Pattern: icon_color template (red/green), secondary = formatted due date,
              # tap = more-info on input_datetime, hold = set today (mark complete)
              - type: custom:mushroom-template-card
                primary: Car Washed
                secondary: "{{ strptime(states('sensor.accord_washed_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:car-wash
                icon_color: "{{ 'red' if is_state('binary_sensor.accord_washed_overdue', 'on') else 'green' }}"
                entity: input_datetime.accord_washed
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.accord_washed}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Coffee Grinder
                secondary: "{{ strptime(states('sensor.coffee_grinder_cleaned_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:coffee-maker
                icon_color: "{{ 'red' if is_state('binary_sensor.coffee_grinder_cleaned_overdue', 'on') else 'green' }}"
                entity: input_datetime.coffee_grinder_cleaned
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.coffee_grinder_cleaned}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Dishwasher
                secondary: "{{ strptime(states('sensor.dishwasher_cleaned_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:dishwasher
                icon_color: "{{ 'red' if is_state('binary_sensor.dishwasher_cleaned_overdue', 'on') else 'green' }}"
                entity: input_datetime.dishwasher_cleaned
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.dishwasher_cleaned}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Disposal
                secondary: "{{ strptime(states('sensor.disposal_cleaned_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:delete-sweep
                icon_color: "{{ 'red' if is_state('binary_sensor.disposal_cleaned_overdue', 'on') else 'green' }}"
                entity: input_datetime.disposal_cleaned
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.disposal_cleaned}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Razor Blade
                secondary: "{{ strptime(states('sensor.razor_blade_changed_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:razor-single-edge
                icon_color: "{{ 'red' if is_state('binary_sensor.razor_blade_changed_overdue', 'on') else 'green' }}"
                entity: input_datetime.razor_blade_changed
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.razor_blade_changed}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Toothbrushes
                secondary: "{{ strptime(states('sensor.toothbrushes_changed_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:toothbrush
                icon_color: "{{ 'red' if is_state('binary_sensor.toothbrushes_changed_overdue', 'on') else 'green' }}"
                entity: input_datetime.toothbrushes_changed
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.toothbrushes_changed}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Washer
                secondary: "{{ strptime(states('sensor.washer_cleaned_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:washing-machine
                icon_color: "{{ 'red' if is_state('binary_sensor.washer_cleaned_overdue', 'on') else 'green' }}"
                entity: input_datetime.washer_cleaned
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.washer_cleaned}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Water Filter
                secondary: "{{ strptime(states('sensor.water_filter_changed_due'), '%Y-%m-%d').strftime('%B %-d, %Y') }}"
                icon: mdi:water-pump
                icon_color: "{{ 'red' if is_state('binary_sensor.water_filter_changed_overdue', 'on') else 'green' }}"
                entity: input_datetime.water_filter_changed
                tap_action: {action: more-info}
                hold_action:
                  action: perform-action
                  perform_action: input_datetime.set_datetime
                  target: {entity_id: input_datetime.water_filter_changed}
                  data: {date: "{{ now().date() | string }}"}
                  confirmation: true
                double_tap_action: {action: none}
  # ── Vacuum (utility subview) ──────────────────────────────────────────────
  - title: Vacuum
    path: vacuum
    type: sections
    subview: true
    max_columns: 1
    sections:
      - title: Map
        cards:
          # Map shown when vacuum is active OR ran today (input_select set by automation)
          - type: conditional
            conditions:
              - condition: or
                conditions:
                  - condition: state
                    entity: vacuum.roborock_q8_max
                    state_not: docked
                  - condition: state
                    entity: input_select.vacuum_ran_today
                    state: "Yes"
            card:
              type: picture-entity
              entity: image.roborock_q8_max_apartment
              show_state: false
              show_name: false
      - title: Status
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-entity-card
                entity: vacuum.roborock_q8_max
                name: Vacuum
                content_info: state
                tap_action: {action: more-info}
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_battery
                name: Battery
                content_info: state
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_cleaning_area
                name: "Area (m²)"
                content_info: state
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_cleaning_time
                name: Duration (min)
                content_info: state
      - title: Controls
        # Native tile used here — Mushroom has no vacuum-specific card
        cards:
          - type: tile
            grid_options:
              rows: auto
              columns: full
            entity: vacuum.roborock_q8_max
            name: Roborock Q8 Max
            color: green
            state_content: [state, area_name]
            vertical: false
            features:
              - type: vacuum-commands
                commands: [start_pause, stop, return_home]
            features_position: inline
      - title: Consumables
        cards:
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-template-card
                primary: Filter
                secondary: "{{ states('sensor.roborock_q8_max_filter_time_left') | round(0) | int }}h remaining"
                icon: mdi:air-filter
                icon_color: "{{ 'red' if is_state('binary_sensor.roborock_replace_filter', 'on') else 'green' }}"
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target: {entity_id: button.roborock_q8_max_reset_air_filter_consumable}
                  confirmation: true
                hold_action: {action: none}
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Main Brush
                secondary: "{{ states('sensor.roborock_q8_max_main_brush_time_left') | round(0) | int }}h remaining"
                icon: mdi:brush
                icon_color: "{{ 'red' if is_state('binary_sensor.roborock_replace_main_brush', 'on') else 'green' }}"
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target: {entity_id: button.roborock_q8_max_reset_main_brush_consumable}
                  confirmation: true
                hold_action: {action: none}
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Side Brush
                secondary: "{{ states('sensor.roborock_q8_max_side_brush_time_left') | round(0) | int }}h remaining"
                icon: mdi:fan
                icon_color: "{{ 'red' if is_state('binary_sensor.roborock_replace_side_brush', 'on') else 'green' }}"
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target: {entity_id: button.roborock_q8_max_reset_side_brush_consumable}
                  confirmation: true
                hold_action: {action: none}
                double_tap_action: {action: none}
              - type: custom:mushroom-template-card
                primary: Sensor
                secondary: "{{ states('sensor.roborock_q8_max_sensor_time_left') | round(0) | int }}h remaining"
                icon: mdi:smoke-detector
                icon_color: "{{ 'red' if is_state('binary_sensor.roborock_clean_sensor', 'on') else 'green' }}"
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target: {entity_id: button.roborock_q8_max_reset_sensor_consumable}
                  confirmation: true
                hold_action: {action: none}
                double_tap_action: {action: none}
```

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
