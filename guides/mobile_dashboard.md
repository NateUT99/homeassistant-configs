# Mobile Dashboard

*Last updated: July 2026*

---

## Overview

`mobile-home` is the primary mobile dashboard for the HA instance, built on Bubble Card and native HA cards throughout. It targets the iOS Companion App and aims for Apple Home-style clarity: header badges for ambient alerts at a glance, a feature-toggle chip strip where each chip navigates to a Bubble Card pop-up, and pop-up overlays for all feature detail views.

The dashboard replaced `mobile-app` (which used Mushroom + native tile cards throughout) in June 2026. `mobile-app` is retired; `mobile-3` (Mobile 3.0) is a separate dashboard and was not affected by this migration.

Adaptive Lighting manages all brightness and color temperature — no brightness sliders appear anywhere on this dashboard.

---

## Architecture

```
mobile-home (storage-mode dashboard, url_path: mobile-home)
│
└── Home (sections, max_columns=1)
    │
    ├── [header badges — view header, always visible]
    │   ├── Alarm (always)
    │   ├── Conditional alerts: water leak, freezer door,
    │   │   exterior doors ×2 (red/orange), garage ×3 (red/orange/green)
    │   ├── Status: Weather, AQI, Guest (always)
    │   └── Avery sleeping (time-gated: 06:30–09:00 when sleeping; 20:30–22:30 when home today)
    │
    ├── [toggle chip strip — single section, no title]
    │   └── Bubble Card sub-buttons: Thermostat, Vacuum, Reminders (ok/alert), Washer, Dryer, Trash
    │       └── each chip tap_action → navigate to matching pop-up hash
    │
    └── [pop-up definitions — single section, no title; invisible until triggered]
        ├── #thermostat  Climate card + 4 mode buttons (Home/Sleep/Away/Clear Hold)
        ├── #vacuum      Commands + map + status + mop settings + consumables
        ├── #reminders   Trash + all 8 tasks with green/red state
        ├── #water-leaks 4 leak sensor tiles
        ├── #doors       4 door/cover tiles (front, office sliding, interior garage, garage door)
        └── #laundry     Washer + dryer status, cycle info, ack button, stats grid
```

**Design decisions:**

- **Bubble Card primary; native HA cards for display and layout.** Bubble Card provides the climate card, vacuum button, pop-up overlays, separators, and the chip strip (`sub-buttons` card). All dynamic icon color is handled via the Bubble Card `styles` CSS-in-JS block. Native HA cards (`tile`, `grid`, `markdown`, `conditional`) are used for read-only data display. Mushroom Cards are not used anywhere in this dashboard except `mushroom-template-badge` for view-level header badges, which is an HA constraint — the `badges` array only accepts badge-type objects.

- **Header badges for status and alerts; chip strip for feature toggles.** Status and alert chips (Alarm, Water Leak, Doors, Garage, Weather, AQI, Guest, Avery) live in the view-level `badges` array as individual `mushroom-template-badge` entries — always visible regardless of scroll position. The chip strip below handles only the three feature toggles (Thermostat, Vacuum, Reminders). This matches the design of `mobile-app` and avoids multiple chip rows.

- **All feature detail surfaces are pop-ups.** Chip taps navigate directly to their pop-up hash (`#thermostat`, `#vacuum`, `#reminders`, `#doors`). There are no inline panels — the Home view contains only the chip strip and the pop-up definitions. Browser back, ESC, tap-outside, and swipe-down all dismiss pop-ups.

- **Pop-ups over subviews for all detail views.** Thermostat, vacuum, reminders, water leaks, and doors are all Bubble Card `pop-up` cards (hash-triggered modal overlays) rather than `subview: true` views. This simplifies the Home view to two sections: the chip strip and the pop-up block.

---

## Prerequisites

- Home Assistant 2025.9 or later
- HACS frontend resources installed and active:
  - `bubble-card` (Bubble Card) — primary card framework
  - `bubble-card-tools` (Bubble Card Tools) — required backend for Bubble Card
  - `lovelace-mushroom` (Mushroom Cards) — required for `mushroom-template-badge` (view-level badges only)
  - `lovelace-card-mod` (card-mod) — vacuum map crop transform
