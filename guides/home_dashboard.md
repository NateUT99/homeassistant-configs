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
│   │                         ── Greeting (markdown: "Good <part of day>, <name>!" + briefing)
│   │                         ── Favorites (heading + 2-up grid of apple_tile buttons)
│   │                         ── Now Playing (YAMP; only while an Apple TV or HomePod plays)
│   └── Section 2          ── Pop-ups: #rooms (room tiles by floor, 2-up) + 6 rooms
│                             + #security #climate #weather #vacuum #laundry #ai
│
└── Chores view ── Navbar Card ── chore-calendar-card
         │
         └── shared Jinja: /config/custom_templates/dashboard.jinja
               room_summary(area, temp, fan)   tile + pop-up header text
               alert_level()                   red if asleep/away, else orange
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
- **Media uses Yet Another Media Player, not the Bubble media card.** YAMP's
  `volume_entity` sends an Apple TV's volume to the Sonos it plays through, and
  `hidden_controls` drops buttons that do nothing for TV. Apple TVs also get `remote_entity`,
  which adds a button that opens a remote pad over the player. One Now Playing card on Home covers
  all seven players (chips switch between them) in compact mode (`always_collapsed`). It shows
  while an Apple TV is playing or paused, or a HomePod is playing — a paused HomePod lingers
  for hours, so it does not keep the card up. The room-pop-up player shows while playing or paused.
- **Areas fold into pop-ups instead of getting tiles** when they have nothing controlled
  from the dashboard more than occasionally (`standards/dashboards.md` §8.1).

---

## Prerequisites

