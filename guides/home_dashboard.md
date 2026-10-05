# Home Dashboard

*Last updated: October 2026*

---

## Overview

`home-main` is the single dashboard for phone, tablet, and desktop. Its Home view answers
"is anything wrong, and what's on?" at a glance: a two-row chip strip of status, alerts, and
running features, and a tile per room showing a live summary. Every chip and tile taps
through to a Bubble Card pop-up (or a secondary view) with the detail and controls.
Navigation is Navbar Card (bottom bar on a phone, left rail on desktop); Kiosk Mode hides the
HA header. Conventions are governed by `standards/dashboards.md`; this guide documents the
build.

---

## Architecture

```
home-main  (storage-mode dashboard, kiosk_mode.hide_header, navbar-templates.main)
│
├── Home view (sections, max_columns 4, theme Frosted Glass)
│   ├── Section 1 (span 4) ── Navbar Card ── Chip strip (Bubble sub-buttons, 2 rows, rows: 1.2)
│   │                                          Row 1  status & alerts
│   │                                          Row 2  features
│   ├── Section 2 (span 4) ── Room tiles × 6 (Bubble button; full width on phone, 4-up desktop)
│   └── Section 3          ── Pop-ups: 6 rooms + #security + #climate
│
└── Chores view ── Navbar Card ── chore-calendar-card
         │
         └── shared Jinja: /config/custom_templates/dashboard.jinja
               room_summary(area, temp, fan)   tile + pop-up header text
               alert_level()                   red if asleep/away, else orange
               alert_tint(level)               30% wash for alerting chips
```

**Design decisions:**

- **One responsive dashboard.** Sections reflow by width, and Bubble pop-ups render as a
  sheet on a phone and a centred dialog on desktop, so one config serves every form factor.
- **Shared logic lives in `dashboard.jinja`.** Bubble renders card templates on the HA
  server, so tiles and chip styles import the same macros. Changing how a summary or alert
  level is computed is a one-file change.
- **Chips read existing helpers where one exists.** Leak visibility uses the
  `water_leak_sensor` label (the same target as the leak automation); HVAC paused reads
  `input_select.household_hvac_mode_before_pause`; nothing is re-derived in the dashboard.
- **Generator chip shows only while running.** Running means a utility outage — worth seeing
  at a glance. Exercising, warnings, and maintenance belong on the Energy view.
- **Areas fold into pop-ups instead of getting tiles** when they have nothing controlled
  from the dashboard more than occasionally (`standards/dashboards.md` §8.1).

---

## Prerequisites

- Home Assistant 2026.9 or later
- HACS frontend: Bubble Card ≥ 3.4, Navbar Card, Kiosk Mode; theme: Frosted Glass
- HACS integration: Bubble Card Tools, added under **Settings → Devices & Services**
- Chore Calendar integration (provides `todo.household_chores`, the chore sensors, and
  `chore-calendar-card`) — see `guides/reminders.md`
- Adaptive Lighting (owns brightness; the dashboard exposes no sliders)

---

## Steps

### 1. Deploy the shared templates

```bash
ssh ha 'mkdir -p /config/custom_templates'
scp ha/custom_templates/dashboard.jinja ha:/config/custom_templates/dashboard.jinja
```

Then call `homeassistant.reload_custom_templates`. Confirm in **Developer Tools →
Template**:

```jinja
{% from 'dashboard.jinja' import room_summary %}{{ room_summary('office', 'sensor.office_climate_temperature', 'fan.office_ceiling_fan') }}
```

### 2. Create the dashboard

Create a storage-mode dashboard with `url_path: home-main`, title **Home**, icon
`mdi:home`, shown in the sidebar, and load `ha/dashboards/home-main.yaml` as its config
(raw configuration editor, or `ha_config_set_dashboard`). Views stay visible; Kiosk Mode
removes the tabs along with the header.

To edit in the UI, open `/home-main/home?disable_km`.

### 3. Chip strip

One Bubble `sub-buttons` card. Chip colours and alert tints are Jinja in the card's
`styles`, keyed by each chip's `css_class` (`standards/dashboards.md` §7, §10).

**Row 1 — status & alerts**

| Chip | Shows | Colour | Tap | Hold |
|---|---|---|---|---|
| Weather | Always; outside temp | Theme | `#weather` | — |
| AQI | Always; index value | Green ≤ 50, yellow ≤ 100, orange ≤ 150, red | `#weather` | — |
| Lock | Always; icon only | Green locked; `alert_level()` + tint when unlocked | `#security` | Lock (confirm) |
| Garage | Always; icon only | Green closed; `alert_level()` + tint when open | `#security` | Close (confirm) |
| Openings | `binary_sensor.household_exterior_openings` on; "N open" | `alert_level()` + tint | `#security` | — |
| Leak | Any `water_leak_sensor`-labelled sensor on | Red + tint | `#water-leaks` | — |
| HVAC paused | `input_select.household_hvac_mode_before_pause` ≠ `none` | Orange | `#climate` | — |
| Internet | WAN down or modem power cycle active | Red + tint | — | — |
| Generator | `sensor.outside_home_generator_status` = `Running` | Orange | — | — |
| Fridge | Refrigerator plug off or power sensor unavailable | Red + tint | — | — |
| Updates | Any `update.*` on; count | Primary | `/config/updates` | — |
| Guest | Always; icon only | Green when on | — | Toggle |
| Avery | She's home today **and** (asleep 06:30–09:00 **or** house awake 20:30–22:30) | Green when asleep | — | Toggle `input_boolean.avery_sleeping` |

