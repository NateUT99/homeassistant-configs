# Dashboard Design Standard

Version 0.1

| Version | Date | Changes |
|---|---|---|
| 0.1 | June 2026 | Initial draft — patterns established during Mobile 3.0 build |

---

## Purpose & Scope

This standard governs the design and construction of all Home Assistant storage-mode dashboards in this instance. It covers visual layer choices, card conventions, chip strip design, room tile and subview patterns, and HACS dependency policy.

Scope: storage-mode dashboards created via the HA UI or `ha_config_set_dashboard`. YAML-mode dashboards (`configuration.yaml`) are out of scope.

---

## Core Principles

- **Mushroom Cards are the primary visual layer.** Use `custom:mushroom-*` cards for rooms, entities, climate, alarm, media, and fan. Do not use native `tile` cards in the primary room or status sections — reserve tile cards for specialized feature sets that Mushroom lacks (e.g., `vacuum-commands` in a utility subview).
- **No brightness or color sliders on room tiles or light cards.** Adaptive Lighting manages brightness and color temperature automatically. Exposing a slider creates a confusing dual-control surface. Set `show_brightness_control: false`, `show_color_temp_control: false`, `show_color_control: false` on all `mushroom-light-card` instances.
- **Native subviews replace popups.** Use `subview: true` views for room drill-down and utility pages. Do not use Bubble Card or any other popup framework on this dashboard.
- **Single-column sections on mobile.** All mobile dashboards use `max_columns: 1`. Desktop dashboards may use higher column counts; establish separately when built.
- **The design target is between Apple Home and full HA.** Sufficient ambient context at a glance (chip strips, room state), with tap to drill down. Avoid information density that requires interpretation; save raw sensor data for subviews.

---

## HACS Dependency Policy

Only the following frontend resources are approved for use across all dashboards:

| Resource | URL path | Purpose |
|---|---|---|
| Mushroom Cards | `/hacsfiles/lovelace-mushroom/mushroom.js` | Primary card visual layer |
| card-mod | `/hacsfiles/lovelace-card-mod/card-mod.js` | CSS variable injection for chip sizing and style overrides |

Do not introduce additional HACS frontend resources without explicit decision. When a capability gap arises, first check whether a native HA card or Mushroom card covers it before reaching for a new dependency.

---

## Dashboard Naming

| Property | Convention |
|---|---|
| `url_path` | Short hyphenated slug: `mobile-3`, `desktop-1` |
| `title` | Human-readable with version: `Mobile 3.0`, `Desktop 1.0` |
| `icon` | Reflects the target device: `mdi:cellphone` for mobile, `mdi:monitor` for desktop |
| `show_in_sidebar` | `true` |

---

## Home View Structure

Every dashboard's primary view is titled **Home**, uses `type: sections` and `max_columns: 1` (mobile). It contains three sections and optionally view-level header badges.