- Home Assistant 2026.9 or later
- HACS frontend: Bubble Card ≥ 3.4, Navbar Card, Kiosk Mode, Battery State Card, Expander Card; theme: Frosted Glass
- HACS integrations: Bubble Card Tools and UIX, each added under **Settings → Devices &
  Services** (installing from HACS alone isn't enough)
- AI insights (`guides/ai_insights.md`) for the greeting line, AI chip, and `#ai`
- Chore Calendar integration (provides `todo.household_chores`, the chore sensors, and
  `chore-calendar-card`) — see `guides/reminders.md`
- Adaptive Lighting (owns brightness; the dashboard exposes no sliders)

---

## Steps

### 1. Deploy the shared templates and modules

```bash
ssh ha 'mkdir -p /config/custom_templates'
scp ha/custom_templates/dashboard.jinja ha:/config/custom_templates/dashboard.jinja
```

Then call `homeassistant.reload_custom_templates` and confirm in **Developer Tools →
Template**:

```jinja
{% from 'dashboard.jinja' import room_summary %}{{ room_summary('office', 'sensor.office_climate_temperature', 'fan.office_ceiling_fan') }}
```

Deploy the Bubble modules (Bubble Card Tools reads every YAML file in this folder):

```bash
scp ha/bubble_modules/*.yaml ha:/config/bubble_card/modules/
```

### 2. Create the dashboard

Create a storage-mode dashboard with `url_path: home-main`, title **Home**, icon
`mdi:home`, shown in the sidebar, and load `ha/dashboards/home-main.yaml` as its config
(raw configuration editor, or `ha_config_set_dashboard`). Views stay visible; Kiosk Mode
removes the tabs along with the header.

To edit in the UI, open `/home-main/home?disable_km`.

### 3. Chip strip

One Bubble `sub-buttons` card: a single row that scrolls sideways (`rows: 0.9`, chips
`custom_height: 40`, overflow styles in the card's `styles`). Chips are for what needs
attention; things you control are Favorites, and running appliances are Happening now.
Order is alerts first, then things due, then status. Chip icon colours are Jinja in the
card's `styles`, keyed by each chip's `css_class` (`standards/dashboards.md` §7, §10).

| Chip | Shows | Colour | Tap | Hold |
|---|---|---|---|---|
| Leak | Any `water_leak_sensor`-labelled sensor on | Red | `#security` | — |
| Internet | WAN down or modem power cycle active | Red | — | — |
| Generator | `sensor.outside_home_generator_status` = `Running` | Orange | — | — |
| Fridge | Refrigerator plug off or power sensor unavailable | Red | — | — |
| Openings | Any exterior opening except the front door (owned by Doors) open; "N open" | `alert_level()` colour | `#security` | — |
| HVAC paused | `input_select.household_hvac_mode_before_pause` ≠ `none` | Orange | `#climate` | — |
| Doors | Front door unlocked or open, or garage not closed; "Unlocked" / "Door open" / "Garage open" / "Door & garage" | `alert_level()` colour | `#security` | `script.household_secure_doors` (confirm) |
| Recycling | Trash chore due/overdue | Amber, red overdue | Chores view | Mark "Take Out Trash" done |
| AQI | AQI > 50 (not Good); index value | Yellow ≤ 100, orange ≤ 150, red | `#weather` | — |
| Updates | Any `update.*` on; count | Primary | `/config/updates` | — |
| Fireplace | Fireplace not `off`; setpoint | Orange | `#climate` | — |
| Weather | Always; outside temp | Theme | `#weather` | — |
| AI | Always; "All good" / "Check" | Orange when the house summary flagged attention | `#ai` | — |
| Nate | Always; "Nate home" / "Nate away" / "Nate asleep" (home while `input_boolean.everyone_sleeping` is on) | Green when home | more-info | — |
| Avery | Always; "Avery here" / "Avery away" / "Avery asleep" — schedule (`binary_sensor.avery_home_today`) plus her sleep switch; she has no person entity | Green when asleep | — | Toggle `input_boolean.avery_sleeping` |

The vacuum has no chip: its state, errors, and "routine paused" show on the Roborock favorite,
due maintenance becomes chores (`guides/vacuum_cleaning_routine.md`), and the routine-pause
toggle lives in `#vacuum`. Chores other than trash are not a chip: the navbar's Chores tab carries a red badge — a dot
for one due or overdue chore, the count for two or more.

The Recycling chip appears in practice only on Trash & Recycling weeks: a trash-only week
auto-completes at its first announcement (see `guides/reminders.md`). Its hold calls
`todo.update_item` on `todo.household_chores`, the same completion path as the chore card.

**Room sections** follow on Home, one HA section each so they sit side by side on desktop, in
this order: Living Room, Master Bedroom, Avery's Room, Office, Family Room, Kitchen, Outside.
Each is a heading — the room name with "›" and its temperature as a badge; tapping it opens
the room's pop-up (`#security` for Outside) — over 2-up `apple_tile` tiles of the room's
everyday controls (tap toggles, hold opens more-info; the Fireplace tile opens its controls
on tap instead of toggling):

| Room | Tiles |
|---|---|
| Living Room | TV Accent, Fireplace |
| Master Bedroom | Ceiling Light, Fan, Nightstand |
| Avery's Room | Ceiling Light, Fan, Desk Lamp |
| Office | Ceiling Light, Fan, Key Light, Bourbon Lamp |
| Family Room | Ambient Lamp, Alice Glow, Peanuts Glow |
| Kitchen | Sink Light |
| Outside | Porch, Front Door, Garage |

The navbar's Rooms tab (`#rooms`) stays as the at-a-glance view of every room.

**Happening now** sits below Favorites: a `Happening now` heading and a 2-column grid,
both shown only while at least one card is visible. Each card is a Bubble `button` whose
`styles` call `progress_fill(pct, rgb)` from `dashboard.jinja`, filling the card left to
right with progress.

| Card | Visible while | Line under the name | Fill | Tap |
|---|---|---|---|---|
| Washer / Dryer | Running, done (`alerting`), or faulted | "23 min left" / "Done · unload" / "Fault" | Teal, cycle progress (full when done) | `#laundry` |
| Dishwasher | `binary_sensor.kitchen_dishwasher_running` on | "Running · N min" | Even tint (no progress reported) | `#laundry` |
| Vacuum | Cleaning, returning, paused, or error | "Room · 60%" / "Returning to dock" / "Paused" / the error | Lavender, cleaning progress | `#vacuum` |

**Greeting** sits below the chip strip: a text-only markdown card, "Good morning/afternoon/
evening, <first name>!" (05:00–11:59 / 12:00–16:59 / otherwise, the logged-in user's first
name) over the latest briefing headline in italics. Markdown sizes itself to its content, so
the line never overlaps the chips. A UIX style trims the heading's bottom margin.

### 4. Room tiles

| Tile | Hold toggles | Tile buttons | Summary |
|---|---|---|---|
| Living Room | — | Apple TV, Fireplace (more-info) | lights · temp |
| Kitchen | — | — | lights · temp |
| Family Room | — | Apple TV (more-info) | lights · temp |
| Office | Ceiling light | Ceiling light, Fan | lights · fan · temp |
| Master Bedroom | Ceiling light | Ceiling light, Fan | lights · fan · temp |
| Avery's Room | Ceiling light | Ceiling light, Fan | lights · fan · temp |

The tiles live in the `#rooms` pop-up (no header), opened from the navbar's Rooms tab: a
Bubble separator per floor (Main Floor, Basement), each followed by a 2-column grid of Bubble
buttons, `rows: 3`, with the tile buttons in the `bottom` sub-button row at 44 px. Light and
fan buttons toggle on tap and open more-info on hold. Each tile's `styles` calls
`room_glow(area)` from `dashboard.jinja`: a warm amber tint and halo while any of the area's
visible lights are on.

### Favorites

A `Favorites` heading and a 2-column grid under the greeting: the Apple Home favourites plus
Guest Mode. Every tile is a Bubble `button` with the `apple_tile` module: translucent dark
when idle; tinted and glowing while active (thermostat heating amber or cooling blue, lock
unlocked, garage open, vacuum cleaning — all amber). Text stays white in both states.

| Tile | Line under the name | Tap | Hold |
|---|---|---|---|
| Thermostat | `73° · 69°–76°` (current · setpoints) | `#climate` | more-info |
| Front Door | Locked / Unlocked | Unlock (when locked) or lock, with confirmation | more-info |
| Garage Door | Open / Closed | Open (when closed) or close, with confirmation | more-info |
| Roborock | State, or the error / dock error / "Stuck"; icon turns `robot-vacuum-off` in orange while the routine is paused | `#vacuum` | Pause (when running) or resume the vacuum routine, with confirmation |
| Guest Mode | On / Off | Turn on (when off) or off, with confirmation | more-info |

Front Door, Garage Door, Guest Mode, and Roborock each exist twice with opposite `visibility` conditions, so the
confirmation can name the exact action ("Unlock the front door?") — an action's
confirmation text cannot be templated. Each copy calls the explicit service
(`lock.unlock`, `cover.open_cover`, `input_boolean.turn_on`, …) rather than `toggle`.

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
| `#living-room` | Apple TV player at the top (YAMP, only while playing or paused; volume → Soundbar; Apps, Speech and Night chips), 4 lights, thermostat + fireplace (Bubble climate) |
| `#kitchen` | Sink light, dishwasher and refrigerator tiles, HomePod |
| `#family-room` | Ambient lamp, 2 pinball underglows, 3 game power switches, Apple TV |
| `#office` | 7 lights, fan speed (tile `fan-speed` feature), HomePod |
| `#master-bedroom` | Ceiling light, nightstand lamp, fan speed, Apple TV, HomePod, bathroom speaker |
| `#averys-room` | Ceiling light, desk and dresser lamps, fan speed, HomePod |
| `#security` | Doorbell camera (square crop, first); lock, garage door, garage interior door, doors & windows; Water (the 4 leak sensors); outside lights |
| `#climate` | Thermostat and fireplace (Bubble climate) |
| `#weather` | 12-hour temperature and rain-chance forecast, daily forecast, outside conditions, AQI and pollutants |
| `#vacuum` | Commands, routine pause, Mop now (confirm), map (only when out or ran today), status, mop settings (when the pad is on), 4 consumables |
| `#ai` | No header bar (`show_header: false`). Three heading cards (Briefing, House Summary, This Week), each with an age badge (`state_content: last_updated`); Briefing and House Summary add a refresh button badge that starts their script. Each heading is followed by a markdown body; see below |
| `#laundry` | Washer and dryer status, remaining, progress, start/finish; "stop reminders" acknowledge (only while `alerting`); dishwasher; washer stats; utility room light |

**`#ai` bodies** are markdown cards, not Bubble cards, because their length varies and Bubble
cards have a fixed height. Each shows *Working on it…* while its script entity is `on`.

- **Briefing:** the headline in bold, then the tip.
- **House Summary:** a *Needs attention* list (orange alert icons) when `attention_items` is
  non-empty, then an *All good* list (green checks).
- **This Week:** the digest headline in italics, then a borderless table. Electricity (kWh,
  cost, change vs. the week before) and Climate (heating/cooling hours) come from the Sunday
  digest. The other rows render live, so they are current between digests:
  - Vacuuming: "Done" with a check when both the day and night counters
    (`sensor.household_vacuum_day_runs_this_week`, `_night_`) are above zero; otherwise
    "Not yet".
  - Mopping: "Done" with a check when both this-week mop flags are on; otherwise "Not yet".
  - Chores: the overdue count and the count due in the next 7 days.

The UIX style on these cards removes table borders and keeps the first column on one line.

`#laundry` is reachable only while a washer, dryer, or dishwasher chip is showing; it is about
the current cycle.

**Vacuum consumables** (filter clean, filter replace, main brush, side brush, sensors) use the `consumable_status` Bubble module (icon red at ≤ 0 h left, amber
under 10 h, green otherwise). Tap opens more-info; hold calls
`script.household_vacuum_reset_consumable` immediately — no confirmation, since a reset is
only done right after the maintenance itself (see `guides/vacuum_cleaning_routine.md`).

**Laundry acknowledge** sets `input_select.utility_room_<appliance>_status` to `acknowledged`,
which ends *Utility Room: Laundry Announcement*'s repeat loop (it continues only while a status
is `alerting` or `fault`). Retrieval or the next cycle returns the status to `idle`.