- Adaptive Lighting integration active (justifies no-slider rule)

---

## Build Steps

### Step 1 — Install HACS resources

In the HA UI: **Settings → HACS → Frontend**. Verify `bubble-card`, `bubble-card-tools`, `lovelace-mushroom` (badges only), and `lovelace-card-mod` are installed.

### Step 2 — Create the dashboard

In the HA UI: **Settings → Dashboards → Add Dashboard**. Set:

| Field | Value |
|---|---|
| Title | `Mobile` |
| Icon | `mdi:cellphone` |
| URL | `mobile-home` |
| Show in sidebar | On |
| Admin only | Off |

> **HA constraint:** New storage-mode dashboard URL paths must contain a hyphen. Single-word paths (e.g., `mobile`) are rejected with a validation error. The standard's aspirational slug is `mobile`; the actual deployed slug is `mobile-home`.

Select **Storage mode**. Add a single view titled **Home**, type **Sections**, `max_columns: 1`.

### Step 3 — Configure view header badges

Set the view-level `badges` array with 12 individual `custom:mushroom-template-badge` entries. Badges use `color` (not `icon_color`) for the badge color field. Use `visibility` on each badge for conditional display — the `type: conditional` chip wrapper used inside chip strips does not work here.

Badge order and behavior:

| Badge | Condition | Color | Notes |
|---|---|---|---|
| Alarm | Always visible | Template: red/orange/green by state | `mdi:shield-home/lock/alert` |
| Water leak | `water_leak_detected` ≠ off | red | Count when 2+; tap → `#water-leaks` |
| Freezer door | `kitchen_freezer_door_contact` ≠ off | red | Always alert; no contextual gate |
| Door open (red) | Any door open AND (sleeping OR away) | red | Count when 2+ |
| Door open (orange) | Any door open AND home AND awake | orange | Count when 2+ |
| Garage open (red) | Garage open AND (sleeping OR away) | red | Tap closes with confirmation |
| Garage open (orange) | Garage open AND home AND awake | orange | Tap closes with confirmation |
| Garage closed (green) | Garage closed | green | Hold opens garage |
| Weather | Always visible | — | Dynamic icon + temp; tap → `more-info` |
| AQI | Always visible | Template: red/accent/green by value | Value content; tap → `more-info` |
| Guest mode | Always visible | green/grey by state | Hold → toggle; tap → none |
| Avery sleeping | Morning 06:30–09:00 when `avery_sleeping` on; evening 20:30–22:30 when `avery_home_today` on AND `everyone_sleeping` off | green | Hold → toggle; tap → none |

Set the view header config: `layout: center`, `badges_position: bottom`, `badges_wrap: scroll`.

### Step 4 — Build the toggle chip strip

Add one section with no title. Place a single Bubble Card `sub-buttons` card (`card_type: sub-buttons`). Chips are organized into two rows via the `bottom` sub-button group array. Conditional chip visibility is handled via native Lovelace `visibility` conditions on each sub-button — not CSS `display` toggling. Icon color and dynamic text (temperature, count, %) are handled in the card's `styles` CSS-in-JS block: icon colors use `ha-icon { color: ... }` scoped to `.bubble-sub-button-N`, and text is injected via `card.querySelector(...).innerText`. The Avery sleeping chip uses `binary_sensor.avery_sleep_reminder` (a template binary sensor) as its visibility entity, which encapsulates the morning and evening time-window logic server-side.

Six chips across two rows. Row 1 (status/alert strip): Alarm, Water Leak, Freezer Door, Doors, Garage, Weather, AQI, Guest Mode, Avery Sleeping, Updates. Row 2 (feature chips):

| Chip | Icon | Icon color | Tap | Hold |
|---|---|---|---|---|
| Thermostat | `mdi:home-thermometer` | Template: blue/orange/grey by hvac_action | Navigate `#thermostat` | None |
| Vacuum | Template (5 states, see below) | Template (5 states) | Navigate `#vacuum` | Toggle `input_boolean.vacuum_routine_pause` |
| Reminders upcoming | `mdi:calendar-clock` | amber (upcoming > 0, nothing overdue) | Navigate `#reminders` | Navigate `#reminders` |
| Reminders overdue | `mdi:calendar-alert` | red (any overdue) | Navigate `#reminders` | Navigate `#reminders` |
| Washer | `mdi:washing-machine` | Orange (running) / green (alerting) / muted (acknowledged) / hidden (idle) | Navigate `#laundry` | Call `script.utility_room_acknowledge_laundry` (no-op when running) |
| Dryer | `mdi:tumble-dryer` | Same pattern as washer | Navigate `#laundry` | Same pattern as washer |