**Header badges** — optional ambient environmental context visible without scrolling. Use only for read-only, non-navigational context; badges have limited tap affordance and no conditional-hide behavior. If color differentiation is needed, use three conditional copies of the same entity with distinct static `color` values and `visibility` conditions (entity badges don't support template colors). An alternative approach: place always-visible ambient context in a dedicated first chip strip instead of badges — this eliminates the badge-to-section spacing gap and allows `type: template` color logic directly.

**Sections**, in this order:

1. **Chip strips** — no section title (omitting the title lets the section collapse visually when all chips are inactive)
2. **Rooms** — room tile grid
3. **House** — cross-room utility controls (climate, alarm, vacuum)

Do not reorder these sections or add sections between them without updating this standard.

---

## Chip Strip System

The chip strip section contains `custom:mushroom-chips-card` rows stacked vertically (Mobile 3.0 uses four). Apply card-mod sizing to every strip:

```yaml
card_mod:
  style: "ha-card { --chip-height: 30px; --chip-padding: 0 6px; }"
```

All strips use `alignment: center`.

### Strip 1 — Safety Alerts

Fully conditional: only chips whose entity is in an alert state are rendered. When all entities are normal the strip is empty.

**Critical rule: use `type: template` for inner chips, not `type: entity`.** The `type: entity` chip applies Mushroom's device-class state color at render time, which overrides a static `icon_color`. When a binary sensor is in `unknown` or `unavailable` state (both satisfy `state_not: "off"`), the chip renders with the entity's native color rather than red. `type: template` renders purely from the YAML values and always produces the intended red.

```yaml
# Correct
chip:
  type: template
  icon: mdi:water-alert
  icon_color: red
  content: Kitchen
  tap_action: {action: more-info, entity: binary_sensor.kitchen_leak_water_leak}

# Wrong — icon_color: red may be overridden by entity state color
chip:
  type: entity
  entity: binary_sensor.kitchen_leak_water_leak
  icon_color: red
```

**Contextual gate for door and garage alerts.** These entities open routinely during the day; surfacing them as alerts at all times creates noise. Apply a compound condition: only alert when the entity is open AND the household is sleeping OR nobody is home:

```yaml
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
```

Water leaks and freezer door do not use a contextual gate — they are always alert-worthy.

### Strip 2 — Device Active Status

Conditional chips for devices that are actively doing something useful to surface (e.g., vacuum cleaning). Use `type: entity` chips here since state-based coloring is appropriate for active-device status. Each chip navigates to the device's utility subview on tap.

### Strip 3 — Modes and Persistent Status

Contextual mode indicators (sleeping states, media modes) plus persistent status indicators (reminders). Modes are conditional and use `type: entity`. The reminders indicator is always present: a green `mdi:calendar-check` chip when the overdue count is zero, replaced by a red `mdi:calendar-alert` chip showing the count when nonzero. Both navigate to the `/reminders` subview.

### Strip 4 — Presence

Always-visible person chips. The primary resident uses `use_entity_picture: true`. Guest presence is a hold-to-toggle pattern (tap does nothing; hold toggles `input_boolean.guest_mode`) to prevent accidental activation.

---

## Room Tiles

Room tiles live in the Rooms section in a 2-column grid (`type: grid, columns: 2, square: false`).

**Standard room tile** (room has a primary ceiling light):

```yaml
type: custom:mushroom-light-card
entity: light.<area>_ceiling         # primary light entity — see note below
name: <Room Name>
icon: <mdi icon representing the room>
use_light_color: true
show_brightness_control: false       # Adaptive Lighting owns brightness
show_color_temp_control: false
show_color_control: false
tap_action:
  action: navigate
  navigation_path: /mobile-3/<room-path>
hold_action:
  action: toggle                     # quick on/off without navigating
double_tap_action:
  action: none
```

**Fallback patterns** (rooms without a primary light):

| Room type | Card type | Entity |
|---|---|---|
| Garage (cover only) | `custom:mushroom-cover-card` | `cover.garage_door` |
| Outside (sensor only) | `custom:mushroom-entity-card` | `sensor.outside_temperature` |

> **Note on primary light entity:** The entity bound to a room tile should be the room's primary ceiling light (the one that best represents "is this room lit?"). In some rooms this is currently a fan entity (`light.living_room_fan`, `light.master_bedroom_fan`) because those lights are part of a ceiling fan unit. This conflicts with `standards/naming.md`'s location-first naming rule — a cleanup pass is tracked separately.

---

## Room Subview Structure

Each room gets a view with `subview: true`. HA renders a back arrow automatically; no manual back-navigation card is needed.

Standard sections, include only those that apply to the room:

| Section | Content | Required |
|---|---|---|
| Lights | 2-col grid of `mushroom-light-card` for every light in the area | Yes |
| Fan | `mushroom-fan-card` with `show_percentage_control: true` | If room has a ceiling fan |
| Climate | `mushroom-climate-card` with `show_temperature_control: true` | If room has a thermostat |
| Media | `mushroom-media-player-card` per device | If room has addressable media |
| Sensors | `mushroom-entity-card` per binary sensor (motion, occupancy, door, etc.) | If room has sensors |

All light cards in subviews follow the same no-slider rule as room tiles.

---

## Utility Subviews

Utility subviews (Reminders, Vacuum, and future equivalents) are not room subviews — they are navigated from chip tap actions, not room tiles. They follow the same `subview: true` pattern but are not required to follow the room section structure.

For reminder cards, use `custom:mushroom-template-card` with:
- `icon_color` as a Jinja template (`red` when overdue, `green` otherwise)
- `secondary` showing the formatted due date: `strptime(...).strftime('%B %-d, %Y')`
- `hold_action` calling `input_datetime.set_datetime` with today's date (mark complete), with `confirmation: {text: "Mark <name> as done today?"}`

---

**Confirmation dialogs must always include descriptive text.** Never use `confirmation: true` (bare boolean). Always use the object form with a `text` field that tells the user exactly what will happen:

```yaml
# Wrong
confirmation: true

# Correct
confirmation:
  text: "Close garage door?"
```

The text should describe the irreversible or consequential action in plain language. Match tense to the action: "Close garage door?", "Reset filter usage counter?", "Mark Car Washed as done today?".

---

## Quick Reference

| Pattern | Card type | Notes |
|---|---|---|
| Room tile | `mushroom-light-card` | No sliders; tap=navigate, hold=toggle |
| Room tile (no light) | `mushroom-cover-card` or `mushroom-entity-card` | Garage, Outside |
| Alert chip | `type: template` inside `conditional` | Not `type: entity` — ensures static red |
| Mode/status chip | `type: entity` inside `conditional` | State color acceptable here |
| Reminder card | `mushroom-template-card` | Template icon_color; hold=mark complete |
| Chip sizing | `card_mod` → `--chip-height: 30px` | Applied to every `mushroom-chips-card` |
| Subview nav | `type: sections, subview: true` | HA renders back arrow automatically |
| Vacuum controls | Native `tile` with `vacuum-commands` feature | Only place native tile is used |
| Confirmation dialog | `confirmation: {text: "..."}` | Never bare `confirmation: true` |
