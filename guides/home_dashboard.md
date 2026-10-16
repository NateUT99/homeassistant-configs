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
├── Home view (sections, max_columns 4, theme Home Flat)
│   ├── Section 1 (span 4) ── Navbar Card ── Chip strip + quick-action chip row (Bubble sub-buttons, 2 rows, rows: 1.2)
│   │                                          Row 1  status & alerts
│   │                                          Row 2  features
│   │                         ── Greeting (markdown: "Good <part of day>, <name>!" + briefing)
│   │                         ── Happening now (heading + 2-up grid, shown while an appliance runs)
│   ├── Sections 2–8       ── Room sections × 7 (Expander: heading + media card + tiles)
│   └── Section 9          ── Pop-ups: #rooms (room tiles by floor, 2-up) + 6 rooms + #living-room-remote #master-bedroom-remote
│                             + #security #hvac #weather #vacuum #vacuum-care #laundry
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
- **Media lives in the room it plays in.** Each room section on Home carries a media card for
  its Apple TV or HomePod, shown only while that player is in use, and the room's pop-up repeats
  it; there is no house-wide player card. Both kinds are specified under *Room media cards* in
  Step 3.
- **Apple TVs on Yet Another Media Player, speakers on Bubble.** YAMP's `volume_entity` sends an
  Apple TV's volume to the speaker that actually plays its sound (Soundbar, bedroom TV, Theater);
  a Bubble media card can only change the Apple TV's own volume, which does nothing audible. CSS
  overrides make YAMP a 16:9 card the artwork fills, with the controls in one row on its bottom
  fade. HomePods and the bathroom speaker keep Bubble Media Player Enhanced, which is built for
  audio and whose own volume button drives the speaker itself.
- **Artwork follows what is playing.** A TV episode shows the Apple TV's own artwork, a 16:9
  still of that episode; a movie shows TMDB's backdrop, because the Apple TV sends only a poster.
  Art of any other shape shows whole on a blurred copy of itself rather than cropped. The rule is
  a JavaScript template rather than Jinja because YAMP caches a Jinja artwork
  override per title (`LESSONS.md` → *Yet Another Media Player caches a Jinja artwork override
  per title*).
- **The Living Room Apple TV has its own remote pop-up.** `#living-room-remote` is the one
  destination for that player: tapping its card on Home, in `#media`, or in `#living-room` opens
  it. It is a separate pop-up rather than a collapsible section in the room pop-up, because
  Expander Card can't be opened from a link and remembers its last state per device, so a
  link could land on a collapsed remote. The remote is Universal Remote Card (HACS), the only
  card besides YAMP that isn't Bubble: it sends the Apple TV `remote.send_command` keys natively, gives
  haptics, and has a swipe touchpad that Bubble has no equivalent for.
- **Media cards by place.** Home, the room pop-ups and `#media` use the room media cards. The
  remote pop-ups' Apple TV tabs lead with a Bubble button card showing the artwork, then the
  title (see `#living-room-remote`); `#media` adds each Apple TV's rating, details line and
  description under its card (Step 3).