Reminders chips are mutually exclusive: the amber upcoming chip shows only when `sensor.upcoming_reminders_count > 0` AND `number.overdue_reminders_count < 1`; the red overdue chip shows only when `number.overdue_reminders_count > 0`; both hide when all tasks are current (nothing due within 3 days). Washer and dryer chips are conditionally hidden (CSS `display: none`) when both `input_select` is `idle` and `current_status` is in `[power_off, initial]`. When running, the chip shows the current progress % as content alongside the icon.

**Vacuum chip states** — color tracks operational status; icon tracks error/maintenance state independently.

| Condition | Color | Icon |
|---|---|---|
| `vacuum_routine_pause` on | Orange | `mdi:robot-vacuum-off` |
| Cleaning / returning / paused | Orange | `mdi:robot-vacuum-alert` if error or maintenance, else `mdi:robot-vacuum` |
| Operational error (`vacuum_error` ≠ none or `dock_error` ≠ ok) | Red | `mdi:robot-vacuum-alert` |
| Not run today | Grey | `mdi:robot-vacuum-alert` if maintenance required, else `mdi:robot-vacuum` |
| Ran today, maintenance required | Green | `mdi:robot-vacuum-alert` |
| Ran today, all clear | Green | `mdi:robot-vacuum` |

Color signals whether the vacuum did its job today; icon signals whether anything needs attention. Red is reserved for actual hardware errors (`sensor.roborock_q8_max_vacuum_error`, `sensor.roborock_q8_max_dock_error`) — maintenance required never changes the color, only the icon.

**Doors chip (Row 1, position 4):** `mdi:door-open`, warning/error color based on sleeping/away state (same as Row 1 badge logic), conditional on `binary_sensor.exterior_door_open` = on. Shows a count badge when 2+ doors are open. Tap navigates to `#doors`.

**Updates chip (Row 1, position 10):** `mdi:update`, accent color, conditional on `binary_sensor.updates_available` = on. Shows a count badge when ≥ 2 updates are pending (same pattern as water leak / doors). Tap navigates to `/config/updates`. The visibility entity `binary_sensor.updates_available` is a template binary sensor helper that evaluates `on` when any `update.*` entity state is `on`.

> **Thermostat chip content:** displays current indoor temperature (`state_attr('climate.living_room_thermostat', 'current_temperature') | int`). The chip has no `entity` field — `more-info` action not applicable here.

> **Icon-only chips:** omit `content` entirely. Do not set `content: ""` — an empty string allocates a text slot in the chip's flex layout and shifts the icon off-center. For entity chips, use `content_info: none`.

### Step 5 — Build the thermostat pop-up

Bubble Card `pop-up` with `hash: "#thermostat"`. Add a section with no title at the bottom of the Home view for all pop-up definitions.

- **Bubble Card climate card:** `card_type: climate`, `entity: climate.living_room_thermostat`. This is the primary thermostat control surface.
- **Mode button row:** A `grid` card with `columns: 4`. Each cell is a Bubble Card button (icon-only, `button_type: name`) with a `tap_action` calling `select.select_option` on `select.living_room_thermostat_current_mode`. Icon color is set via the `styles` block on each card.

| Mode | Icon | Active color | Entity |
|---|---|---|---|
| Home | `mdi:home` | green | `select.living_room_thermostat_current_mode` = home |
| Sleep | `mdi:sleep` | blue | = sleep |
| Away | `mdi:home-export-outline` | orange | = away |
| Clear Hold | `mdi:calendar-remove` | red (always) | `button.living_room_thermostat_clear_hold` |

### Step 6 — Build the vacuum detail pop-up

Add all pop-up cards to the same no-title section at the bottom of the Home view. Bubble Card `pop-up` with `hash: "#vacuum"` and `popup_mode: adaptive-dialog`.

