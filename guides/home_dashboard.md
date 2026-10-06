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
│   ├── Section 1 (span 4) ── Navbar Card ── Chip strip + quick-action chip row (Bubble sub-buttons, 2 rows, rows: 1.2)
│   │                                          Row 1  status & alerts
│   │                                          Row 2  features
│   │                         ── Greeting (markdown: "Good <part of day>, <name>!" + briefing)
│   │                         ── Happening now (heading + 2-up grid, shown while an appliance runs)
│   ├── Sections 2–8       ── Room sections × 7 (Expander: heading + media card + tiles)
│   └── Section 9          ── Pop-ups: #rooms (room tiles by floor, 2-up) + 6 rooms
│                             + #security #climate #weather #vacuum #laundry #ai
│
└── Chores view ── Navbar Card ── chore-calendar-card
         │
         └── shared Jinja: /config/custom_templates/dashboard.jinja
               room_summary(area, temp, fan)   tile + pop-up header text
               alert_level()                   red if asleep/away, else amber
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
- **Media lives in the room it plays in.** Each room section on Home carries a Bubble
  `media-player` card for its Apple TV or HomePod, shown only while that player is in use —
  no house-wide player card. Bubble's own volume button controls the Apple TV, not the
  speaker it plays through, so Apple TV cards hide it and add an always-visible slider
  sub-button on the real speaker (Sonos, or the bedroom TV). Every media card — room
  sections, `#media`, `#living-room` — uses the Bubble Media Player Enhanced module
  (artwork background and colours; `idle_artwork: none` since the cards hide when idle), so
  there is one media style and no separate media card dependency. Bubble's own icon is hidden
  (`show_icon: false`) because the module already draws the cover. All media cards use the large
  layout (`rows: 3`, full scrubbable progress bar above the controls,
  `main_buttons_position: bottom`); Apple TV cards also use `artwork_fit: original` so wide
  TV artwork is not cropped square.