### 6. Views

Navbar order: Home · Rooms · Climate · Chores · More. Rooms opens `/home-main/home#rooms`; More opens a menu with Energy and Maintenance.

| View | Path | Contents |
|---|---|---|
| Home | `home` | Steps 3–5 |
| Climate | `climate` | Collapsible sections (Thermostat and Rooms open by default, Humidity collapsed): thermostat and fireplace (Bubble climate), HVAC-paused line (only while paused), HVAC runtime and cycles today; per-room temperature tiles with a 24 h trend; one 24 h humidity history graph |
| Energy | `energy` | Built-in energy cards: date selection, compare, Sankey, per-device detail graph; cost table; generator status, warning, maintenance, last ran, run time, battery, connection, status message |
| Chores | `chores` | `chore-calendar-card` on `calendar.household_chores` |
| Maintenance | `maintenance` | Collapsible sections (Expander Card; Batteries open by default, the rest collapsed): vacuum consumables (same cards as `#vacuum`); pending updates; network (WAN, Firewalla, speed test, latency, loss, alarms, modem resets, modem maintenance, Litra agent); batteries |

**Energy** reads the Energy settings: grid import from `sensor.household_energy_monitor_total_energy_delivered`
with `sensor.household_energy_monitor_power_demand` as the grid power sensor, and the six
tracked devices. Small smart plugs are deliberately not tracked devices — they read as
"untracked" in the Sankey. The live power cards (`power-total`, `power-sankey`) are not used
here; they fail outside the built-in Energy dashboard, which keeps its own Now tab.

