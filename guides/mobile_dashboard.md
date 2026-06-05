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
│   │   ├── Strip 1: General Alerts  ← icon-only, hidden when quiet
│   │   │   ├── Alarm alert [red/orange]    triggered or pending = red; arming = orange → tap more-info
│   │   │   ├── Water leak [red]            any of 4 sensors not off → tap navigates to /water-leaks; count if 2+
│   │   │   ├── Freezer open [red]          kitchen_freezer_door_contact not off → tap more-info
│   │   │   ├── Exterior door [red]         any of 3 doors open AND (sleeping OR away) → count if 2+
│   │   │   ├── Exterior door [orange]      any of 3 doors open AND home AND awake → count if 2+
│   │   │   ├── Garage open [red]           not closed AND (sleeping OR away) → tap closes w/ confirm
│   │   │   ├── Garage open [orange]        not closed AND home AND awake → tap closes w/ confirm
│   │   │   ├── Trash pickup [red]          trash_pickup_pending on → label "Trash", "Recycling", or "Both"
│   │   │   └── Overdue reminders [red]     count > 0 → tap navigates to /reminders; count if 2+
│   │   │
│   │   ├── Strip 2: Device & Persistent Status  ← always visible
│   │   │   ├── Alarm status        (green shield, Away/Home/Off, hidden during alert) ← col 1 mirrors strip 1
│   │   │   ├── Vacuum [grey/orange/green]   grey=docked+not run today, orange=running, green=docked+ran today → /vacuum
│   │   │   ├── Thermostat [grey/orange/blue] grey=idle, orange=heating, blue=cooling; shows current temp → /climate
│   │   │   └── Reminders OK        (green calendar-check, hidden when any overdue)
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
│   │
│   └── Weather
│       ├── Daily forecast  weather.apartment
│       ├── Temperature     sensor.outside_temperature
│       └── Humidity        sensor.outside_humidity
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
│   ├── Household        car, coffee grinder, dishwasher, disposal,
│   │                    razor, toothbrushes, washer, water filter
│   └── Vacuum Maint.    filter, main brush, side brush, sensor
│
├── Vacuum        (utility subview)
│   ├── Map         conditional picture-entity
│   ├── Status      state, battery, area, duration
│   ├── Controls    native tile with vacuum-commands feature
│   └── Consumables filter, main brush, sensor, side brush (hours remaining)
│
├── Climate       (utility subview — tap target for thermostat chip)
│   │             Badges: Inside temp+humidity (apartment sensors, blue), Outside temp+humidity (amber)
│   ├── Controls  thermostat tile + comfort select (home/sleep/away) + clear hold
│   │             + HVAC Runtime subtitle + 28-day line chart (cooling + heating)
│   └── Weather   weather.apartment daily forecast
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

### Strip 1 — General Alerts

Surfaces any active hazard or condition requiring attention. All chips are icon-only (no content label) and use `type: template` so `icon_color: red` is always respected regardless of entity state. See `standards/dashboards.md` for why `type: entity` breaks static icon colors for sensors in `unknown` state.

When the strip is empty (no active alerts), it renders as zero-height and no visual gap remains.

**Alarm** — First chip; highest urgency. Covers three states: `triggered` and `pending` render red (`mdi:shield-alert`); `arming` renders orange. Disappears when the alarm is disarmed or armed normally — those states show as a green chip on strip 2 instead.

**Water leaks** — A single chip replaces four individual sensors. An OR condition across all four sensors (`state_not: "off"`) activates it; tapping navigates to the Water Leaks subview showing all four. `state_not: "off"` is intentional: `unknown` state (sensor offline) also triggers the chip as a conservative default for water detection.

**Freezer door** — Always-alert: no contextual gate.

**Exterior doors** — Two chips, mutually exclusive, covering three sensors: garage interior door (`binary_sensor.garage_interior_door_contact`), front door (`binary_sensor.entrance_front_door_contact`), and office sliding door (`binary_sensor.office_sliding_door_contact`). Orange when any door is open AND someone is home AND awake (informational). Red when any door is open AND (sleeping OR nobody home) — the contextual alert. Count shown when 2 or more doors are open.

