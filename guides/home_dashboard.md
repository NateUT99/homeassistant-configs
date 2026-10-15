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
- **Media lives in the room it plays in.** Each room section on Home carries a Bubble
  `media-player` card for its Apple TV or HomePod, shown only while that player is in use, with
  no house-wide player card. It is the two-row layout with the Media Player Enhanced artwork
  background (Apple TV cards drop the timeline with `progress_bar: none`, since live TV has none and it lives in the remote pop-up; HomePod cards keep it) and playback controls only: play/pause, plus previous/next on HomePods (an Apple
  TV's skip keys mean nothing to most video apps). Tapping an Apple TV card opens its remote pop-up (Living Room, Master
  Bedroom) or `#media` (Family Room); HomePod cards don't respond to taps and show Bubble's own
  volume button beside play/pause (it drives the HomePod itself, which is why the Apple TV
  cards hide it: there it would change the Apple TV's volume, not the speaker's). Bubble's
  media-player `tap_action` fires only on the icon, which these cards hide, so the navigation
  is set in `button_action`.
- **The Living Room Apple TV has its own remote pop-up.** `#living-room-remote` is the one
  destination for that player: tapping its card on Home, in `#media`, or in `#living-room` opens
  it. It is a separate pop-up rather than a collapsible section in the room pop-up, because
  Expander Card can't be opened from a link and remembers its last state per device, so a
  link could land on a collapsed remote. The remote is Universal Remote Card (HACS), the only
  card besides YAMP that isn't Bubble: it sends the Apple TV `remote.send_command` keys natively, gives
  haptics, and has a swipe touchpad that Bubble has no equivalent for.
- **Media cards by place.** Home uses the two-row Bubble cards above. The remote pop-ups lead
  with a full-height Yet Another Media Player card (artwork first). `#media` uses YAMP
  cards, square for Apple TVs and compact for HomePods. The room pop-ups'
  HomePod and Family Room cards keep the large Bubble Media Player Enhanced layout (`rows: 3`,
  scrubbable progress bar, `background_opacity: 0.85`, `idle_artwork: none`, Bubble's icon
  hidden since the module draws the cover; Apple TV cards use `artwork_fit: original`); the
  Living Room and Master Bedroom pop-ups reuse the Home card, since their remotes hold the rest.