- **Apple TV cards show while playing or paused; HomePod cards while playing plus 10
  minutes.** A paused Apple TV is a show you'll come back to. A HomePod usually drops from
  `paused` to `idle` on its own 8 minutes after playing, but an app that parks a track on it
  without playing (`idle` → `paused`, seen with AirMusic in Avery's room) leaves it paused
  indefinitely. So HomePod cards — and the Media chip's count — follow a template sensor
  that is on while playing and for 10 minutes after (`ha/packages/media_activity.yaml`).
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
`custom_height: 40`, overflow styles in the card's `styles`). It follows Apple Home's top
row: always-on **category chips** with a one-line status, plus a few standalone chips. Conditional
chips (faults, a leak, recycling due) come first, so an alert is visible without scrolling. Status
text and icon colours come from macros in `dashboard.jinja` (`weather_status`,
`security_status`, `lights_on_count`, …), so the strip's own config stays small. Things you
switch by hand are quick actions; running appliances are Happening now.

| Chip | Shows | Status line | Icon colour | Tap | Hold |
|---|---|---|---|---|---|
| Internet | WAN down or modem power cycle | "Down" / "Modem reset" | Red | — | — |
| Generator | Running | "Generator" | Amber | — | — |
| Fridge | Plug off or power sensor unavailable | "Fridge" | Red | — | — |
| **Water** | A leak | "Leak: <sensor>" | Red | `#security` | — |
| Recycling | Trash chore due/overdue | "Recycling" | Amber, red overdue | Chores view | Mark "Take Out Trash & Recycling" done |
| **Weather** | Always | Outside temp and condition ("58° Sunny"), plus "AQI n" when above 50 | AQI on the EPA scale: yellow > 50, orange > 100, red > 150; neutral otherwise | `#weather` | — |
| **Lights** | Always | "N on" / "All off" (visible lights in the areas listed in `house_light_areas()`) | Amber when any are on | `#lights` | — |
| **Security** | Always | Apple Home-style, higher risk first: "N Open" (front door, patio door, or garage physically open), else "N Unlocked" (front door lock), else "Secure". Interior doors and windows are not counted | Green secure, else `alert_level()` (amber / red); icon open door, open lock, or check-shield | `#security` | `script.household_secure_doors` |
| **Media** | Always | "N on" / "Media off" — players with a room media card showing: Apple TVs playing or paused, HomePods whose activity sensor is on | Purple when any are on | `#media` | — |

**`#lights`** lists every light by room (Living Room through Utility Room) as `apple_tile`
tiles — tap toggles, hold opens more-info. **`#media`** lists every Apple TV and HomePod card
by room, the same cards the room sections show. Both lists are static: a new light or player
is added to the pop-up by hand.

**Quick actions** are a second chip row directly under the status row: a separate
`sub-buttons` card with the same scrolling layout, for the AI check-in and the people and house modes you switch by hand. The chip group is
`width: max-content` with `min-width: 100%` and `justify-content: center`, so the row centres
when it fits and scrolls from the first chip when it doesn't (`safe center` clips the first chip on iOS — see LESSONS.md).
Tap opens more-info, hold toggles (`standards/dashboards.md` §12):

| Chip | Icon and colour | Hold toggles |
|---|---|---|
| AI (icon only) | `mdi:creation`, amber while the house summary from the last 12 hours flagged something, grey otherwise | — (tap `#ai`) |
| Climate (icon only) | `mdi:fire` amber while heating, `mdi:snowflake` blue while cooling, `mdi:hvac-off` amber while an open door or window has paused it, otherwise grey `mdi:hvac` (idle or switched off) | — (tap `#climate`, hold opens more-info) |
| Nate | Sleep (indigo) while `input_boolean.everyone_sleeping` is on; otherwise home (green) or away (grey) from `person.nate` | `input_boolean.everyone_sleeping` |
| Avery | Sleep (indigo) while `input_boolean.avery_sleeping` is on; otherwise home (green) on her scheduled days (`binary_sensor.avery_home_today`), away (grey) on others | `input_boolean.avery_sleeping` |
| Vacuum (icon only) | `mdi:robot-vacuum-alert` (red, stuck or a vacuum or dock error), `mdi:robot-vacuum-off` (amber, routine paused), or `mdi:robot-vacuum` (purple cleaning or returning, grey otherwise); tap opens `#vacuum` | `input_boolean.vacuum_routine_pause` |
| Guest (icon only) | Amber while guest mode is on | `input_boolean.guest_mode` |

Sleep wins over location, so a stale sleep flag is visible at a glance. Quick actions are icon-only so the row keeps a fixed width; every state that matters has its own icon, so none relies on colour alone, and tap opens the detail.

Chores other than trash are not a chip: the navbar's Chores tab carries a red badge — a dot
for one due or overdue chore, the count for two or more.

The Recycling chip appears in practice only on Trash & Recycling weeks: a trash-only week
auto-completes at its first announcement (see `guides/reminders.md`). Its hold calls
`todo.update_item` on `todo.household_chores`, the same completion path as the chore card.

**Room sections** follow on Home, one HA section each so they sit side by side on desktop, in
this order: Living Room, Master Bedroom, Avery's Room, Office, Family Room, Kitchen, Outside.
Each is an Expander Card (`title-card-clickable: false`, so the heading stays its own card
and the chevron is a separate button; inner padding `4px 10px 10px`; open state remembered
per device under `storage-id: home-main-room-<slug>`). The title card is a heading — the room
name (HA adds the arrow for a tappable heading) and its temperature as a badge; tapping it
opens the room's pop-up (`#security` for Outside). Inside: the room's media card(s) while in
use, then 2-up `apple_tile` tiles of the room's everyday controls (tap toggles, hold opens
more-info; the Fireplace tile opens its controls on tap instead of toggling). Living Room,
Master Bedroom, Avery's Room, and Office start expanded; Family Room, Kitchen, and Outside
start collapsed.

| Room | Media card (while in use) | Tiles |
|---|---|---|
| Living Room | Apple TV; volume slider → Soundbar | TV Accent, Fireplace |
| Master Bedroom | Apple TV (slider → TV); HomePod | Ceiling Light, Fan, Nightstand |
| Avery's Room | HomePod | Ceiling Light, Fan, Desk Lamp |
| Office | HomePod | Ceiling Light, Fan, Key Light, Bourbon Lamp |
| Family Room | Apple TV; volume slider → Theater | Ambient Lamp, Alice Glow, Peanuts Glow |
| Kitchen | HomePod | Sink Light |
| Outside | — | Porch, Front Door, Garage |


The navbar's Rooms tab (`#rooms`) stays as the at-a-glance view of every room.

**HomePod activity package** — `ha/packages/media_activity.yaml`, deployed to
`/config/packages/media_activity.yaml`, reload with `template.reload`:

```yaml
# "Recently active" flags for the HomePods, used to show a room's media card on the
# home-main dashboard and to count it in the Media chip: on while the HomePod is playing,
# and held on for 10 minutes after it stops (delay_off). A HomePod usually drops from
# paused to idle by itself after 8 minutes, but not when an app parks a track on it
# without playing (idle -> paused directly), which can sit paused indefinitely -- so the
# card can't rely on "paused". Apple TVs don't need this: their cards show while playing
# or paused. See guides/home_dashboard.md.
#
# Deployed to /config/packages/media_activity.yaml; reload with template.reload.

template:
  - binary_sensor:
      - name: Kitchen HomePod Active
        unique_id: kitchen_homepod_active
        state: "{{ is_state('media_player.kitchen_homepod', 'playing') }}"
        delay_off: "00:10:00"
      - name: Office HomePod Active
        unique_id: office_homepod_active
        state: "{{ is_state('media_player.office_homepod', 'playing') }}"
        delay_off: "00:10:00"
      - name: Master Bedroom HomePod Active
        unique_id: master_bedroom_homepod_active
        state: "{{ is_state('media_player.master_bedroom_homepod', 'playing') }}"
        delay_off: "00:10:00"
      - name: Averys Room HomePod Active
        unique_id: averys_room_homepod_active
        state: "{{ is_state('media_player.averys_room_homepod', 'playing') }}"
        delay_off: "00:10:00"
```

**Happening now** sits below the greeting: a `Happening now` heading and a 2-column grid,
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
| `#living-room` | Apple TV player at the top (only while playing or paused; Soundbar volume slider; Apps, Speech and Night sub-buttons), 4 lights, thermostat + fireplace (Bubble climate) |
| `#kitchen` | Sink light, dishwasher and refrigerator tiles, HomePod |
| `#family-room` | Ambient lamp, 2 pinball underglows, 3 game power switches, Apple TV |
| `#office` | 7 lights, fan speed (tile `fan-speed` feature), HomePod |
| `#master-bedroom` | Ceiling light, nightstand lamp, fan speed, Apple TV, HomePod, bathroom speaker |
| `#averys-room` | Ceiling light, desk and dresser lamps, fan speed, HomePod |
| `#security` | Doorbell camera (square crop, first); lock, garage door, garage interior door, doors & windows; Water (the 4 leak sensors); outside lights |
| `#climate` | Thermostat and fireplace (Bubble climate) |
| `#weather` | Bubble Weather card (`weather_forecast` module: animated condition background, 5-day forecast), outside conditions, AQI and pollutants |
| `#vacuum` | Commands, routine pause, Mop now (confirm), map (only when out or ran today), status, mop settings (when the pad is on), 4 consumables |
| `#ai` | No header bar (`show_header: false`). Three heading cards (Briefing, House Summary, This Week), each with an age badge (`state_content: last_updated`); Briefing and House Summary add a refresh button badge that starts their script. Each heading is followed by a markdown body; see below |
| `#laundry` | Washer and dryer status, remaining, progress, start/finish; "stop reminders" acknowledge (only while `alerting`); dishwasher; washer stats; utility room light |

**`#ai` bodies** are markdown cards, not Bubble cards, because their length varies and Bubble
cards have a fixed height. Each shows *Working on it…* while its script entity is `on`.

- **Briefing:** the headline in bold, then the tip.
- **House Summary:** a *Needs attention* list (amber alert icons) when `attention_items` is
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

**Navbar badges and visibility:** More shows a red badge while any `update.*` entity is on
(Maintenance inside its menu carries the same badge) or while
`binary_sensor.outside_home_generator_warning` or `_maintenance_alert` is on (Energy inside the
menu carries that one) — generator
problems surface there rather than as a Home chip. The Maintenance item is hidden for
non-admin users (`hidden: [[[ return !user.is_admin ]]]`).

**Batteries** use Battery State Card (HACS): every `device_class: battery` sensor except the
Companion App devices (`sensor.nates_*`), lowest first. Batteries under 30 % are listed
individually (amber under 30 %, red under 20 %); the rest collapse into one "N others OK"
row showing the lowest level. New devices appear automatically.

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Home dashboard | `home-main` | Lovelace dashboard |
| Household Exterior Openings | `binary_sensor.household_exterior_openings` | Group helper (Show As: Opening) |
| Household Chores | `todo.household_chores` | To-do list (Chore Calendar) |
| Take Out Trash & Recycling | `sensor.household_chores_take_out_trash` | Chore sensor |
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
| `ha/bubble_modules/apple_tile.yaml` | `/config/bubble_card/modules/apple_tile.yaml` | Apple-style tile module for `#lights` and room tiles (repo authoritative) |
| `ha/packages/media_activity.yaml` | `/config/packages/media_activity.yaml` | HomePod "recently active" sensors for room media cards and the Media chip (repo authoritative) |

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