```yaml
type: custom:bubble-card
card_type: pop-up
hash: "#vacuum"
name: Vacuum
icon: mdi:robot-vacuum
popup_mode: adaptive-dialog
with_bottom_offset: true
show_header: false
cards:
  # Vacuum commands button (Bubble Card button, sub-buttons)
  # Vacuum map image (conditional picture-entity)
  # Bubble Card separators as section headings
  # Status grid (native tile cards, 2 columns)
  # Mop settings (conditional on mop attached)
  # Maintenance (Bubble Card buttons, 4 items)
```

> **Pop-up mode:** all Bubble Card pop-ups on this dashboard use `popup_mode: adaptive-dialog` ("Fit content" on mobile). Set this on every pop-up card — it is not the default.

**Map card** — `picture-entity` on `image.roborock_q8_max_apartment`, shown when vacuum is not docked OR `input_select.vacuum_ran_today` = Yes. Apply `card_mod` to crop black padding from the Roborock map image — see `standards/dashboards.md` → card-mod Use Cases for the exact CSS.

**Status** (`mdi:gauge`) — Native `tile` cards in a `grid` with `columns: 2`: vacuum state, battery, cleaning area (m²), duration (min). Add a `conditional` tile for `sensor.roborock_q8_max_current_room` shown only when `binary_sensor.roborock_q8_max_cleaning` = on.

**Mop Settings** (`mdi:water`) — A `conditional` card wrapping both a Bubble Card separator and a 2-column grid of tiles (`select.roborock_q8_max_mop_intensity`, `select.roborock_q8_max_mop_mode`, `binary_sensor.roborock_q8_max_water_shortage`), gated on `binary_sensor.roborock_q8_max_mop_attached` = on.

**Maintenance** (`mdi:wrench`) — 4 Bubble Card buttons in a 2-column grid. Each shows hours remaining; icon color is set via the `styles` block (red when the maintenance binary sensor is on, green otherwise). Tap calls `script.vacuum_reset_consumable` (with a confirmation dialog), which presses the reset button then force-refreshes all consumable sensors so the UI reflects the cleared state within ~2 seconds.

| Consumable | Sensor | Reset button | Maintenance flag |
|---|---|---|---|
| Filter | `sensor.roborock_q8_max_filter_time_left` | `button.roborock_q8_max_reset_air_filter_consumable` | `binary_sensor.roborock_replace_filter` |
| Main brush | `sensor.roborock_q8_max_main_brush_time_left` | `button.roborock_q8_max_reset_main_brush_consumable` | `binary_sensor.roborock_replace_main_brush` |
| Side brush | `sensor.roborock_q8_max_side_brush_time_left` | `button.roborock_q8_max_reset_side_brush_consumable` | `binary_sensor.roborock_replace_side_brush` |
| Sensor | `sensor.roborock_q8_max_sensor_time_left` | `button.roborock_q8_max_reset_sensor_consumable` | `binary_sensor.roborock_clean_sensor` |

### Step 8 — Build the laundry pop-up

Add a Bubble Card `pop-up` with `hash: "#laundry"`, `popup_mode: adaptive-dialog`, `with_bottom_offset: true`. See `guides/laundry_automation.md` → Step 7b for the full per-appliance layout. The pop-up contains Washer and Dryer sections built entirely from Bubble Card and native HA cards — no Mushroom cards.

The `#laundry` pop-up is triggered by tapping either the washer or dryer chip in the chip strip. It is not triggered from a room tile; there is no room tile for the utility room.

### Step 9 — Build the reminders and water leaks pop-ups

Add two more Bubble Card `pop-up` cards to the same pop-up section at the bottom of the Home view.

**`#reminders` pop-up** — Organized into two sections: **Overdue** and **Next 3 Days** (due within 3 calendar days). Tasks due more than 3 days out are intentionally not shown — the popup surfaces only what needs attention. Each section begins with a Bubble Card separator (red and amber respectively). Both sections hide when empty, so the popup is blank when all tasks are current.

Each of the 8 reminders appears once per section — 16 total card instances, each gated by a `visibility` condition. The Lovelace JS frontend cannot evaluate `as_timestamp(now())` or date arithmetic in `condition: template` visibility conditions, so all date bucketing uses `condition: numeric_state` on backend template sensors (`sensor.<key>_days_until_due`) instead:

| Section | Visibility condition | Icon color |
|---|---|---|
| Overdue | `condition: state`, `binary_sensor.<key>_overdue` = on | Red |
| Next 3 Days | `condition: numeric_state`, `sensor.<key>_days_until_due`, `above: 0, below: 4` | Amber |

The `_days_until_due` sensors return **integer calendar days** (`(as_date(states('sensor.<key>_due')) - today()).days`), so `below: 4` means exactly 1, 2, or 3 — no fractional bleed. The Overdue separator gates on `number.overdue_reminders_count` > 0. The Next 3 Days separator gates on `sensor.upcoming_reminders_count` > 0 (an aggregate template sensor that counts reminders with integer `days_until_due` between 1 and 3).

All reminder cards use `entity: sensor.<key>_due` for the state display (the formatted due date string), `card_layout: normal` for compact height, `button_type: state`. Tap = none; hold on the card body = `script.reminder_mark_complete` — set via `button_action.hold_action`, not the top-level `hold_action` (which binds to the icon area, not the card body).

A final **empty state card** appears as the last card in the pop-up, visible only when both counts are 0 (nothing overdue, nothing in the next 3 days). It shows a green `mdi:calendar-check` icon with the label "All caught up." Tapping it navigates to `/mobile-home`, closing the pop-up — useful when the last overdue item is marked complete while the pop-up is open and both sections disappear, leaving an otherwise blank overlay.

**`#water-leaks` pop-up** — Heading + 2-column grid of 4 native `tile` cards:

| Name | Entity |
|---|---|
| Kitchen | `binary_sensor.kitchen_leak_water_leak` |
| Bathroom | `binary_sensor.bathroom_leak_water_leak` |
| Master Bath | `binary_sensor.master_bathroom_leak_water_leak` |
| Utility | `binary_sensor.utility_room_leak_water_leak` |

Triggered by tapping the water leak chip (`tap_action: navigate #water-leaks`).

**`#doors` pop-up** — 2-column grid of 4 native `tile` cards:

| Name | Entity |
|---|---|
| Front Door | `binary_sensor.entrance_front_door_contact` |
| Office Sliding | `binary_sensor.office_sliding_door_contact` |
| Interior Garage | `binary_sensor.garage_interior_door_contact` |
| Garage Door | `cover.garage_door` |

Triggered by tapping the doors chip (`tap_action: navigate #doors`). The garage door tile uses the `cover` entity (not a binary sensor) since the exterior door is a motorized cover — the tile card handles open/closed/opening/closing states natively.

### Step 10 — Cutover

Once the new dashboard is verified:

1. Pin the iPhone Companion App to `mobile-home` via **Settings → Companion App → Dashboard**.
2. Delete the old `mobile-app` dashboard via `ha_config_delete_dashboard(url_path="mobile-app")` (requires explicit confirmation).
3. Delete the now-unused helper `input_boolean.mobile_show_primary_lights` (Primary Lights section not built in this migration).

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Mobile dashboard | `mobile-home` | Lovelace dashboard |
| Home alarm | `alarm_control_panel.home_alarm` | Entity |
| Living room thermostat | `climate.living_room_thermostat` | Entity |
| Thermostat comfort mode | `select.living_room_thermostat_current_mode` | Entity |
| Thermostat clear hold | `button.living_room_thermostat_clear_hold` | Entity |
| Apartment weather | `weather.apartment` | Entity |
| Outdoor AQI | `sensor.toledo_ohio_usa_air_quality_index` | Entity |
| Roborock Q8 Max | `vacuum.roborock_q8_max` | Entity |
| Apartment map image | `image.roborock_q8_max_apartment` | Entity |
| Vacuum cleaning (binary) | `binary_sensor.roborock_q8_max_cleaning` | Entity |
| Vacuum error | `sensor.roborock_q8_max_vacuum_error` | Entity |
| Dock error | `sensor.roborock_q8_max_dock_error` | Entity |
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
| Vacuum Reset Consumable | `script.vacuum_reset_consumable` | Script |
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
| Trash pickup pending | `input_boolean.trash_pickup_pending` | Helper |
| Trash pickup label | `input_text.trash_pickup_pending_label` | Helper |
| Trash next pickup date | `input_text.trash_next_pickup_date` | Helper |
| Vacuum ran today | `input_select.vacuum_ran_today` | Helper |
| Vacuum routine pause | `input_boolean.vacuum_routine_pause` | Helper |
| Overdue reminders count | `number.overdue_reminders_count` | Helper |
| Upcoming reminders count | `sensor.upcoming_reminders_count` | Helper (template sensor) |
| Razor blade days until due | `sensor.razor_blade_changed_days_until_due` | Helper (template sensor) |
| Accord days until due | `sensor.accord_washed_days_until_due` | Helper (template sensor) |
| Water filter days until due | `sensor.water_filter_changed_days_until_due` | Helper (template sensor) |
| Coffee grinder days until due | `sensor.coffee_grinder_cleaned_days_until_due` | Helper (template sensor) |
| Dishwasher days until due | `sensor.dishwasher_cleaned_days_until_due` | Helper (template sensor) |
| Disposal days until due | `sensor.disposal_cleaned_days_until_due` | Helper (template sensor) |
| Washer days until due | `sensor.washer_cleaned_days_until_due` | Helper (template sensor) |
| Toothbrushes days until due | `sensor.toothbrushes_changed_days_until_due` | Helper (template sensor) |
| Everyone sleeping | `input_boolean.everyone_sleeping` | Helper |
| Avery sleeping | `input_boolean.avery_sleeping` | Helper |
| Avery sleep reminder (chip visibility) | `binary_sensor.avery_sleep_reminder` | Helper (template binary sensor) |
| Updates available (chip visibility) | `binary_sensor.updates_available` | Helper (template binary sensor) |
| Guest mode | `input_boolean.guest_mode` | Helper |
| Remind mark complete | `script.reminder_mark_complete` | Script |
| Washer status | `input_select.utility_room_washer_status` | Helper (input_select) |
| Dryer status | `input_select.utility_room_dryer_status` | Helper (input_select) |
| Washer progress | `sensor.utility_room_washer_progress` | Helper (template sensor) |
| Washer minutes remaining | `sensor.utility_room_washer_minutes_remaining` | Helper (template sensor) |
| Dryer progress | `sensor.utility_room_dryer_progress` | Helper (template sensor) |
| Dryer minutes remaining | `sensor.utility_room_dryer_minutes_remaining` | Helper (template sensor) |
| Washer cycle started | `input_datetime.utility_room_washer_cycle_started` | Helper (input_datetime) |
| Washer cycle ended | `input_datetime.utility_room_washer_cycle_ended` | Helper (input_datetime) |
| Dryer cycle started | `input_datetime.utility_room_dryer_cycle_started` | Helper (input_datetime) |
| Dryer cycle ended | `input_datetime.utility_room_dryer_cycle_ended` | Helper (input_datetime) |
| Washer cycles at last cleaning | `input_number.utility_room_washer_cycles_at_last_cleaning` | Helper (input_number) |
| Washer energy this month | `sensor.washer_energy_this_month` | Entity (lg_thinq) |
| Washer energy last month | `sensor.washer_energy_last_month` | Entity (lg_thinq) |
| Washer cycles | `sensor.washer_cycles` | Entity (lg_thinq) |
| Washer last error | `event.washer_error` | Entity (lg_thinq) |
| Dryer last error | `event.dryer_error` | Entity (lg_thinq) |
| Acknowledge laundry | `script.utility_room_acknowledge_laundry` | Script |
| Office bourbon lamp fireplace toggle | `script.office_bourbon_lamp_fireplace_toggle` | Script |
| Office accent scene selector | `input_select.office_accent_scene` | Helper (input_select) |

---

## Related Documents

- `standards/dashboards.md` — Governs all dashboard builds; defines card vocabulary, pop-up pattern, chip strip rules, and HACS policy
- `standards/naming.md` — Entity naming standard
- `guides/reminders.md` — Reminder system architecture; defines `script.reminder_mark_complete` and why a direct service call is insufficient
- `guides/laundry_automation.md` — Laundry automation guide; defines the status helpers, template sensors, and automations that drive the Laundry section