- **Media cards follow an "active" template sensor per player**
  (`ha/packages/media_activity.yaml`), and so does the Media chip's count. Apple TVs are
  active while playing or paused (a paused show is one you'll come back to) plus 30 seconds,
  because moving around the Apple TV interface drops it to `idle` for under a second at a
  time, which would otherwise hide and re-show the card. HomePods are active while playing
  plus 10 minutes: a HomePod usually drops from `paused` to `idle` on its own 8 minutes after
  playing, but an app that parks a track on it without playing (`idle` → `paused`, seen with
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
get a full-width card, poster-shaped (`card_height` 535, a 2:3 card the poster fills exactly) when Apple's poster is available and square (340) otherwise, artwork first, with play/pause, the volume stepper, a dimmed progress-bar track, the same details line as the remotes plus the description (truncated to 220 characters), and volume on
the real speaker (Soundbar, bedroom TV, Theater) and the favourite-app fallback artwork; tapping
one opens its remote pop-up (a hidden YAMP navigate action on `card_trigger: tap`; Family Room
has no remote yet). HomePods get a compact card (`always_collapsed`: title, previous/play/next and
volume beside a small artwork tile). The Master Bedroom HomePod's heading shows only when the
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


The navbar's Rooms tab (`#rooms`) stays as the at-a-glance view of every room.

**Media activity package** — `ha/packages/media_activity.yaml`, deployed to
`/config/packages/media_activity.yaml`, reload with `template.reload`. HA derives
`binary_sensor.*_apple_tv_active` from the "Apple TV" names; rename the three to
`*_appletv_active` after the first reload so they match the media player IDs the dashboard
uses:

```yaml
# "Recently active" flags for the HomePods and Apple TVs, used to show a room's media card
# on the home-main dashboard and to count it in the Media chip.
#
# HomePods: on while playing, held on for 10 minutes after it stops (delay_off). A HomePod
# usually drops from paused to idle by itself after 8 minutes, but not when an app parks a
# track on it without playing (idle -> paused directly), which can sit paused indefinitely
# -- so the card can't rely on "paused".
#
# Apple TVs: on while playing or paused (a paused show is one you'll come back to), held on
# for 30 seconds. Moving around the Apple TV interface drops it to idle for under a second
# at a time, which would otherwise hide and re-show the card. See guides/home_dashboard.md.
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
      - name: Living Room Apple TV Active
        unique_id: living_room_appletv_active
        state: "{{ is_state('media_player.living_room_appletv', ['playing', 'paused']) }}"
        delay_off: "00:00:30"
      - name: Family Room Apple TV Active
        unique_id: family_room_appletv_active
        state: "{{ is_state('media_player.family_room_appletv', ['playing', 'paused']) }}"
        delay_off: "00:00:30"
      - name: Master Bedroom Apple TV Active
        unique_id: master_bedroom_appletv_active
        state: "{{ is_state('media_player.master_bedroom_appletv', ['playing', 'paused']) }}"
        delay_off: "00:00:30"
```

**Media info package** — `ha/packages/media_info.yaml`, deployed to
`/config/packages/media_info.yaml`, reload with `template.reload` (`rest_command.reload` for the
lookup command; the first deploy needed a restart because the instance had no `rest_command`).
HA derives `sensor.*_apple_tv_info`; rename to `*_appletv_info`. The sensor's `content_id` is
stored as a number, so cards compare it with the player's ID as strings:

```yaml
# Now-playing details for the Apple TVs, from Apple's public iTunes lookup service.
#
# Content bought or rented from Apple reports its iTunes store ID as media_content_id (a plain
# number, e.g. 271991087 for The Terminator), which the lookup resolves exactly: year, content
# rating, genre, runtime, director, description and a poster. Other apps (YouTube, Disney+,
# live TV) report non-numeric IDs and get no details. The lookup runs only when the content ID
# changes (or HA starts / templates reload), not on a timer, and needs no account or key. The home-main remote pop-ups show the
# details under the timeline. See guides/home_dashboard.md.
#
# Top-level variables can't see `this`, so `changed` reads the sensor by entity ID (the
# renamed sensor.<room>_appletv_info).
#
# Deployed to /config/packages/media_info.yaml; reload with template.reload (rest_command.reload
# for the command; adding rest_command to an instance that had none needs a restart).

rest_command:
  itunes_lookup:
    url: "https://itunes.apple.com/lookup?id={{ id }}&country=us"
    method: GET
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
      changed: "{{ new_id != (state_attr('sensor.living_room_appletv_info', 'content_id') | default('', true) | string) }}"
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
    sensor:
      - name: Living Room Apple TV Info
        unique_id: living_room_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
            {{ (c.results | first | default({})).trackName | default('none') }}
          {% elif active and owned and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and owned) else '' }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
              {% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'director': r.artistName | default(''),
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb')
              } }}
            {% elif active and owned and not changed %}
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
      changed: "{{ new_id != (state_attr('sensor.master_bedroom_appletv_info', 'content_id') | default('', true) | string) }}"
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
    sensor:
      - name: Master Bedroom Apple TV Info
        unique_id: master_bedroom_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
            {{ (c.results | first | default({})).trackName | default('none') }}
          {% elif active and owned and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and owned) else '' }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
              {% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'director': r.artistName | default(''),
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb')
              } }}
            {% elif active and owned and not changed %}
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
      changed: "{{ new_id != (state_attr('sensor.family_room_appletv_info', 'content_id') | default('', true) | string) }}"
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
    sensor:
      - name: Family Room Apple TV Info
        unique_id: family_room_appletv_info
        icon: mdi:movie-open-outline
        # The title while details are available, otherwise "none" (the card hides).
        state: >
          {% if active and owned and itunes is defined and itunes.status == 200 %}
            {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
            {{ (c.results | first | default({})).trackName | default('none') }}
          {% elif active and owned and not changed %}
            {{ this.state }}
          {% else %}
            none
          {% endif %}
        attributes:
          content_id: "{{ new_id if (active and owned) else '' }}"
          details: >
            {% if active and owned and itunes is defined and itunes.status == 200 %}
              {% set c = itunes.content if itunes.content is mapping else (itunes.content | from_json) %}
              {% set r = c.results | first | default({}) %}
              {% set mins = ((r.trackTimeMillis | default(0) | int) / 60000) | round(0) | int %}
              {{ {
                'year': (r.releaseDate | default(''))[:4],
                'rating': r.contentAdvisoryRating | default(''),
                'genre': r.primaryGenreName | default(''),
                'runtime': ((mins // 60) ~ 'h ' ~ (mins % 60) ~ 'm') if mins >= 60 else ((mins ~ 'm') if mins else ''),
                'director': r.artistName | default(''),
                'description': r.longDescription | default(r.shortDescription | default('')),
                'poster': (r.artworkUrl100 | default('')) | replace('100x100bb', '1000x1000bb')
              } }}
            {% elif active and owned and not changed %}
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
| `#living-room-remote` | No header; `popup_style: home-assistant` (Bubble Card ≥ the release that added it) with no `popup_mode`, so on mobile the sheet keeps the more-info dialog's full height and doesn't resize as tabs change. A segmented switch at the top (`input_select.living_room_remote_view`: Now Playing · Apple TV (`phu:appletv-sim`) · TV; it remembers the last tab, starting on Apple TV) shows one tab at a time through card `visibility`. **Now Playing** is information only: a markdown card with Apple's 2000 px store poster, the series as a small heading for a TV episode, the title, the content rating as an outlined badge with year · genre · runtime, the director for a movie, and the full description, all from `sensor.living_room_appletv_info`. The tab is dimmed and untappable while the sensor is `none`, and if it is selected when details disappear the Apple TV tab shows instead. **Apple TV** opens with a display-only Yet Another Media Player card in its compact layout (`always_collapsed`, 100 px: an artwork tile 84 px tall whose width follows the artwork's shape (a portrait poster is 56 px wide, widescreen art is capped at 150 px), centred beside the title; YAMP sizes that tile for a compact card that also has control and volume rows, so the tile size, clearance and centring are set in UIX; Apple's series art is square and posters are 2:3, so a wide short card cut off their lower third, and the full artwork lives on Now Playing; every control, volume, timeline and menu hidden; the same artwork rule as `#media`, so an episode the Apple TV sends no artwork for still shows Apple's image), then the timeline, then a volume row for the Soundbar (mute on the left, filled while muted, via `script.household_media_toggle_mute` since a tap action can't read the current mute state; then − / level / +, ±2% a tap, the level reading "Muted" while muted), then Speech · Night · Sub, the app favourites, and the Universal Remote Card (back and play/pause, the 190 × 170 px touchpad, home and hold-to-toggle power, skip ±10 s and the focus-only keyboard). **TV** controls the LG (`media_player.living_room_tv`): input pills (Apple TV, HDMI 3, HDMI 4, Live TV; the current input is filled, via the `segmented` module reading `source`), channel presets shown as network logos (`phu:cbs` 11.1, `phu:abc` 13.1, `phu:nbc` 24.1, `phu:fox` 36.1: `media_player.play_media` with `media_content_type: channel` and the LG's `11-1` channel-number form), and a Universal Remote Card on the LG webOS platform with a 1–9 / – 0 enter number pad, channel up and down, guide, and back. Timeline: a Bubble slider on `number.living_room_appletv_position` (from `ha/packages/media_seek.yaml`; refreshed every 2 s while playing, holding a dragged value for 6 s because the Apple TV keeps reporting the pre-seek position, excluded from the recorder) that fills purple, reads e.g. "0:21:41 / 1:47:24", seeks on release, labels the drag target as m:ss through the `time_slider` module, and hides when there is no duration (live TV) |
| `#kitchen` | Sink light, dishwasher and refrigerator tiles, HomePod |
| `#family-room` | Ambient lamp, 2 pinball underglows, 3 game power switches, Apple TV player (only while active; Theater volume slider; Apps, Speech and Night sub-buttons) |
| `#office` | 7 lights, fan speed (tile `fan-speed` feature), HomePod |
| `#master-bedroom` | Ceiling light, nightstand lamp, fan speed, Apple TV card, the same as on Home (only while active; tap opens `#master-bedroom-remote`), otherwise the same compact Apple TV card as `#living-room`, HomePod, bathroom speaker |
| `#master-bedroom-remote` | `#living-room-remote` for the bedroom Apple TV, minus the Sonos sound row: YAMP's volume slider and mute drive the LG TV (`media_player.master_bedroom_tv`, which reports `unavailable` while the TV is off), and the keyboard uses the Master Bedroom AppleTV config entry |
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
| `ha/packages/media_activity.yaml` | `/config/packages/media_activity.yaml` | HomePod and Apple TV "recently active" sensors for room media cards and the Media chip (repo authoritative) |
| `ha/www/media_art/*.svg` | `/config/www/media_art/` | Fallback artwork for the favourite Apple TV apps (YouTube, TV, Disney+, Prime Video) in the remote pop-ups (repo authoritative) |
| `ha/packages/media_info.yaml` | `/config/packages/media_info.yaml` | Apple TV now-playing details and poster from the iTunes lookup (repo authoritative) |
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
- **Chip strip clipped at the top or floating with a gap:** a row is wrapping. See
  `LESSONS.md` → *Bubble `sub-buttons` cards anchor their rows to the bottom*.