**Row 2 — features**

| Chip | Shows | Colour | Tap | Hold |
|---|---|---|---|---|
| Thermostat | Always; indoor temp | Orange heating, blue cooling | `#climate` | — |
| Fireplace | Fireplace not `off`; setpoint | Orange | `#climate` | — |
| Vacuum | Always; icon only | Red error/stuck, orange running or paused, green ran today | `#vacuum` | Toggle routine pause (confirm) |
| Chores | Any chore (except trash) due/overdue; "N due" | Amber due, red overdue | Chores view | — |
| Recycling | Trash chore due/overdue | Amber, red overdue | Chores view | Mark "Take Out Trash" done |
| Washer / Dryer | Running, done, or faulted; progress % or "Done" | Blue running, green done, red fault | `#laundry` | — |
| Dishwasher | Running | Blue | `#laundry` | — |

The Recycling chip appears in practice only on Trash & Recycling weeks: a trash-only week
auto-completes at its first announcement (see `guides/reminders.md`). Its hold calls
`todo.update_item` on `todo.household_chores`, the same completion path as the chore card.

### 4. Room tiles

| Tile | Hold toggles | Tile buttons | Summary |
|---|---|---|---|
| Living Room | — | Apple TV, Fireplace (more-info) | lights · temp |
| Kitchen | — | — | lights · temp |
| Family Room | — | Apple TV (more-info) | lights · temp |
| Office | Ceiling light | Fan (toggle) | lights · fan · temp |
| Master Bedroom | Ceiling light | Fan (toggle) | lights · fan · temp |
| Avery's Room | Ceiling light | Fan (toggle) | lights · fan · temp |

Areas without a tile: Entrance, Garage, and Outside fold into `#security`; Utility Room
into `#laundry`; the Bathroom lamp is automated and its leak sensor feeds the Leak chip;
Pantry has nothing to show.

> **Coordinated change:** the Living Room ceiling fan and light are being added. When they
> are in HA, the Living Room tile becomes `button_type: switch` with the light as `entity`
> and hold, and gains a fan tile button.

### 5. Pop-ups

All pop-ups use `popup_mode: adaptive-dialog` and `popup_style: bubble`; the room pop-ups'
header shows the same `room_summary` as the tile.

| Hash | Contents |
|---|---|
| `#living-room` | 4 lights, thermostat + fireplace (Bubble climate), Apple TV |
| `#kitchen` | Sink light, dishwasher and refrigerator tiles, HomePod |
| `#family-room` | Ambient lamp, 2 pinball underglows, 3 game power switches, Apple TV |
| `#office` | 7 lights, fan speed (tile `fan-speed` feature), HomePod |
| `#master-bedroom` | Ceiling light, nightstand lamp, fan speed, Apple TV, HomePod, bathroom speaker |
| `#averys-room` | Ceiling light, desk and dresser lamps, fan speed, HomePod |
| `#security` | Lock, garage door, garage interior door, doors & windows, outside lights, doorbell camera (square crop, last) |
| `#climate` | Thermostat and fireplace (Bubble climate) |

Not yet built: `#weather`, `#vacuum`, `#laundry`, `#water-leaks` — their chips render but
open nothing until they exist.

### 6. Views

| View | Path | Contents |
|---|---|---|
| Home | `home` | Steps 3–5 |
| Chores | `chores` | `chore-calendar-card` on `calendar.household_chores` |

Planned: Climate, Energy, Maintenance (admin-only route).

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Home dashboard | `home-main` | Lovelace dashboard |
| Household Exterior Openings | `binary_sensor.household_exterior_openings` | Group helper (Show As: Opening) |
| Household Chores | `todo.household_chores` | To-do list (Chore Calendar) |
| Take Out Trash | `sensor.household_chores_take_out_trash` | Chore sensor |
| Avery Home Today | `binary_sensor.avery_home_today` | Template helper |
| Avery Sleeping | `input_boolean.avery_sleeping` | Helper |
| Guest Mode | `input_boolean.guest_mode` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |
| HVAC Mode Before Pause | `input_select.household_hvac_mode_before_pause` | Helper |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/custom_templates/dashboard.jinja` | `/config/custom_templates/dashboard.jinja` | Shared macros (repo authoritative) |
| `ha/dashboards/home-main.yaml` | HA storage (`home-main`) | Dashboard mirror (HA authoritative) |

---

## Related Documents

- `standards/dashboards.md` — conventions this build follows
- `guides/reminders.md` — chore lifecycle, trash week types, completion path
- `guides/presence_tracking.md` — `zone.home`, sleeping helpers used by `alert_level()`
- `LESSONS.md` → Dashboards & Lovelace — Bubble/Kiosk/Navbar gotchas found building this

---

## Troubleshooting

- **A tile or chip shows raw `{{ ... }}` or nothing:** `dashboard.jinja` is missing or
  stale on the host — redeploy it and run `homeassistant.reload_custom_templates`.
- **A room's light count looks wrong:** an indicator LED or group member is counting as a
  room light. Hide it in the entity registry; `room_summary` excludes hidden entities.
- **Chip strip clipped at the top or floating with a gap:** a row is wrapping. See
  `LESSONS.md` → *Bubble `sub-buttons` cards anchor their rows to the bottom*.