**Garage door** — Two chips, mutually exclusive. Orange when the door is open AND someone is home AND nobody is sleeping (informational — door left open during normal hours). Red when open AND (sleeping OR away) — the contextual alert. Only one chip is ever visible at a time. Both chips use tap-to-close with confirmation; hold shows `more-info`.

**Trash pickup** — `input_boolean.trash_pickup_pending` is the gate. Icon-only; no content label.

**Overdue reminders** — Moved here from strip 3. Shows a count label only when 2 or more reminders are overdue; icon-only when exactly 1 is overdue. Tapping navigates to `/mobile-3/reminders`.

### Strip 2 — Device and Persistent Status

Always-present indicators that represent ongoing or normal-state conditions. Uses `type: entity` chips where state-based coloring is appropriate.

**Alarm status** — Position 1, mirroring the strip 1 alarm chip. Green `mdi:shield-home` showing "Away", "Home", or "Off" depending on `alarm_control_panel.home_alarm` state. Hides when the alarm is in any alert state (triggered/pending/arming), at which point the strip 1 alarm chip takes over at the same column position.

**Vacuum** — Always visible. Three color states driven by `type: template`: orange when actively running (state not `docked`), green when docked and `input_select.vacuum_ran_today` = Yes, grey when docked and not yet run today. Taps to the Vacuum subview.

**Thermostat** — Always visible. Shows current indoor temperature as content. Color reflects the `hvac_action` attribute (not the mode state): blue = cooling, orange = heating, grey = idle. Taps to the Climate subview.

**Reminders OK** — Green `mdi:calendar-check`, visible when `number.overdue_reminders_count` is below 1. No content label. Taps to `/mobile-3/reminders`. Disappears when any reminder is overdue; strip 1 shows the red count chip instead.

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

**Vacuum Maintenance** — 2-col grid of `mushroom-template-card` for the four Roborock Q8 Max consumables. Each card shows hours remaining and taps to reset the consumable (with confirmation). Icon is red when the consumable's overdue binary sensor is active.

---

## Vacuum Subview

Four sections:

- **Map** — `picture-entity` showing `image.roborock_q8_max_apartment`, conditionally visible when vacuum is not docked OR `input_select.vacuum_ran_today` is "Yes"
- **Status** — 2-col grid: vacuum state, battery, cleaning area, duration
- **Controls** — Native `tile` card with `vacuum-commands` feature (start/pause, stop, return home); `color: green`, `state_content: [state, area_name]`, `grid_options: {columns: full}`, `features_position: inline`. Only place in this dashboard where a native tile card is used; Mushroom has no vacuum-specific card.
- **Consumables** — 2-col grid of the four time-left sensors (read-only; actionable reset is in the Reminders subview)

---

## Climate Subview

Tap target for the thermostat chip on strip 2.

**Badges** — Four entity badges in the view header. Blue pair (`mdi:home-thermometer` + `mdi:water-percent`, both labeled "Inside"): `sensor.apartment_temperature` and `sensor.apartment_humidity`. Amber pair (`mdi:sun-thermometer` + `mdi:water-percent`, both labeled "Outside"): `sensor.outside_temperature` and `sensor.outside_humidity`. Icon differentiates temperature from humidity within each pair; color differentiates inside from outside.

Two sections:

- **Controls** — Thermostat tile (`climate.living_room_thermostat`, `grid_options: {columns: 6}`, `features_position: bottom`, HVAC modes + target temperature + fan modes, `state_content: [current_temperature, current_humidity]`). Comfort Setting tile (`select.living_room_thermostat_current_mode` with `select-options` feature — Home/Sleep/Away). Clear Hold tile (`button.living_room_thermostat_clear_hold`). Below these, an "HVAC Runtime" subtitle heading followed by a `statistics-graph` line chart (`chart_type: line`, `period: day`, `stat_types: [max]`, `days_to_show: 28`, `grid_options: {columns: full}`) for `sensor.cooling_today` and `sensor.heating_today` — two lines showing cooling and heating daily totals over 4 weeks; daily max equals daily total since both sensors reset at midnight.
- **Weather** — `weather-forecast` card for `weather.apartment` (`forecast_type: daily`).

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
    card_mod:
      style: ":host { --ha-view-sections-column-gap: 8px; } hui-sections-view { --ha-view-sections-column-gap: 8px; }"
    sections:

      # Chip strips — no section title so the block collapses when quiet
      - cards:

          # Strip 1 — General alerts (icon-only; type: template required so
          # icon_color: red is always respected regardless of entity state)
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              # Alarm — highest urgency; appears first; orange when arming, red when triggered or pending
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
              # Water leaks — grouped: one chip for all 4 sensors, navigates to subview
              # Count shown only when 2 or more sensors are active
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
              # Count shown when 2 or more doors are open
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
              # Overdue reminders — count shown only when 2 or more overdue
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

          # Strip 2 — Device and persistent status
          - type: custom:mushroom-chips-card
            alignment: center
            card_mod:
              style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
            chips:
              # Alarm status — position 1, mirrors strip 1 alarm chip column position
              # Green when normal; hides when strip 1 alarm chip is active
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
                  content: "{{ 'Away' if is_state('alarm_control_panel.home_alarm', 'armed_away') else ('Home' if is_state('alarm_control_panel.home_alarm', 'armed_home') else 'Off') }}"
                  tap_action: {action: more-info, entity: alarm_control_panel.home_alarm}
                  hold_action: {action: none}
                  double_tap_action: {action: none}
              # Vacuum — always visible; 3 states: orange=running, green=ran today, grey=not run yet
              - type: template
                icon: mdi:robot-vacuum
                icon_color: "{{ 'orange' if states('vacuum.roborock_q8_max') != 'docked' else ('green' if is_state('input_select.vacuum_ran_today', 'Yes') else 'grey') }}"
                content: ""
                tap_action: {action: navigate, navigation_path: /mobile-3/vacuum}
                hold_action: {action: none}
                double_tap_action: {action: none}
              # Thermostat — always visible; color = hvac_action (blue=cooling, orange=heating, grey=idle)
              # Uses hvac_action attribute, not mode state, to reflect what the system is actually doing
              - type: template
                icon: mdi:home-thermometer
                icon_color: "{{ 'blue' if state_attr('climate.living_room_thermostat', 'hvac_action') == 'cooling' else ('orange' if state_attr('climate.living_room_thermostat', 'hvac_action') == 'heating' else 'grey') }}"
                content: "{{ state_attr('climate.living_room_thermostat', 'current_temperature') | int }}°"
                tap_action: {action: navigate, navigation_path: /mobile-3/climate}
                hold_action: {action: none}
                double_tap_action: {action: none}
              # Reminders OK — hides when any reminder is overdue (strip 1 shows count instead)
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

      # Weather
      - title: Weather
        cards:
          - type: weather-forecast
            entity: weather.apartment
            forecast_type: daily
          - type: grid
            columns: 2
            square: false
            cards:
              - type: custom:mushroom-entity-card
                entity: sensor.outside_temperature
                name: Temperature
              - type: custom:mushroom-entity-card
                entity: sensor.outside_humidity
                name: Humidity

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
      # Blue = inside; amber = outside. Icon differentiates temp from humidity within each pair.
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
      - type: entity
        entity: sensor.outside_temperature
        name: Outside
        icon: mdi:sun-thermometer
        color: amber
      - type: entity
        entity: sensor.outside_humidity
        name: Outside
        icon: mdi:water-percent
        color: amber
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
          # 28-day line: daily max = daily total since sensors reset at midnight
          # Two lines (cooling + heating) show usage pattern and week-over-week trend
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
      - cards:
          - type: heading
            heading: Weather
          - type: weather-forecast
            entity: weather.apartment
            forecast_type: daily

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
                icon: mdi:razor
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
      - title: Vacuum Maintenance
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
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_filter_time_left
                name: Filter
                content_info: state
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_main_brush_time_left
                name: Main Brush
                content_info: state
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_sensor_time_left
                name: Sensor
                content_info: state
              - type: custom:mushroom-entity-card
                entity: sensor.roborock_q8_max_side_brush_time_left
                name: Side Brush
                content_info: state
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