**Navbar badges and visibility:** More, and Energy inside its menu, show a red badge while
`binary_sensor.outside_home_generator_warning` or `_maintenance_alert` is on — generator
problems surface there rather than as a Home chip. The Maintenance item is hidden for
non-admin users (`hidden: [[[ return !user.is_admin ]]]`).

**Batteries** use Battery State Card (HACS): every `device_class: battery` sensor except the
Companion App devices (`sensor.nates_*`), lowest first. Batteries under 30 % are listed
individually (orange under 30 %, red under 20 %); the rest collapse into one "N others OK"
row showing the lowest level. New devices appear automatically.

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
| Household: Vacuum Reset Consumable | `script.household_vacuum_reset_consumable` | Script |
| Household: Vacuum Mop Now | `script.household_vacuum_mop_now` | Script |
| Household: Secure Doors | `script.household_secure_doors` | Script (lock front door if closed, close garage) |
| Household AI Briefing / House Summary / Weekly Digest | `sensor.household_ai_briefing`, `sensor.household_ai_house_summary`, `sensor.household_ai_weekly_digest` | Template sensors (`guides/ai_insights.md`) |
| Living Room Vacuum Filter Clean Time Left | `sensor.living_room_vacuum_filter_clean_time_left` | Template helper |
| HVAC Mode Before Pause | `input_select.household_hvac_mode_before_pause` | Helper |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/custom_templates/dashboard.jinja` | `/config/custom_templates/dashboard.jinja` | Shared macros (repo authoritative) |
| `ha/dashboards/home-main.yaml` | HA storage (`home-main`) | Dashboard mirror (HA authoritative) |
| `ha/bubble_modules/consumable_status.yaml` | `/config/bubble_card/modules/consumable_status.yaml` | Consumable icon colour module (repo authoritative) |
| `ha/bubble_modules/apple_tile.yaml` | `/config/bubble_card/modules/apple_tile.yaml` | Apple-style Favorites tile module (repo authoritative) |

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