- **Media cards follow an "active" template sensor per player**
  (`ha/packages/media_activity.yaml`), and so does the Media chip's count. Apple TVs are
  active while playing, or paused in the app that last played (a paused show is one you'll come
  back to; a paused session from another app is a leftover — `LESSONS.md` → *The AppleTV reports
  an old app's paused session after the current one ends*), plus 30 seconds,
  because moving around the Apple TV interface drops it to `idle` for under a second at a
  time, which would otherwise hide and re-show the card. HomePods are active while playing
  something with a track title, plus 10 minutes. The title requirement keeps a TTS
  announcement — `playing` for a few seconds with no title or artist — from showing the card
  for 10 minutes. The 10-minute hold exists because a HomePod usually drops from `paused` to
  `idle` on its own 8 minutes after playing, but an app that parks a track on it without playing (`idle` → `paused`, seen with
  AirMusic in Avery's room) leaves it paused indefinitely.
- **Areas fold into pop-ups instead of getting tiles** when they have nothing controlled
  from the dashboard more than occasionally (`standards/dashboards.md` §8.1).

---

## Prerequisites

- Home Assistant 2026.9 or later
- HACS frontend: Bubble Card ≥ 3.4, Navbar Card ≥ 1.7 (badge icons), Kiosk Mode, Battery State Card, Expander Card, apexcharts-card, Universal Remote Card (`Nerwyn/universal-remote-card`), Yet Another Media Player (`jianyu-li/yet-another-media-player`); custom-brand-icons (`phu:` icons); theme: Home Flat (repo, `ha/themes/home_flat.yaml`)
- HACS integrations: Bubble Card Tools and UIX, each added under **Settings → Devices &
  Services** (installing from HACS alone isn't enough)
- AI insights (`guides/ai_insights.md`) for the greeting line, the `#weather` tip, and the AI Insight cards
- Chore Calendar integration (provides `todo.household_chores`, the chore sensors, and
  `chore-calendar-card`) — see `guides/reminders.md`
- Adaptive Lighting (owns brightness; the dashboard exposes no sliders)
- A TMDB account (free) for the Now Playing cast, tagline, score and background art: its API Read Access Token goes in `/config/secrets.yaml` as `tmdb_token: "Bearer <token>"` (see Media info package below)

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

Deploy the theme, then call `frontend.reload_themes`:

```bash
scp ha/themes/home_flat.yaml ha:/config/themes/home_flat.yaml
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
| **Weather** | Always | Current temperature and today's high, Apple Weather style ("58° H:70°"; the high is `sensor.outside_forecast`), plus "AQI n" when above 50; the condition is the icon | AQI on the EPA scale: yellow > 50, orange > 100, red > 150; neutral otherwise | `#weather` | — |
| **Lights** | Always | "N on" / "All off" (visible lights in the areas listed in `house_light_areas()`) | Amber when any are on | `#lights` | — |
| **Security** | Always | Apple Home-style, higher risk first: "N Open" (front door, patio door, or garage physically open), else "N Unlocked" (front door lock), else "Secure". Interior doors and windows are not counted | Green secure, else `alert_level()` (amber / red); icon open door, open lock, or check-shield | `#security` | `script.household_secure_doors` |
| **Media** | Always | "N playing" / "Media off" — players with a room media card showing (their activity sensor is on) | Purple when any are playing | `#media` | — |

**`#lights`** lists every light by room (Living Room through Utility Room) as `apple_tile`
tiles — tap toggles, hold opens more-info. **`#media`** is the house-wide "Speakers & TVs"
list: one Yet Another Media Player card per active player, under its room heading. Apple TVs
get the Apple TV room media card (*Room media cards*, below), the same as on Home; Family Room's has no
tap action since it is already in `#media`. Under it, once `sensor.<room>_appletv_info` has
looked the title up, a Bubble row with the content rating as an outlined badge and year ·
genre · runtime, then the description truncated to 220 characters. HomePods get the same Bubble card as on Home. Each room label is a heading card in
the `title` style with the area's icon (`mdi:sofa`, `mdi:bed-king`, `mdi:teddy-bear`,
`mdi:desktop-classic`, `mdi:pac-man`, `mdi:stove`) on a tinted bar (`uix`: a 9 % text-colour
background, 12 px radius), so each room's group is easy to pick out. Spacing or a divider can't
do it: a heading card has a fixed height, so added padding pushes its label under the next card. The Master Bedroom HomePod's heading shows only when the
bedroom Apple TV isn't, so the room is labelled once. Each card and room heading sits in a
`conditional` card keyed on the player's activity sensor (the Media chip's rule), so idle
players are hidden; with none active the pop-up shows a single "Nothing playing" line. Both
lists are static: a new light or player is added to the pop-up by hand, along with its
activity sensor in the conditions.

**Quick actions** are a second chip row directly under the status row: a separate
`sub-buttons` card with the same scrolling layout, for the HVAC and vacuum and the people and house modes you switch by hand. The chip group is
`width: max-content` with `min-width: 100%` and `justify-content: center`, so the row centres
when it fits and scrolls from the first chip when it doesn't (`safe center` clips the first chip on iOS — see LESSONS.md).
Chips are grouped devices first, then people (HVAC, Vacuum, then Nate, Avery, Guest).
Tap opens more-info, hold toggles (`standards/dashboards.md` §12):

| Chip | Icon and colour | Hold toggles |
|---|---|---|
| HVAC (icon only) | `mdi:fire` amber while heating, `mdi:snowflake` blue while cooling, `mdi:hvac-off` amber while an open door or window has paused it, otherwise grey `mdi:hvac` (idle or switched off) | — (tap `#hvac`, hold opens more-info) |
| Vacuum (icon only) | `mdi:robot-vacuum-alert` (red, stuck or a vacuum or dock error), `mdi:robot-vacuum-off` (amber, routine paused), or `mdi:robot-vacuum` (amber paused mid-clean, purple cleaning or returning, green once today's daytime pass is done, grey otherwise); tap opens `#vacuum` | `input_boolean.vacuum_routine_pause`, `input_boolean.vacuum_ran_daytime` |
| Nate | Sleep (indigo) while `input_boolean.everyone_sleeping` is on; otherwise home (green) or away (grey) from `person.nate` | `input_boolean.everyone_sleeping` |
| Avery | Sleep (indigo) while `input_boolean.avery_sleeping` is on; otherwise home (green) on her scheduled days (`binary_sensor.avery_home_today`), away (grey) on others | `input_boolean.avery_sleeping` |
| Guest | Green while guest mode is on, matching the status lamps | `input_boolean.guest_mode` |

Sleep wins over location, so a stale sleep flag is visible at a glance. HVAC and Vacuum are icon-only and the people chips carry their name, so the row keeps a steady width; every state that matters has its own icon, so none relies on colour alone, and tap opens the detail.

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
use, then 2-up `apple_tile` tiles of the room's everyday controls: tapping the tile toggles
it (`button_action`), tapping its icon opens more-info (card `tap_action`), and hold opens
more-info. Living Room,
Master Bedroom, Avery's Room, and Office start expanded; Family Room, Kitchen, and Outside
start collapsed.

| Room | Media card (while in use) | Tiles |
|---|---|---|
| Living Room | Apple TV | Ceiling Light, Fan |
| Master Bedroom | Apple TV; HomePod | Ceiling Light, Fan, Nightstand |
| Avery's Room | HomePod | Ceiling Light, Fan, Desk Lamp |
| Office | HomePod | Ceiling Light, Fan, Key Light, Bourbon Lamp |
| Family Room | Apple TV | Ambient Lamp, Alice Glow, Peanuts Glow |
| Kitchen | HomePod | Sink Light |
| Outside | — | Porch, Front Door, Garage |

**Room media cards** — the same card for a player on Home, in its room pop-up and in `#media`.

*Apple TVs* get a Yet Another Media Player card:

| Player | `volume_entity` | Tap |
|---|---|---|
| Living Room Apple TV | `media_player.living_room_soundbar` | `#living-room-remote` |
| Master Bedroom Apple TV | `media_player.master_bedroom_tv` | `#master-bedroom-remote` |
| Family Room Apple TV | `media_player.family_room_theater` | `#media` (none inside `#media`) |

Each sets `volume_mode: stepper` (−/+ at `volume_step: 0.02`, mute on the speaker icon),
`match_theme: true`, `artwork_object_fit: cover` and `details_alignment: left`, hides every
control but play/pause (most video apps ignore previous/next), and opens the remote through a
hidden `navigate` action on `card_trigger: tap`. The artwork is a `media_artwork_overrides` entry
whose `image_url` is a JavaScript template (`[[[ ... ]]]`): when `sensor.<room>_appletv_info`
matches the playing `media_content_id` and the title is a movie, TMDB's backdrop; otherwise the
Apple TV's own `entity_picture` (for an episode, a 16:9 still of it); then the sensor's backdrop
or poster; then the app's fallback image (`/local/media_art/`). The Family Room pop-up adds an
Apps · Speech · Night row under its card, styled like the remote's sound row.

*HomePods and the bathroom speaker* get a Bubble `media-player` card with the Media Player
Enhanced module (`card_layout: default`, `idle_artwork: none`, `background_opacity: 0.85`,
Bubble's icon hidden since the module draws the cover): previous / play-pause / next, Bubble's
own volume button (it drives the HomePod itself) and a scrubbable progress bar
(`progress_bar: full`). On Home and in `#media` it is the two-row layout (`rows: 2`,
`artwork_fit: cover`) and doesn't respond to taps; in the room pop-ups it is the larger
`rows: 3` layout, and the bathroom speaker uses `progress_bar: compact`.

The Apple TV card's look comes from CSS in its `uix.style`. The selectors are YAMP internals, so
recheck them after a YAMP update:

| Override | Why it's needed |
|---|---|
| `.yamp-card-inner { container-type: inline-size }` and `.card-artwork-spacer { height: max(40px, calc(56.25cqw - 85px)) }` | YAMP has no aspect-ratio option. The empty band above the title is sized so the whole card is 16:9 at any width: 56.25 % of the card's width, less the 85 px of title and controls below it. A wide backdrop or episode still then fills the card uncropped. |
| `.card-lower-content-bg { min-height: 0; height: 100%; background-position: center }` | YAMP pins its artwork layer at 350 px inline; on a shorter card the image is scaled to 350 px and its bottom is cut off (`LESSONS.md` → *Yet Another Media Player pins its artwork layer at 350 px*). |
| `.card-lower-content-bg` drawn by two pseudo-elements that inherit its `background-image` (its own `background-size: 0 0`): `::before` at `cover`, blurred and darkened; `::after` at `contain` | Artwork that isn't 16:9 — a film's 2:3 poster when TMDB has no backdrop — shows whole and centred on a blurred copy of itself instead of being cropped. 16:9 art fills the card exactly, so it looks the same either way. |
| `.card-lower-content` as a two-column grid; the controls `div` in column 1, `.volume-row` in column 2 pushed right (`.volume-left { margin-left: auto }`, `.volume-center { width: auto }`) | Puts play/pause and the volume stepper on one row. YAMP stacks them, which costs about 60 px. |
| `.details` top padding 4 px; `.progress-bar-container` and `.details .artist` hidden | Keeps the rows below the artwork short so less of it is covered; an Apple TV's "artist" line is only the app name. |
| `:host { --accent-color: var(--primary-text-color) }`, `.volume-percentage-indicator` in the background colour, `.more-info-menu` hidden | Neutral white controls instead of YAMP's orange accent, and no menu button: the menu opens YAMP's own search and source sheet, which the remotes already cover. |


The navbar's Rooms tab (`#rooms`) stays as the at-a-glance view of every room.

**Media activity package** — `ha/packages/media_activity.yaml`, deployed to
`/config/packages/media_activity.yaml`, reload with `template.reload`. HA derives
`binary_sensor.*_apple_tv_active` from the "Apple TV" names; rename the three to
`*_appletv_active` after the first reload so they match the media player IDs the dashboard
uses. The three `sensor.*_appletv_last_played_app` sensors are named "AppleTV" so they need no
rename:

```yaml
# "Recently active" flags for the HomePods and Apple TVs, used to show a room's media card
# on the home-main dashboard and to count it in the Media chip.
#
# HomePods: on while playing something with a track title, held on for 10 minutes after it
# stops (delay_off). A TTS announcement plays with no title, so it never shows the card. A
# HomePod usually drops from paused to idle by itself after 8 minutes, but not when an app
# parks a track on it without playing (idle -> paused directly), which can sit paused
# indefinitely -- so the card can't rely on "paused".
#
# Apple TVs: on while playing or paused (a paused show is one you'll come back to), held on
# for 30 seconds. Moving around the Apple TV interface drops it to idle for under a second
# at a time, which would otherwise hide and re-show the card.
#
# A paused session counts only if it belongs to the app that last played. When an app's
# session ends (leaving the TV app, going to the Home screen) the Apple TV reports some older
# app's paused session instead -- typically a YouTube video paused hours ago -- for minutes,
# as if it were current. sensor.<room>_appletv_last_played_app records the app_id of the last
# session that reached `playing` (trigger-based, so it survives restarts), and a paused
# session from any other app turns the flag off at once, with no 30-second hold, so the
# leftover title and artwork never show. See guides/home_dashboard.md.
#
# Deployed to /config/packages/media_activity.yaml; reload with template.reload.

template:
  - binary_sensor:
      - name: Kitchen HomePod Active
        unique_id: kitchen_homepod_active
        state: >-
          {{ is_state('media_player.kitchen_homepod', 'playing')
             and state_attr('media_player.kitchen_homepod', 'media_title') not in [none, ''] }}
        delay_off: "00:10:00"
      - name: Office HomePod Active
        unique_id: office_homepod_active
        state: >-
          {{ is_state('media_player.office_homepod', 'playing')
             and state_attr('media_player.office_homepod', 'media_title') not in [none, ''] }}
        delay_off: "00:10:00"
      - name: Master Bedroom HomePod Active
        unique_id: master_bedroom_homepod_active
        state: >-
          {{ is_state('media_player.master_bedroom_homepod', 'playing')
             and state_attr('media_player.master_bedroom_homepod', 'media_title') not in [none, ''] }}
        delay_off: "00:10:00"
      - name: Averys Room HomePod Active
        unique_id: averys_room_homepod_active
        state: >-
          {{ is_state('media_player.averys_room_homepod', 'playing')
             and state_attr('media_player.averys_room_homepod', 'media_title') not in [none, ''] }}
        delay_off: "00:10:00"
      - name: Living Room Apple TV Active
        unique_id: living_room_appletv_active
        state: >-
          {{ is_state('media_player.living_room_appletv', 'playing')
             or (is_state('media_player.living_room_appletv', 'paused')
                 and state_attr('media_player.living_room_appletv', 'app_id') == states('sensor.living_room_appletv_last_played_app')) }}
        delay_off: >-
          {{ '00:00:00' if is_state('media_player.living_room_appletv', 'paused')
                and state_attr('media_player.living_room_appletv', 'app_id') != states('sensor.living_room_appletv_last_played_app') else '00:00:30' }}
      - name: Family Room Apple TV Active
        unique_id: family_room_appletv_active
        state: >-
          {{ is_state('media_player.family_room_appletv', 'playing')
             or (is_state('media_player.family_room_appletv', 'paused')
                 and state_attr('media_player.family_room_appletv', 'app_id') == states('sensor.family_room_appletv_last_played_app')) }}
        delay_off: >-
          {{ '00:00:00' if is_state('media_player.family_room_appletv', 'paused')
                and state_attr('media_player.family_room_appletv', 'app_id') != states('sensor.family_room_appletv_last_played_app') else '00:00:30' }}
      - name: Master Bedroom Apple TV Active
        unique_id: master_bedroom_appletv_active
        state: >-
          {{ is_state('media_player.master_bedroom_appletv', 'playing')
             or (is_state('media_player.master_bedroom_appletv', 'paused')
                 and state_attr('media_player.master_bedroom_appletv', 'app_id') == states('sensor.master_bedroom_appletv_last_played_app')) }}
        delay_off: >-
          {{ '00:00:00' if is_state('media_player.master_bedroom_appletv', 'paused')
                and state_attr('media_player.master_bedroom_appletv', 'app_id') != states('sensor.master_bedroom_appletv_last_played_app') else '00:00:30' }}

  - triggers:
      - trigger: state
        entity_id: media_player.living_room_appletv
        to: playing
      - trigger: state
        entity_id: media_player.living_room_appletv
        attribute: app_id
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    conditions:
      - condition: state
        entity_id: media_player.living_room_appletv
        state: playing
    sensor:
      - name: Living Room AppleTV Last Played App
        unique_id: living_room_appletv_last_played_app
        icon: mdi:application-outline
        state: "{{ state_attr('media_player.living_room_appletv', 'app_id') or this.state }}"

  - triggers:
      - trigger: state
        entity_id: media_player.family_room_appletv
        to: playing
      - trigger: state
        entity_id: media_player.family_room_appletv
        attribute: app_id
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    conditions:
      - condition: state
        entity_id: media_player.family_room_appletv
        state: playing
    sensor:
      - name: Family Room AppleTV Last Played App
        unique_id: family_room_appletv_last_played_app
        icon: mdi:application-outline
        state: "{{ state_attr('media_player.family_room_appletv', 'app_id') or this.state }}"

  - triggers:
      - trigger: state
        entity_id: media_player.master_bedroom_appletv
        to: playing
      - trigger: state
        entity_id: media_player.master_bedroom_appletv
        attribute: app_id
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    conditions:
      - condition: state
        entity_id: media_player.master_bedroom_appletv
        state: playing
    sensor:
      - name: Master Bedroom AppleTV Last Played App
        unique_id: master_bedroom_appletv_last_played_app
        icon: mdi:application-outline
        state: "{{ state_attr('media_player.master_bedroom_appletv', 'app_id') or this.state }}"
```

**Media info package** — `ha/packages/media_info.yaml`, deployed to
`/config/packages/media_info.yaml`, reload with `rest_command.reload` then `template.reload`
(the first deploy needed a restart because the instance had no `rest_command`). HA derives
`sensor.*_apple_tv_info`; rename to `*_appletv_info`. The sensor's `content_id` is stored as a
number, so cards compare it with the player's ID as strings. The TMDB token is read from
`secrets.yaml` and sent only as an `Authorization` header; it is a read-only token for TMDB's
public catalogue, and the trade-off is that every store title played is sent to Apple and TMDB,
and every TV-app title's name to TMDB:

```yaml
# Now-playing details for the Apple TVs, from Apple's public iTunes lookup service and TMDB.
#
# Content bought or rented from Apple reports its iTunes store ID as media_content_id (a plain
# number, e.g. 271991087 for The Terminator), which the lookup resolves exactly: year, content
# rating, genre, runtime, description and a poster, plus the director for a movie or the series
# for a TV episode (Apple's artistName is the director on a movie and the series on an
# episode).
#
# TMDB (The Movie Database) then adds the cast with headshots, tagline, audience score, wide
# background art and, for an episode, the series' 2:3 poster. TMDB doesn't know Apple's IDs, so
# it is matched by name: a movie by title and release year; an episode by series name (Apple's
# "(Original)"-style suffix removed), taking the newest series that started no later than the
# episode aired (so Magnum, P.I. 1982 finds the 1980 series, not the 2018 one), then the season
# and episode numbers from Apple's track name ("Season 2, Episode 20: ..."). An unmatched title
# just gets no TMDB fields.
#
# Titles streamed in the TV app (Apple TV+ and the like) report a non-numeric ID (e.g.
# A0006203008) and only a title, so they skip Apple's lookup and go straight to a TMDB search
# by that title (the series name when the player reports one). Only an exact, case-insensitive
# name match is used, or failing that a TMDB title of the form "<prefix>: <title>" -- specials
# are often listed under their franchise ("Snoopy Presents: A Summer Musical" when the Apple TV
# says "A Summer Musical"); anything looser could show the wrong show. These get TMDB's fields only:
# the US content rating from TMDB, the player's own duration as runtime, and the series (not
# the episode) for TV. Other apps (YouTube, Disney+) and live TV (no duration) get no details.
#
# Security: the TMDB API Read Access Token lives in /config/secrets.yaml as
# `tmdb_token: "Bearer <token>"` and is sent as a request header, never in a URL (so it never
# lands in a log line). It grants read access to TMDB's public catalogue only. Each new store
# title played is sent to Apple and TMDB; each new TV-app title's name is sent to TMDB.
#
# The lookups run only when the content ID changes (or HA starts / templates reload), not on a
# timer. The home-main remote pop-ups and #media show the details. See guides/home_dashboard.md.
#
# Top-level variables can't see `this`, so `changed` reads the sensor by entity ID (the
# renamed sensor.<room>_appletv_info). `lookup_version` marks which lookup rules produced the
# stored details; `changed` is also true when it differs, so raising it re-fetches whatever is
# playing once under the new rules. A TV-app title with no TMDB match stores its ID with empty
# details, so it is searched only once per version.
#
# Deployed to /config/packages/media_info.yaml; reload with rest_command.reload then
# template.reload.

rest_command:
  itunes_lookup:
    url: "https://itunes.apple.com/lookup?id={{ id }}&country=us"
    method: GET
    timeout: 10

  # `path` is everything after /3/, query string included.
  tmdb_get:
    url: "https://api.themoviedb.org/3/{{ path }}"
    method: GET
    headers:
      Authorization: !secret tmdb_token
      accept: application/json
    timeout: 10

template:
  - triggers:
      - trigger: state
        entity_id: media_player.living_room_appletv
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    variables:
      new_id: "{{ state_attr('media_player.living_room_appletv', 'media_content_id') | default('', true) | string }}"
      active: "{{ is_state('media_player.living_room_appletv', ['playing', 'paused']) }}"
      owned: "{{ new_id is match('^[0-9]+$') }}"
      tvapp: "{{ not owned and new_id != '' and is_state_attr('media_player.living_room_appletv', 'app_id', 'com.apple.TVWatchList') and (state_attr('media_player.living_room_appletv', 'media_duration') or 0) > 0 }}"
      title: "{{ state_attr('media_player.living_room_appletv', 'media_series_title') or state_attr('media_player.living_room_appletv', 'media_title') or '' }}"
      changed: "{{ new_id != (state_attr('sensor.living_room_appletv_info', 'content_id') | default('', true) | string) or (state_attr('sensor.living_room_appletv_info', 'lookup_version') | int(0)) != 2 }}"
    actions:
      - if:
          - condition: template
            value_template: "{{ active and owned and changed }}"
        then:
          - action: rest_command.itunes_lookup
            data:
              id: "{{ new_id }}"
            response_variable: itunes
            continue_on_error: true
          - if:
              - condition: template
                value_template: >
                  {% if itunes is defined and itunes.status == 200 %}{% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.kind | default('') in ['feature-movie', 'tv-episode'] }}{% else %}false{% endif %}
            then:
              - action: rest_command.tmdb_get
                data:
                  path: >
                    {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% if r.kind == 'feature-movie' %}search/movie?query={{ r.trackName | urlencode }}&primary_release_year={{ r.releaseDate[:4] }}{% else %}search/tv?query={{ r.artistName | regex_replace('\\s*\\([^)]*\\)$', '') | urlencode }}{% endif %}
                response_variable: tsearch
                continue_on_error: true
              - if:
                  - condition: template
                    value_template: "{{ tsearch is defined and tsearch.status == 200 and (tsearch.content.results | default([]) | count) > 0 }}"
                then:
                  - action: rest_command.tmdb_get
                    data:
                      path: >
                        {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% set res = tsearch.content.results %}
                        {% if r.kind == 'feature-movie' %}movie/{{ (res | first).id }}?append_to_response=credits
                        {%- else %}{% set aired = r.releaseDate[:10] %}{% set shows = res | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', aired) | sort(attribute='first_air_date', reverse=true) | list %}{% set show = (shows or res) | first %}{% set se = r.trackName | regex_findall('Season (\\d+), Episode (\\d+)') | first | default([]) %}
                        {%- if se %}tv/{{ show.id }}/season/{{ se[0] }}/episode/{{ se[1] }}?append_to_response=credits{% else %}tv/{{ show.id }}?append_to_response=credits{% endif %}{% endif %}
                    response_variable: tdetail
                    continue_on_error: true
      - if:
          - condition: template
            value_template: "{{ active and tvapp and changed and title != '' }}"
        then:
          - action: rest_command.tmdb_get
            data:
              path: "search/multi?query={{ title | urlencode }}"
            response_variable: msearch
            continue_on_error: true
          # Only an exact (case-insensitive) title match is trusted; anything else shows no details.
          - variables:
              hit: >
                {% set ns = namespace(m=[], p=[]) %}{% set t = title | lower %}{% if msearch is defined and msearch.status == 200 %}{% for x in msearch.content.results | default([]) if x.get('media_type') in ['movie', 'tv'] %}{% set n = (x.get('name') or x.get('title') or '') | lower %}{% if n == t %}{% set ns.m = ns.m + [x] %}{% elif n.endswith(': ' ~ t) %}{% set ns.p = ns.p + [x] %}{% endif %}{% endfor %}{% endif %}{{ (ns.m or ns.p) | first | default({}) }}
          - if:
              - condition: template
                value_template: "{{ hit.get('id') is not none }}"
            then:
              - action: rest_command.tmdb_get
                data:
                  path: "{{ hit.media_type }}/{{ hit.id }}?append_to_response=credits,{{ 'content_ratings' if hit.media_type == 'tv' else 'release_dates' }}"
                response_variable: tdetail
                continue_on_error: true
    sensor:
      - name: Living Room Apple TV Info
        unique_id: living_room_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.trackName | default('none') }}
          {% elif active and tvapp and tdetail is defined and tdetail.status == 200 %}
            {{ title }}
          {% elif active and (owned or tvapp) and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and (owned or tvapp)) else '' }}"
          lookup_version: "{{ 2 }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {% set t = tdetail.content if (tdetail is defined and tdetail.status == 200 and tdetail.content is mapping) else {} %}
              {% set people = ((t.get('credits') or {}).get('cast') or []) + (t.get('guest_stars') or []) %}
              {% set ns = namespace(cast=[]) %}
              {% for p in people[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% set art = t.get('backdrop_path') or t.get('still_path') %}
              {% set sres = tsearch.content.results if (tsearch is defined and tsearch.status == 200) else [] %}
              {% set shows = sres | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', (r.releaseDate | default(''))[:10]) | sort(attribute='first_air_date', reverse=true) | list %}
              {% set sp = ((shows or sres) | first | default({})).get('poster_path') if r.kind | default('') == 'tv-episode' else none %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': r.kind | default(''),
                'series': r.artistName | default('') if r.kind | default('') == 'tv-episode' else '',
                'director': r.artistName | default('') if r.kind | default('') == 'feature-movie' else '',
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb'),
                'show_poster': ('https://image.tmdb.org/t/p/w780' ~ sp) if sp else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ art) if art else ''
              } }}
            {% elif active and tvapp and tdetail is defined and tdetail.status == 200 and tdetail.content is mapping %}
              {% set t = tdetail.content %}{% set tv = 'first_air_date' in t %}
              {% set mins = ((state_attr('media_player.living_room_appletv', 'media_duration') or 0) / 60) | round(0) | int %}
              {% set ns = namespace(cast=[]) %}
              {% for p in ((t.get('credits') or {}).get('cast') or [])[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% if tv %}
                {% set rating = (t.get('content_ratings') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='rating') | first | default('') %}
              {% else %}
                {% set rating = (t.get('release_dates') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='release_dates') | first | default([]) | map(attribute='certification') | reject('eq', '') | first | default('') %}
              {% endif %}
              {% set poster = ('https://image.tmdb.org/t/p/w780' ~ t.poster_path) if t.get('poster_path') else '' %}
              {{ {
                'year': (t.get('first_air_date') or t.get('release_date') or '')[:4],
                'rating': rating,
                'genre': (t.get('genres') or []) | map(attribute='name') | first | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': 'tv-series' if tv else 'feature-movie',
                'series': '',
                'director': '' if tv else ((t.get('credits') or {}).get('crew') or []) | selectattr('job', 'eq', 'Director') | map(attribute='name') | first | default(''),
                'description': t.get('overview') or '',
                'poster': poster,
                'show_poster': poster if tv else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ t.backdrop_path) if t.get('backdrop_path') else ''
              } }}
            {% elif active and (owned or tvapp) and not changed %}
              {{ this.attributes.details | default({}) }}
            {% else %}
              {{ {} }}
            {% endif %}

  - triggers:
      - trigger: state
        entity_id: media_player.master_bedroom_appletv
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    variables:
      new_id: "{{ state_attr('media_player.master_bedroom_appletv', 'media_content_id') | default('', true) | string }}"
      active: "{{ is_state('media_player.master_bedroom_appletv', ['playing', 'paused']) }}"
      owned: "{{ new_id is match('^[0-9]+$') }}"
      tvapp: "{{ not owned and new_id != '' and is_state_attr('media_player.master_bedroom_appletv', 'app_id', 'com.apple.TVWatchList') and (state_attr('media_player.master_bedroom_appletv', 'media_duration') or 0) > 0 }}"
      title: "{{ state_attr('media_player.master_bedroom_appletv', 'media_series_title') or state_attr('media_player.master_bedroom_appletv', 'media_title') or '' }}"
      changed: "{{ new_id != (state_attr('sensor.master_bedroom_appletv_info', 'content_id') | default('', true) | string) or (state_attr('sensor.master_bedroom_appletv_info', 'lookup_version') | int(0)) != 2 }}"
    actions:
      - if:
          - condition: template
            value_template: "{{ active and owned and changed }}"
        then:
          - action: rest_command.itunes_lookup
            data:
              id: "{{ new_id }}"
            response_variable: itunes
            continue_on_error: true
          - if:
              - condition: template
                value_template: >
                  {% if itunes is defined and itunes.status == 200 %}{% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.kind | default('') in ['feature-movie', 'tv-episode'] }}{% else %}false{% endif %}
            then:
              - action: rest_command.tmdb_get
                data:
                  path: >
                    {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% if r.kind == 'feature-movie' %}search/movie?query={{ r.trackName | urlencode }}&primary_release_year={{ r.releaseDate[:4] }}{% else %}search/tv?query={{ r.artistName | regex_replace('\\s*\\([^)]*\\)$', '') | urlencode }}{% endif %}
                response_variable: tsearch
                continue_on_error: true
              - if:
                  - condition: template
                    value_template: "{{ tsearch is defined and tsearch.status == 200 and (tsearch.content.results | default([]) | count) > 0 }}"
                then:
                  - action: rest_command.tmdb_get
                    data:
                      path: >
                        {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% set res = tsearch.content.results %}
                        {% if r.kind == 'feature-movie' %}movie/{{ (res | first).id }}?append_to_response=credits
                        {%- else %}{% set aired = r.releaseDate[:10] %}{% set shows = res | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', aired) | sort(attribute='first_air_date', reverse=true) | list %}{% set show = (shows or res) | first %}{% set se = r.trackName | regex_findall('Season (\\d+), Episode (\\d+)') | first | default([]) %}
                        {%- if se %}tv/{{ show.id }}/season/{{ se[0] }}/episode/{{ se[1] }}?append_to_response=credits{% else %}tv/{{ show.id }}?append_to_response=credits{% endif %}{% endif %}
                    response_variable: tdetail
                    continue_on_error: true
      - if:
          - condition: template
            value_template: "{{ active and tvapp and changed and title != '' }}"
        then:
          - action: rest_command.tmdb_get
            data:
              path: "search/multi?query={{ title | urlencode }}"
            response_variable: msearch
            continue_on_error: true
          # Only an exact (case-insensitive) title match is trusted; anything else shows no details.
          - variables:
              hit: >
                {% set ns = namespace(m=[], p=[]) %}{% set t = title | lower %}{% if msearch is defined and msearch.status == 200 %}{% for x in msearch.content.results | default([]) if x.get('media_type') in ['movie', 'tv'] %}{% set n = (x.get('name') or x.get('title') or '') | lower %}{% if n == t %}{% set ns.m = ns.m + [x] %}{% elif n.endswith(': ' ~ t) %}{% set ns.p = ns.p + [x] %}{% endif %}{% endfor %}{% endif %}{{ (ns.m or ns.p) | first | default({}) }}
          - if:
              - condition: template
                value_template: "{{ hit.get('id') is not none }}"
            then:
              - action: rest_command.tmdb_get
                data:
                  path: "{{ hit.media_type }}/{{ hit.id }}?append_to_response=credits,{{ 'content_ratings' if hit.media_type == 'tv' else 'release_dates' }}"
                response_variable: tdetail
                continue_on_error: true
    sensor:
      - name: Master Bedroom Apple TV Info
        unique_id: master_bedroom_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.trackName | default('none') }}
          {% elif active and tvapp and tdetail is defined and tdetail.status == 200 %}
            {{ title }}
          {% elif active and (owned or tvapp) and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and (owned or tvapp)) else '' }}"
          lookup_version: "{{ 2 }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {% set t = tdetail.content if (tdetail is defined and tdetail.status == 200 and tdetail.content is mapping) else {} %}
              {% set people = ((t.get('credits') or {}).get('cast') or []) + (t.get('guest_stars') or []) %}
              {% set ns = namespace(cast=[]) %}
              {% for p in people[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% set art = t.get('backdrop_path') or t.get('still_path') %}
              {% set sres = tsearch.content.results if (tsearch is defined and tsearch.status == 200) else [] %}
              {% set shows = sres | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', (r.releaseDate | default(''))[:10]) | sort(attribute='first_air_date', reverse=true) | list %}
              {% set sp = ((shows or sres) | first | default({})).get('poster_path') if r.kind | default('') == 'tv-episode' else none %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': r.kind | default(''),
                'series': r.artistName | default('') if r.kind | default('') == 'tv-episode' else '',
                'director': r.artistName | default('') if r.kind | default('') == 'feature-movie' else '',
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb'),
                'show_poster': ('https://image.tmdb.org/t/p/w780' ~ sp) if sp else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ art) if art else ''
              } }}
            {% elif active and tvapp and tdetail is defined and tdetail.status == 200 and tdetail.content is mapping %}
              {% set t = tdetail.content %}{% set tv = 'first_air_date' in t %}
              {% set mins = ((state_attr('media_player.master_bedroom_appletv', 'media_duration') or 0) / 60) | round(0) | int %}
              {% set ns = namespace(cast=[]) %}
              {% for p in ((t.get('credits') or {}).get('cast') or [])[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% if tv %}
                {% set rating = (t.get('content_ratings') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='rating') | first | default('') %}
              {% else %}
                {% set rating = (t.get('release_dates') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='release_dates') | first | default([]) | map(attribute='certification') | reject('eq', '') | first | default('') %}
              {% endif %}
              {% set poster = ('https://image.tmdb.org/t/p/w780' ~ t.poster_path) if t.get('poster_path') else '' %}
              {{ {
                'year': (t.get('first_air_date') or t.get('release_date') or '')[:4],
                'rating': rating,
                'genre': (t.get('genres') or []) | map(attribute='name') | first | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': 'tv-series' if tv else 'feature-movie',
                'series': '',
                'director': '' if tv else ((t.get('credits') or {}).get('crew') or []) | selectattr('job', 'eq', 'Director') | map(attribute='name') | first | default(''),
                'description': t.get('overview') or '',
                'poster': poster,
                'show_poster': poster if tv else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ t.backdrop_path) if t.get('backdrop_path') else ''
              } }}
            {% elif active and (owned or tvapp) and not changed %}
              {{ this.attributes.details | default({}) }}
            {% else %}
              {{ {} }}
            {% endif %}

  - triggers:
      - trigger: state
        entity_id: media_player.family_room_appletv
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    variables:
      new_id: "{{ state_attr('media_player.family_room_appletv', 'media_content_id') | default('', true) | string }}"
      active: "{{ is_state('media_player.family_room_appletv', ['playing', 'paused']) }}"
      owned: "{{ new_id is match('^[0-9]+$') }}"
      tvapp: "{{ not owned and new_id != '' and is_state_attr('media_player.family_room_appletv', 'app_id', 'com.apple.TVWatchList') and (state_attr('media_player.family_room_appletv', 'media_duration') or 0) > 0 }}"
      title: "{{ state_attr('media_player.family_room_appletv', 'media_series_title') or state_attr('media_player.family_room_appletv', 'media_title') or '' }}"
      changed: "{{ new_id != (state_attr('sensor.family_room_appletv_info', 'content_id') | default('', true) | string) or (state_attr('sensor.family_room_appletv_info', 'lookup_version') | int(0)) != 2 }}"
    actions:
      - if:
          - condition: template
            value_template: "{{ active and owned and changed }}"
        then:
          - action: rest_command.itunes_lookup
            data:
              id: "{{ new_id }}"
            response_variable: itunes
            continue_on_error: true
          - if:
              - condition: template
                value_template: >
                  {% if itunes is defined and itunes.status == 200 %}{% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.kind | default('') in ['feature-movie', 'tv-episode'] }}{% else %}false{% endif %}
            then:
              - action: rest_command.tmdb_get
                data:
                  path: >
                    {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% if r.kind == 'feature-movie' %}search/movie?query={{ r.trackName | urlencode }}&primary_release_year={{ r.releaseDate[:4] }}{% else %}search/tv?query={{ r.artistName | regex_replace('\\s*\\([^)]*\\)$', '') | urlencode }}{% endif %}
                response_variable: tsearch
                continue_on_error: true
              - if:
                  - condition: template
                    value_template: "{{ tsearch is defined and tsearch.status == 200 and (tsearch.content.results | default([]) | count) > 0 }}"
                then:
                  - action: rest_command.tmdb_get
                    data:
                      path: >
                        {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{% set res = tsearch.content.results %}
                        {% if r.kind == 'feature-movie' %}movie/{{ (res | first).id }}?append_to_response=credits
                        {%- else %}{% set aired = r.releaseDate[:10] %}{% set shows = res | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', aired) | sort(attribute='first_air_date', reverse=true) | list %}{% set show = (shows or res) | first %}{% set se = r.trackName | regex_findall('Season (\\d+), Episode (\\d+)') | first | default([]) %}
                        {%- if se %}tv/{{ show.id }}/season/{{ se[0] }}/episode/{{ se[1] }}?append_to_response=credits{% else %}tv/{{ show.id }}?append_to_response=credits{% endif %}{% endif %}
                    response_variable: tdetail
                    continue_on_error: true
      - if:
          - condition: template
            value_template: "{{ active and tvapp and changed and title != '' }}"
        then:
          - action: rest_command.tmdb_get
            data:
              path: "search/multi?query={{ title | urlencode }}"
            response_variable: msearch
            continue_on_error: true
          # Only an exact (case-insensitive) title match is trusted; anything else shows no details.
          - variables:
              hit: >
                {% set ns = namespace(m=[], p=[]) %}{% set t = title | lower %}{% if msearch is defined and msearch.status == 200 %}{% for x in msearch.content.results | default([]) if x.get('media_type') in ['movie', 'tv'] %}{% set n = (x.get('name') or x.get('title') or '') | lower %}{% if n == t %}{% set ns.m = ns.m + [x] %}{% elif n.endswith(': ' ~ t) %}{% set ns.p = ns.p + [x] %}{% endif %}{% endfor %}{% endif %}{{ (ns.m or ns.p) | first | default({}) }}
          - if:
              - condition: template
                value_template: "{{ hit.get('id') is not none }}"
            then:
              - action: rest_command.tmdb_get
                data:
                  path: "{{ hit.media_type }}/{{ hit.id }}?append_to_response=credits,{{ 'content_ratings' if hit.media_type == 'tv' else 'release_dates' }}"
                response_variable: tdetail
                continue_on_error: true
    sensor:
      - name: Family Room Apple TV Info
        unique_id: family_room_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}{{ r.trackName | default('none') }}
          {% elif active and tvapp and tdetail is defined and tdetail.status == 200 %}
            {{ title }}
          {% elif active and (owned or tvapp) and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and (owned or tvapp)) else '' }}"
          lookup_version: "{{ 2 }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}{% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {% set t = tdetail.content if (tdetail is defined and tdetail.status == 200 and tdetail.content is mapping) else {} %}
              {% set people = ((t.get('credits') or {}).get('cast') or []) + (t.get('guest_stars') or []) %}
              {% set ns = namespace(cast=[]) %}
              {% for p in people[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% set art = t.get('backdrop_path') or t.get('still_path') %}
              {% set sres = tsearch.content.results if (tsearch is defined and tsearch.status == 200) else [] %}
              {% set shows = sres | selectattr('first_air_date', 'defined') | rejectattr('first_air_date', 'eq', '') | selectattr('first_air_date', 'le', (r.releaseDate | default(''))[:10]) | sort(attribute='first_air_date', reverse=true) | list %}
              {% set sp = ((shows or sres) | first | default({})).get('poster_path') if r.kind | default('') == 'tv-episode' else none %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': r.kind | default(''),
                'series': r.artistName | default('') if r.kind | default('') == 'tv-episode' else '',
                'director': r.artistName | default('') if r.kind | default('') == 'feature-movie' else '',
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb'),
                'show_poster': ('https://image.tmdb.org/t/p/w780' ~ sp) if sp else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ art) if art else ''
              } }}
            {% elif active and tvapp and tdetail is defined and tdetail.status == 200 and tdetail.content is mapping %}
              {% set t = tdetail.content %}{% set tv = 'first_air_date' in t %}
              {% set mins = ((state_attr('media_player.family_room_appletv', 'media_duration') or 0) / 60) | round(0) | int %}
              {% set ns = namespace(cast=[]) %}
              {% for p in ((t.get('credits') or {}).get('cast') or [])[:8] %}
                {% set ns.cast = ns.cast + [{'name': p.name, 'role': p.character | default(''), 'photo': ('https://image.tmdb.org/t/p/w185' ~ p.profile_path) if p.profile_path else ''}] %}
              {% endfor %}
              {% if tv %}
                {% set rating = (t.get('content_ratings') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='rating') | first | default('') %}
              {% else %}
                {% set rating = (t.get('release_dates') or {}).get('results', []) | selectattr('iso_3166_1', 'eq', 'US') | map(attribute='release_dates') | first | default([]) | map(attribute='certification') | reject('eq', '') | first | default('') %}
              {% endif %}
              {% set poster = ('https://image.tmdb.org/t/p/w780' ~ t.poster_path) if t.get('poster_path') else '' %}
              {{ {
                'year': (t.get('first_air_date') or t.get('release_date') or '')[:4],
                'rating': rating,
                'genre': (t.get('genres') or []) | map(attribute='name') | first | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'kind': 'tv-series' if tv else 'feature-movie',
                'series': '',
                'director': '' if tv else ((t.get('credits') or {}).get('crew') or []) | selectattr('job', 'eq', 'Director') | map(attribute='name') | first | default(''),
                'description': t.get('overview') or '',
                'poster': poster,
                'show_poster': poster if tv else '',
                'tagline': t.get('tagline') or '',
                'score': ('%.1f' | format(t.vote_average)) if (t.get('vote_count') or 0) > 0 else '',
                'cast': ns.cast,
                'backdrop': ('https://image.tmdb.org/t/p/w1280' ~ t.backdrop_path) if t.get('backdrop_path') else ''
              } }}
            {% elif active and (owned or tvapp) and not changed %}
              {{ this.attributes.details | default({}) }}
            {% else %}
              {{ {} }}
            {% endif %}
```

**Media seek package** — `ha/packages/media_seek.yaml`, deployed to
`/config/packages/media_seek.yaml`, reload with `template.reload`; a change to its `recorder:`
block needs a restart. It covers all three Apple TVs, Family Room included, ahead of its remote
pop-up. HA derives `number.*_apple_tv_position` from the "Apple TV" names; rename them to
`*_appletv_position` after the first reload, like the activity sensors (the recorder exclusion
already uses the renamed IDs):

```yaml
# Playback position of each Apple TV as a number entity, so the
# home-main remote pop-ups can show it as a Bubble Card slider: drag to a point and
# release to seek. Bubble's slider can't bind to a media player's position, only to a
# number, and setting this number sends media_player.media_seek.
#
# The Apple TV only reports media_position when playback starts, pauses or seeks, so the
# state adds the time elapsed since media_position_updated_at while playing. A 2-second
# time_pattern keeps the slider moving; it is gated to playing/paused so an idle or off
# Apple TV does no work. Unavailable when the app reports no duration (live TV), which
# hides the slider. See guides/home_dashboard.md.
#
# A seek fires media_seek_requested, which the number takes as its value and holds for 6 s
# (advancing while playing): the Apple TV keeps reporting the pre-seek position for a few
# seconds, and recalculating from it in that window made the slider jump back and forth.
#
# The position is excluded from the recorder: at 2 s it would write ~1,800 useless rows per
# hour of playback. This is the only recorder config in the instance (configuration.yaml
# has none); recorder config is not reloadable, so changing it needs a restart.
#
# Deployed to /config/packages/media_seek.yaml; reload with template.reload (a restart if
# the recorder block changes).

recorder:
  exclude:
    entities:
      - number.living_room_appletv_position
      - number.master_bedroom_appletv_position
      - number.family_room_appletv_position

template:
  - trigger:
      - trigger: time_pattern
        seconds: "/2"
      - trigger: state
        entity_id: media_player.living_room_appletv
      - trigger: event
        event_type: media_seek_requested
        event_data:
          entity_id: media_player.living_room_appletv
        id: seek
    condition:
      - condition: state
        entity_id: media_player.living_room_appletv
        state:
          - playing
          - paused
    number:
      - name: Living Room Apple TV Position
        unique_id: living_room_appletv_position
        icon: mdi:play-box-outline
        unit_of_measurement: s
        min: 0
        max: "{{ state_attr('media_player.living_room_appletv', 'media_duration') | float(1) }}"
        step: 1
        optimistic: true
        availability: "{{ state_attr('media_player.living_room_appletv', 'media_duration') | float(0) > 0 }}"
        state: >
          {% set e = 'media_player.living_room_appletv' %}
          {% set t = now().timestamp() %}
          {% set seek_at = this.attributes.seek_at | default(0) | float(0) %}
          {% if trigger.id == 'seek' %}
            {{ trigger.event.data.position | float(0) | round(0) }}
          {% elif t - seek_at < 6 %}
            {% set held = this.attributes.seek_value | default(0) | float(0) %}
            {{ (held + ((t - seek_at) if is_state(e, 'playing') else 0)) | round(0) }}
          {% else %}
            {% set pos = state_attr(e, 'media_position') | float(0) %}
            {% set upd = state_attr(e, 'media_position_updated_at') %}
            {% if is_state(e, 'playing') and upd is not none %}
              {% set pos = pos + (now() - upd).total_seconds() %}
            {% endif %}
            {{ [pos, state_attr(e, 'media_duration') | float(0)] | min | round(0) }}
          {% endif %}
        attributes:
          seek_at: "{{ now().timestamp() if trigger.id == 'seek' else (this.attributes.seek_at | default(0)) }}"
          seek_value: "{{ trigger.event.data.position if trigger.id == 'seek' else (this.attributes.seek_value | default(0)) }}"
        set_value:
          - action: media_player.media_seek
            target:
              entity_id: media_player.living_room_appletv
            data:
              seek_position: "{{ value }}"
          - event: media_seek_requested
            event_data:
              entity_id: media_player.living_room_appletv
              position: "{{ value }}"

  - trigger:
      - trigger: time_pattern
        seconds: "/2"
      - trigger: state
        entity_id: media_player.master_bedroom_appletv
      - trigger: event
        event_type: media_seek_requested
        event_data:
          entity_id: media_player.master_bedroom_appletv
        id: seek
    condition:
      - condition: state
        entity_id: media_player.master_bedroom_appletv
        state:
          - playing
          - paused
    number:
      - name: Master Bedroom Apple TV Position
        unique_id: master_bedroom_appletv_position
        icon: mdi:play-box-outline
        unit_of_measurement: s
        min: 0
        max: "{{ state_attr('media_player.master_bedroom_appletv', 'media_duration') | float(1) }}"
        step: 1
        optimistic: true
        availability: "{{ state_attr('media_player.master_bedroom_appletv', 'media_duration') | float(0) > 0 }}"
        state: >
          {% set e = 'media_player.master_bedroom_appletv' %}
          {% set t = now().timestamp() %}
          {% set seek_at = this.attributes.seek_at | default(0) | float(0) %}
          {% if trigger.id == 'seek' %}
            {{ trigger.event.data.position | float(0) | round(0) }}
          {% elif t - seek_at < 6 %}
            {% set held = this.attributes.seek_value | default(0) | float(0) %}
            {{ (held + ((t - seek_at) if is_state(e, 'playing') else 0)) | round(0) }}
          {% else %}
            {% set pos = state_attr(e, 'media_position') | float(0) %}
            {% set upd = state_attr(e, 'media_position_updated_at') %}
            {% if is_state(e, 'playing') and upd is not none %}
              {% set pos = pos + (now() - upd).total_seconds() %}
            {% endif %}
            {{ [pos, state_attr(e, 'media_duration') | float(0)] | min | round(0) }}
          {% endif %}
        attributes:
          seek_at: "{{ now().timestamp() if trigger.id == 'seek' else (this.attributes.seek_at | default(0)) }}"
          seek_value: "{{ trigger.event.data.position if trigger.id == 'seek' else (this.attributes.seek_value | default(0)) }}"
        set_value:
          - action: media_player.media_seek
            target:
              entity_id: media_player.master_bedroom_appletv
            data:
              seek_position: "{{ value }}"
          - event: media_seek_requested
            event_data:
              entity_id: media_player.master_bedroom_appletv
              position: "{{ value }}"

  - trigger:
      - trigger: time_pattern
        seconds: "/2"
      - trigger: state
        entity_id: media_player.family_room_appletv
      - trigger: event
        event_type: media_seek_requested
        event_data:
          entity_id: media_player.family_room_appletv
        id: seek
    condition:
      - condition: state
        entity_id: media_player.family_room_appletv
        state:
          - playing
          - paused
    number:
      - name: Family Room Apple TV Position
        unique_id: family_room_appletv_position
        icon: mdi:play-box-outline
        unit_of_measurement: s
        min: 0
        max: "{{ state_attr('media_player.family_room_appletv', 'media_duration') | float(1) }}"
        step: 1
        optimistic: true
        availability: "{{ state_attr('media_player.family_room_appletv', 'media_duration') | float(0) > 0 }}"
        state: >
          {% set e = 'media_player.family_room_appletv' %}
          {% set t = now().timestamp() %}
          {% set seek_at = this.attributes.seek_at | default(0) | float(0) %}
          {% if trigger.id == 'seek' %}
            {{ trigger.event.data.position | float(0) | round(0) }}
          {% elif t - seek_at < 6 %}
            {% set held = this.attributes.seek_value | default(0) | float(0) %}
            {{ (held + ((t - seek_at) if is_state(e, 'playing') else 0)) | round(0) }}
          {% else %}
            {% set pos = state_attr(e, 'media_position') | float(0) %}
            {% set upd = state_attr(e, 'media_position_updated_at') %}
            {% if is_state(e, 'playing') and upd is not none %}
              {% set pos = pos + (now() - upd).total_seconds() %}
            {% endif %}
            {{ [pos, state_attr(e, 'media_duration') | float(0)] | min | round(0) }}
          {% endif %}
        attributes:
          seek_at: "{{ now().timestamp() if trigger.id == 'seek' else (this.attributes.seek_at | default(0)) }}"
          seek_value: "{{ trigger.event.data.position if trigger.id == 'seek' else (this.attributes.seek_value | default(0)) }}"
        set_value:
          - action: media_player.media_seek
            target:
              entity_id: media_player.family_room_appletv
            data:
              seek_position: "{{ value }}"
          - event: media_seek_requested
            event_data:
              entity_id: media_player.family_room_appletv
              position: "{{ value }}"
```

**Happening now** sits below the greeting: a `Happening now` heading and a 1-column grid (full-width cards, so the status line never scrolls),
both shown only while at least one card is visible. Each card is a Bubble `button` with the
`progress_fill` module, which fills the card left to right with progress; the card's `styles`
set `--fill` (percent), `--fill-color`, and `--fill-tint`. The fill starts at the icon's right
edge so a low percentage isn't hidden behind the icon. The laundry cards' phase, fill colour,
and fault line come from `laundry_phase`, `laundry_color`, and `laundry_fault` in
`dashboard.jinja`.

| Card | Visible while | Line under the name | Fill | Tap |
|---|---|---|---|---|
| Washer / Dryer (name shows the phase: "Washer (Rinsing)", "Dryer (Cooling)", "(Done)", "(Fault)"; LG `running` reads "Washing" / "Drying") | Running, done (`alerting`), or faulted | "23 min left"; "Unload" when done; on a fault the LG error code ("Unable to lock") if its error event fired within 5 minutes of the fault, else "Check the washer" | Cyan, cycle progress; amber when paused or done (full); red on a fault | `#laundry` |
| Dishwasher | `binary_sensor.kitchen_dishwasher_running` on | "Running · N min" | Cyan, even tint (no progress reported) | `#laundry` |
| Vacuum (name shows the action: "Vacuum (Cleaning)", "(Paused)", "(Returning to dock)", "(Docking)", "(Error)") | Cleaning, returning, paused, or error | "Room · 27%" while cleaning or paused; "27%" otherwise; the error text on error | Purple, cleaning progress; amber when paused; red on error | `#vacuum` |

**Greeting** sits below the chip strip: a text-only markdown card, "Good morning/afternoon/
evening, <first name>!" (05:00–11:59 / 12:00–16:59 / otherwise, the logged-in user's first
name) over the latest briefing headline in italics (it covers only what is left of today). Markdown sizes itself to its content, so
the line never overlaps the chips. A UIX style trims the heading's bottom margin.

### 4. Room tiles

| Tile | Hold toggles | Tile buttons | Summary |
|---|---|---|---|
| Living Room | Ceiling light | Ceiling light, Fan, Apple TV | lights · fan · temp |
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

### 5. Pop-ups

All pop-ups use `popup_mode: adaptive-dialog` and `popup_style: bubble`. All except the six
room pop-ups also set `show_header: false`: no title row or close button, closed by swiping
down on a phone or tapping outside / pressing Esc on a desktop, with the first card saying what
the pop-up is. The room pop-ups keep their header, which shows the same `room_summary` as the
tile, until they get a room hero (#13 step 4).

| Hash | Contents |
|---|---|
| `#living-room` | Apple TV card at the top, the same card as on Home (only while active; tap opens `#living-room-remote`, where volume, apps and sound settings live), otherwise a compact Apple TV card showing its state that opens the remote, with a power button (`media_player.turn_on`) only while it is `off`; 4 lights, thermostat + fireplace (Bubble climate) |
| `#living-room-remote` | No header; `popup_style: home-assistant` (Bubble Card ≥ the release that added it) with no `popup_mode`, so on mobile the sheet keeps the more-info dialog's full height and doesn't resize as tabs change. A segmented switch at the top (`input_select.living_room_remote_view`: Now Playing · Apple TV (`phu:appletv-sim`) · TV; the pop-up's `close_action` sets it back to Apple TV, so every open starts on that tab) shows one tab at a time through card `visibility`. **Now Playing** is information only: a markdown card led by a 2:3 poster at 62% width (Apple's store poster for a movie, the series' TMDB poster for an episode or a TV-app series, TMDB's poster for a TV-app movie; TMDB's wide background art, then Apple's art, at full width when there's no poster), the series as a small heading for a TV episode, the title, the tagline in italics, the content rating as an outlined badge (left out when there is none) with year · genre · runtime · ★ TMDB score, the director for a movie, the full description, and a Cast grid (up to 8, four to a row: round headshot, name, role; an episode lists its regulars then guest stars), all from `sensor.living_room_appletv_info`. The tab is dimmed and untappable while the sensor is `none`, and if it is selected when details disappear the Apple TV tab shows instead. **Apple TV** opens with the artwork alone (hidden while the Apple TV is off): a Bubble button card whose JS style template sets the image as its background with `background-size: contain`, so a portrait poster or square series art shows whole at up to 150 px tall (media cards fit artwork into a fixed-shape slot and crop the rest); wide art (anything but a poster or a fallback icon) instead turns the card 16:9 with no padding and fills it edge to edge; tapping it switches to Now Playing. Below it, a markdown card shows the title centred at 15 px semibold, with the series above it in 12 px secondary text (shown while playing or paused). While `sensor.living_room_appletv_info` matches what is playing, both come from it, so a store episode shows its series and episode name ("Season 2, Episode 20: The Last Page"); otherwise the player's own `media_title` is used. A TV-app stream reports only the show name, so it has no episode line. The image follows the room media card's rule (*Room media cards*, Step 3): TMDB's backdrop for a movie once `sensor.living_room_appletv_info` has looked it up, otherwise the Apple TV's own artwork (a 16:9 still for a TV episode), then the sensor's art, then the app's fallback image, else the TV app's image. Between two titles the Apple TV reports itself idle for up to about 15 s, and an Apple-store title's lookup takes a moment, so in either case the card keeps the last artwork it showed (held in a `window` variable), falling back to the app's image after 30 s. A leftover paused session from another app (`binary_sensor.living_room_appletv_active` off while the player is `paused`) counts as nothing playing: the title card hides and the hold falls back to the TV app's image rather than that app's. Then the timeline, then a volume row for the Soundbar (mute on the left, filled while muted, via `script.household_media_toggle_mute` since a tap action can't read the current mute state; then − / level / +, ±2% a tap, the level reading "Muted" while muted), then Speech · Night · Sub, the app favourites, and the Universal Remote Card (a left column of back, play/pause and skip −10 s, where play/pause shows pause while playing and play otherwise and runs Household: Apple TV Play Pause (`script.household_appletv_play_pause`): `media_player.media_pause` / `media_play` for a title with a duration, the `play_pause` remote key for a live stream, since the Apple TV ignores the key during a movie and refuses `media_pause` on live TV; the 190 × 232 px touchpad, which runs the full height of the side columns; a right column of home, hold-to-toggle power and skip +10 s; the keyboard sits in its own row below and takes no space unless an Apple TV text field has focus). **TV** controls the LG (`media_player.living_room_tv`): input pills (Apple TV, HDMI 3, HDMI 4, Live TV; the current input is filled, via the `segmented` module reading `source`), channel presets shown as network logos (`phu:cbs` 11.1, `phu:abc` 13.1, `phu:nbc` 24.1, `phu:fox` 36.1: `media_player.play_media` with `media_content_type: channel` and the LG's `11-1` channel-number form), and a Universal Remote Card on the LG webOS platform with a 1–9 / – 0 enter number pad, channel up and down, guide, and back. Timeline: a Bubble slider on `number.living_room_appletv_position` (from `ha/packages/media_seek.yaml`; refreshed every 2 s while playing, holding a dragged value for 6 s because the Apple TV keeps reporting the pre-seek position, excluded from the recorder) that fills purple, reads e.g. "0:21:41 / 1:47:24", seeks on release, labels the drag target as m:ss through the `time_slider` module, and hides when there is no duration (live TV) or the Apple TV isn't playing or paused (the number keeps its last value while off) |
| `#kitchen` | Sink light, dishwasher and refrigerator tiles, HomePod |
| `#family-room` | Ambient lamp, 2 pinball underglows, 3 game power switches, Apple TV media card (only while active) with an Apps · Speech · Night row under it |
| `#office` | 7 lights, fan speed (tile `fan-speed` feature), HomePod |
| `#master-bedroom` | Ceiling light, nightstand lamp, fan speed, Apple TV card, the same as on Home (only while active; tap opens `#master-bedroom-remote`), otherwise the same compact Apple TV card as `#living-room`, HomePod, bathroom speaker |
| `#master-bedroom-remote` | `#living-room-remote` for the bedroom Apple TV with only the Now Playing and Apple TV tabs (`input_select.master_bedroom_remote_view`), since the bedroom TV is only used with the Apple TV, and no Speech · Night · Sub row: the volume row drives the LG TV (`media_player.master_bedroom_tv`, which reports `unavailable` while the TV is off), and the keyboard uses the Master Bedroom AppleTV config entry |
| `#averys-room` | Ceiling light, desk and dresser lamps, fan speed, HomePod |
| `#security` | Doorbell camera (square crop, first); lock, garage door, garage interior door, doors & windows; Water (the 4 leak sensors); outside lights |
| `#hvac` | Hero (indoor temperature; Heating to / Cooling to / Holding range / Paused, and preset; humidity; amber or blue tint while running), heat and cool setpoint steppers, segmented presets (Home · Away · Sleep), fireplace (hold toggles off ↔ heat; amber while on), Today: three metric tiles for whichever mode has run more today (runtime, cycles, average cycle — amber under 10 min, an early short-cycling sign), Last 12 hours chart (apexcharts: indoor temperature, dashed setpoints, outside temperature, heating/cooling bands), Last 14 days chart (apexcharts on long-term statistics: daily heating/cooling hours as stacked columns via `change`, daily mean outside temperature on the right axis; `extend_to: false` so the live point doesn't narrow the columns) |
| `#weather` | Hero (outside temperature, condition icon, condition with today's high and low, feels-like), the AI briefing tip (text-only markdown, hidden until the briefing exists), rain line (first hour in the next 24 with a 40%+ chance, or "No rain expected"), six `metric_tile` tiles (wind and direction, humidity, rain chance over 24 h, AQI and dominant pollutant in the EPA colour above 50, UV index, next sunset or sunrise), Next 24 hours chart (apexcharts from `sensor.outside_forecast`: temperature line, rain-chance columns), Next 5 days (Bubble Weather `weather_forecast` module, `card_layout: weather_only`), Air quality pollutant tiles only while AQI > 50 |
| `#vacuum` | Status hero (state; room, area and time while out, last clean when docked; battery), primary action (amber Pause while cleaning, Start/Resume otherwise, with Dock and Stop), How: segmented Mode, Suction and Water (Water only in vacuum + mop with the pad on), routine pause, Mop now (confirm), map (only when out or ran today; cropped to 3:2 and zoomed 135% with a UIX `background-size` rule, since Roborock renders the plan small inside a 2340×1848 canvas), Care & settings row (icon amber/red when a consumable is low or due) |
| `#vacuum-care` | Mop pass (segmented Fast / Standard), mop pad and water status, robot status, 5 consumables |
| `#laundry` | Washer and dryer status, remaining, progress, start/finish; "stop reminders" acknowledge (only while `alerting`); dishwasher; washer stats; utility room light |

`#laundry` is reachable only while a washer, dryer, or dishwasher chip is showing; it is about
the current cycle.

**Vacuum consumables** (filter clean, filter replace, main brush, side brush, sensors) use the `consumable_status` Bubble module (icon red at ≤ 0 h left, amber
under 10 h, green otherwise). Tap opens more-info; hold calls
`script.household_vacuum_reset_consumable` immediately — no confirmation, since a reset is
only done right after the maintenance itself (see `guides/vacuum_cleaning_routine.md`).

**Laundry acknowledge** sets `input_select.utility_room_<appliance>_status` to `acknowledged`,
which ends *Utility Room: Laundry Announcement*'s repeat loop (it continues only while a status
is `alerting` or `fault`). Retrieval or the next cycle returns the status to `idle`.

**Weather forecast package** — `ha/packages/weather_forecast.yaml`, deployed to
`/config/packages/weather_forecast.yaml`, reload with `template.reload`. It creates
`sensor.outside_forecast`, which the `#weather` hero, rain line, Rain tile and Next 24 hours
chart read:

```yaml
# Outside forecast snapshot for the home-main #weather pop-up.
#
# Weather entities only hand out forecasts through the weather.get_forecasts action, so a
# card can't read them directly. This trigger-based sensor fetches the hourly and daily
# forecasts every 30 minutes and keeps a trimmed copy as attributes: the next 24 hours
# (time, temperature, rain chance, condition) for the apexcharts hourly chart, today's
# high and low, and the first hour in the next 24 with a 40%+ chance of rain.
# The full hourly response covers about a week; trimming it keeps the attribute small
# enough for the recorder.
#
# The response variables are named *_fc because an attribute named `hourly` would shadow a
# response variable of the same name for the attributes rendered after it.
#
# State: today's forecast high. See guides/home_dashboard.md.
# Deployed to /config/packages/weather_forecast.yaml; reload with template.reload.

template:
  - trigger:
      - trigger: time_pattern
        minutes: /30
      - trigger: homeassistant
        event: start
      - trigger: event
        event_type: event_template_reloaded
    action:
      - action: weather.get_forecasts
        target:
          entity_id: weather.outside_waterville_oh_usa
        data:
          type: hourly
        response_variable: hourly_fc
      - action: weather.get_forecasts
        target:
          entity_id: weather.outside_waterville_oh_usa
        data:
          type: daily
        response_variable: daily_fc
    sensor:
      - name: Outside Forecast
        unique_id: outside_forecast
        icon: mdi:weather-partly-cloudy
        device_class: temperature
        unit_of_measurement: "°F"
        state: "{{ daily_fc['weather.outside_waterville_oh_usa'].forecast[0].temperature }}"
        attributes:
          low: "{{ daily_fc['weather.outside_waterville_oh_usa'].forecast[0].templow }}"
          hourly: >-
            {% set ns = namespace(out=[]) %}
            {% for h in hourly_fc['weather.outside_waterville_oh_usa'].forecast[:24] %}
              {% set ns.out = ns.out + [{'datetime': h.datetime, 'temperature': h.temperature,
                 'rain': h.precipitation_probability | default(0), 'condition': h.condition}] %}
            {% endfor %}
            {{ ns.out }}
          rain_max_24h: >-
            {{ hourly_fc['weather.outside_waterville_oh_usa'].forecast[:24]
               | map(attribute='precipitation_probability', default=0) | map('float', 0) | max | int }}
          next_rain: >-
            {% set wet = hourly_fc['weather.outside_waterville_oh_usa'].forecast[:24]
               | selectattr('precipitation_probability', 'defined')
               | selectattr('precipitation_probability', 'ge', 40) | list %}
            {{ wet[0].datetime if wet else none }}
```

Static `state_content` text on a Bubble button must be a template (`"{{ 'Humidity' }}"`): a
plain string is read as an attribute name and renders blank.

### 6. Views

Navbar order: Home · Rooms · Climate · Chores · More. Rooms opens `/home-main/home#rooms`; More opens a menu with Energy and Maintenance.

| View | Path | Contents |
|---|---|---|
| Home | `home` | Steps 3–5 |
| Climate | `climate` | HVAC row (thermostat state line; tap opens `/home-main/home#hvac`); Inside and Outside cards (Bubble button + Bubble Graphs, 24 h temperature graph, value line "74.1° · 55%"; Inside reads the Main Floor averages); the AI Insight card (below); then two collapsible sections, both collapsed by default: Rooms — per-room temperature cards (24 h area graph under the name and value), each labelled with its offset from `sensor.main_floor_temperature` and tinted blue or amber, graph included, at 1.5° or more (`room_temp_style` in `dashboard.jinja` sets `--room-tint`, which the graph `color` reads; utility room has no offset); Humidity — the same card per room, value rounded to a whole percent, tinted amber (graph included) at 40% or below or above 60% (`room_humidity_style` in `dashboard.jinja`; 40% is when the bedroom humidifiers go on) |
| Energy | `energy` | The AI Insight card (below); built-in energy cards: date selection, compare, Sankey, per-device detail graph; cost table; generator status, warning, maintenance, last ran, run time, battery, connection, status message |
| Chores | `chores` | `chore-calendar-card` on `calendar.household_chores` |
| Maintenance | `maintenance` | Collapsible sections (Expander Card; Availability and Batteries open by default, the rest collapsed): availability (offline and partially unavailable devices from `sensor.household_devices_offline`, see `guides/device_availability.md`); vacuum consumables (same cards as `#vacuum-care`); pending updates; network (WAN, Firewalla, speed test, latency, loss, alarms, modem resets, modem maintenance, Litra agent); batteries |

**Energy** reads the Energy settings: grid import from `sensor.household_energy_monitor_total_energy_delivered`
with `sensor.household_energy_monitor_power_demand` as the grid power sensor, and the six
tracked devices. Small smart plugs are deliberately not tracked devices — they read as
"untracked" in the Sankey. The live power cards (`power-total`, `power-sankey`) are not used
here; they fail outside the built-in Energy dashboard, which keeps its own Now tab.

**AI Insight** (Climate and Energy): an Expander Card, open by default (`storage-id` remembers a
collapse per device) and toggled only by its chevron (`title-card-clickable: false`, so the ✓
badge doesn't collapse it). Its title card is a heading "AI Insight" (`mdi:creation`) with an age badge
(`state_content: last_updated`) and, while a note is flagged, a ✓ button badge that presses
`input_button.household_ai_climate_seen` / `_energy_seen`; then one markdown card with the note
in italics (no headline), "Nothing notable yesterday." on a quiet day, *Working on it…* while
the script runs, and a native `<details>` fold-out, **History (past month)**, listing the last
30 days' earlier flagged notes by day (at most 12). Sunday weekly notes render as
`<strong>`/`<em>` instead of `<b>`/`<i>`, which the card's UIX style colours `--teal-color`, so a
week-in-review stands apart without a label; the same applies to the main note on a Sunday. The fold-out sits inside the same card so it reads as part of
the insight, and appears only when there are earlier notes. Content comes from
`sensor.household_ai_climate_insight` / `_energy_insight` (`guides/ai_insights.md`).

**Navbar badges and visibility:** More shows a red badge while any `update.*` entity is on or
`sensor.household_devices_offline` is above 0 (Maintenance inside its menu carries the same
badge), or while
`binary_sensor.outside_home_generator_warning` or `_maintenance_alert` is on (Energy inside the
menu carries that one) — generator
problems surface there rather than as a Home chip. The Maintenance item is hidden for
non-admin users (`hidden: [[[ return !user.is_admin ]]]`).

**AI Insight badges:** Climate, and Energy inside More, show an amber badge with the
`mdi:creation` icon (badge `icon` and `icon_color`) while the newest `history`
entry's `at` is newer than that section's seen marker. On More and Energy the red fault badge
wins: `color` and `icon` are templated to red with no icon whenever a fault is showing.

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
| Household AI Briefing / Climate Insight / Energy Insight | `sensor.household_ai_briefing`, `sensor.household_ai_climate_insight`, `sensor.household_ai_energy_insight` | Template sensors (`guides/ai_insights.md`) |
| Household AI Climate Seen / Energy Seen | `input_button.household_ai_climate_seen`, `input_button.household_ai_energy_seen` | Helpers (`guides/ai_insights.md`) |
| Living Room Vacuum Filter Clean Time Left | `sensor.living_room_vacuum_filter_clean_time_left` | Template helper |
| HVAC Mode Before Pause | `input_select.household_hvac_mode_before_pause` | Helper |
| Main Floor Temperature / Humidity | `sensor.main_floor_temperature`, `sensor.main_floor_humidity` | Combine helpers (`min_max`, mean) over Living Room, Kitchen, Office, Master Bedroom, Avery's Room |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/custom_templates/dashboard.jinja` | `/config/custom_templates/dashboard.jinja` | Shared macros (repo authoritative) |
| `ha/dashboards/home-main.yaml` | HA storage (`home-main`) | Dashboard mirror (HA authoritative) |
| `ha/bubble_modules/consumable_status.yaml` | `/config/bubble_card/modules/consumable_status.yaml` | Consumable icon colour module (repo authoritative) |
| `ha/bubble_modules/apple_tile.yaml` | `/config/bubble_card/modules/apple_tile.yaml` | Apple-style tile module for `#lights` and room tiles (repo authoritative) |
| `ha/bubble_modules/segmented.yaml` | `/config/bubble_card/modules/segmented.yaml` | Segmented pill control for pop-up choices; on a `media_player` it follows `app_name` (repo authoritative) |
| `ha/bubble_modules/time_slider.yaml` | `/config/bubble_card/modules/time_slider.yaml` | Rewrites a seconds slider's drag label as m:ss / h:mm:ss (repo authoritative) |
| `ha/bubble_modules/progress_fill.yaml` | `/config/bubble_card/modules/progress_fill.yaml` | Progress-bar background for Happening now cards (repo authoritative) |
| `scripts/dashboard_preview.py` | — (runs on the Mac) | WebKit iPhone-size screenshots of any view or pop-up as the non-admin Dashboard Preview user, for tuning; setup and options in its docstring |
| `ha/bubble_modules/metric_tile.yaml` | `/config/bubble_card/modules/metric_tile.yaml` | Compact value-over-label tile for the `#weather` grid (repo authoritative) |
| `ha/packages/weather_forecast.yaml` | `/config/packages/weather_forecast.yaml` | `sensor.outside_forecast`: 24-hour hourly forecast, today's high and low, rain timing for `#weather`; `template.reload` after a change (repo authoritative) |
| `ha/themes/home_flat.yaml` | `/config/themes/home_flat.yaml` | Dashboard theme; `frontend.reload_themes` after a change (repo authoritative) |
| `ha/packages/media_activity.yaml` | `/config/packages/media_activity.yaml` | HomePod and Apple TV "recently active" sensors for room media cards and the Media chip, and each Apple TV's last-played app (repo authoritative) |
| `ha/www/media_art/*.svg` | `/config/www/media_art/` | Fallback artwork for the favourite Apple TV apps (YouTube, TV, Disney+, Prime Video) in the remote pop-ups (repo authoritative) |
| `ha/packages/media_info.yaml` | `/config/packages/media_info.yaml` | Apple TV now-playing details from the iTunes lookup, plus cast, tagline, score, background art and series posters from TMDB (repo authoritative) |
| `ha/packages/media_seek.yaml` | `/config/packages/media_seek.yaml` | Apple TV playback-position numbers behind the remote pop-ups' timeline sliders (repo authoritative) |

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
- **A media card is tall, cropped, or shows its controls on two rows:** a YAMP update changed
  a class the card's CSS targets. Inspect the card's shadow DOM and update the selectors in the
  override table under *Room media cards* (Step 3).
- **Chip strip clipped at the top or floating with a gap:** a row is wrapping. See
  `LESSONS.md` → *Bubble `sub-buttons` cards anchor their rows to the bottom*.
