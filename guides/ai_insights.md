# AI Insights

*Last updated: October 2026*

---

## Overview

Claude writes two pieces of text for the `home-main` dashboard: a **briefing** three times
a day (the headline shows under the chip strip) and a Sunday **weekly digest** on energy and
HVAC use. Every briefing covers the weather ahead; the morning one also looks back, with a
house recap of overnight and yesterday and what the house needs today. Both run on Claude Sonnet (`ai_task.claude_sonnet_ai_task`).
Scripts gather an explicit allowlist of facts, call `ai_task.generate_data` with a typed
`structure`, and fire a `*_ready` event; trigger-based template sensors in a package store
the result. The dashboard only reads those sensors — it never calls Claude.

---

## Architecture

```
AI Insights Schedule ──06:30/12:00/17:00──▶ script.household_ai_briefing ──────┐
  (automation)        ──Sun 18:00─────────▶ script.household_ai_weekly_digest ─┤
#ai Refresh button ───────────────────────▶ script.household_ai_briefing       │
                                                                              │
   facts: weather_facts()  ← weather.get_forecasts, yesterday's statistics    │
          house_facts()    ← overnight counters, 8 days of statistics,        │
                             laundry and chores (morning only)                │
          window_total() / vs() ← 5 weeks of daily statistics                 │
          (ha/custom_templates/ai_insights.jinja)                             │
                                                                              ▼
                              ai_task.generate_data (structure: typed fields)
                                                                              │
                                   event household_ai_*_ready ◀────────────────┘
                                                                              │
                     ha/packages/ai_insights.yaml (trigger-based template sensors)
                                                                              │
             sensor.household_ai_briefing / sensor.household_ai_weekly_digest
                                                                              │
                home-main: greeting line, AI chip, #ai pop-up ◀───────────────┘
```

**Design decisions:**

- **Claude only where it adds something.** The model gets jobs that turn a lot of numbers
  into a short story: 24 hours of hourly forecast, five weeks of energy and runtime
  statistics, and the night's activity. Current house status (doors, chores, appliances) is
  already exact on the chips and badges, so the house recap covers what the chips can't
  show: what happened while you weren't looking, and how yesterday compared.
- **Scripts generate, a package stores.** Each script is traceable and runs on demand; the
  trigger-based sensors survive restarts and keep the last good text when a call fails,
  because a failed call fires no event.
- **The macros are the allowlist.** `weather_facts()`, `house_facts()`, `window_total()`, and `vs()` in
  `ha/custom_templates/ai_insights.jinja` build everything sent. Anything not in them is
  never sent, and the file is the single place to review or extend.
- **Jinja does the arithmetic, Claude writes.** Highs and lows with their times, rain
  windows (30% or more), the gap to yesterday, weekly totals, degree days, and every
  comparison ("47% less", "about the same", within 10%) are computed before the call. A
  model left to compare raw numbers will sometimes reverse a direction.
- **Degree days explain HVAC.** Heating and cooling degree days (base 65°F, from the daily
  mean outdoor temperature) say how much the weather called for, so the digest can tell a
  colder week from the furnace running more than the weather explains.
- **Typed output, enforced twice.** `structure:` asks for named fields; the store step
  also truncates every field and checks the icon against an allowed list, so a model that
  ignores the limits can't break a card.
- **Sonnet over Haiku.** Compared on the same forecast and prompt, Sonnet got timings right
  where Haiku guessed, for about 80¢ a month more (three short calls a day and one a week).

---

## Prerequisites

- Anthropic integration with an AI Task subentry on `claude-sonnet-5` (**Claude Sonnet AI
  Task**, `ai_task.claude_sonnet_ai_task`; web search, web fetch, code execution and user
  location off)
- `/config/packages/` included from `configuration.yaml` (see `guides/vacuum_cleaning_routine.md`)
- `weather.outside_waterville_oh_usa`, `sensor.outside_temperature` (long-term statistics),
  the Chore Calendar integration, the Eagle energy sensor, the refrigerator plug, and
  `sensor.household_hvac_*_runtime_today` (see their guides)
- `home-main` dashboard (see `guides/home_dashboard.md`)

---

## Steps

### 1. Create the label

Create `int_ai_insights` (create with the ID as the name, then rename to **AI Insights**,
purple, `mdi:creation` — see `standards/automations.md` §3.2). It is applied to the two
scripts, the automation, the two AI sensors, and `input_button.household_ai_seen`.

### 2. Deploy the facts macro

```bash
scp ha/custom_templates/ai_insights.jinja ha:/config/custom_templates/ai_insights.jinja
```

Then call `homeassistant.reload_custom_templates`. Check it in **Developer Tools → Template**:

```jinja
{% from 'ai_insights.jinja' import weather_facts, vs %}{{ weather_facts([], []) }} / {{ vs(9, 10) }}
```

### 3. Deploy the package

```bash
scp ha/packages/ai_insights.yaml ha:/config/packages/ai_insights.yaml
```

Then call `template.reload` and `history_stats.reload`. The two AI sensors read `unknown`
until their first event. Two `history_stats` counters count how many times each daily
vacuum "ran" flag turned on since Monday 08:05 (the flags reset at 08:00, so a start any
earlier would count Sunday night's still-on flag as a Monday run). Four more count door
openings, garage openings, internet drops, and generator runs since the most recent 10 PM,
for the morning recap.

```yaml
# Stores the Claude-generated text shown on the home-main dashboard: the
# briefing (weather, plus a house recap in the morning) and the weekly digest. Generation lives in
# script.household_ai_briefing / _weekly_digest, which call
# ai_task.generate_data and then fire one of the *_ready events below; these
# trigger-based sensors only store the result, so the dashboard never calls
# Claude itself. Trigger-based template sensors restore their last value across
# restarts, and a failed generation fires no event, so the previous text simply
# stays (the cards show its age). See guides/ai_insights.md.
#
# Deployed to /config/packages/ai_insights.yaml; reload with template.reload and
# history_stats.reload.

template:
  - trigger:
      - trigger: event
        event_type: household_ai_briefing_ready
        alias: A new briefing was generated
    sensor:
      - name: Household AI Briefing
        unique_id: household_ai_briefing
        # State holds the short headline (state is capped at 255 characters).
        state: "{{ (trigger.event.data.headline | default('') | string)[:250] }}"
        icon: "{{ trigger.event.data.icon | default('mdi:creation') }}"
        attributes:
          tip: "{{ trigger.event.data.tip | default('') }}"
          # Only the morning run writes the house recap; later runs keep it, so
          # it reads as "this morning's" until the next morning.
          house: >-
            {{ trigger.event.data.house if trigger.event.data.house | default('') != ''
               else (this.attributes.house | default('') if this is defined and this.attributes is defined else '') }}
          generated_at: "{{ now().isoformat() }}"

  - trigger:
      - trigger: event
        event_type: household_ai_weekly_digest_ready
        alias: A new weekly digest was generated
    sensor:
      - name: Household AI Weekly Digest
        unique_id: household_ai_weekly_digest
        state: "Week of {{ (now() - timedelta(days=6)).strftime('%b %-d') }}"
        icon: mdi:calendar-week
        # The numbers are computed by the script from statistics, not written by
        # Claude, so they are exact; Claude writes only the headline and the story.
        attributes:
          headline: "{{ trigger.event.data.headline | default('') }}"
          story: "{{ trigger.event.data.story | default('') }}"
          energy_kwh: "{{ trigger.event.data.energy_kwh | default(0) }}"
          energy_prev_kwh: "{{ trigger.event.data.energy_prev_kwh | default(0) }}"
          energy_avg_kwh: "{{ trigger.event.data.energy_avg_kwh | default(0) }}"
          energy_cost: "{{ trigger.event.data.energy_cost | default(0) }}"
          heating_h: "{{ trigger.event.data.heating_h | default(0) }}"
          heating_prev_h: "{{ trigger.event.data.heating_prev_h | default(0) }}"
          cooling_h: "{{ trigger.event.data.cooling_h | default(0) }}"
          cooling_prev_h: "{{ trigger.event.data.cooling_prev_h | default(0) }}"
          hdd: "{{ trigger.event.data.hdd | default(0) }}"
          hdd_prev: "{{ trigger.event.data.hdd_prev | default(0) }}"
          cdd: "{{ trigger.event.data.cdd | default(0) }}"
          cdd_prev: "{{ trigger.event.data.cdd_prev | default(0) }}"
          fridge_kwh: "{{ trigger.event.data.fridge_kwh | default(0) }}"
          fridge_avg_kwh: "{{ trigger.event.data.fridge_avg_kwh | default(0) }}"
          vacuum_day_runs: "{{ trigger.event.data.vacuum_day_runs | default(0) }}"
          vacuum_night_runs: "{{ trigger.event.data.vacuum_night_runs | default(0) }}"
          mop_common_done: "{{ trigger.event.data.mop_common_done | default(false) }}"
          mop_master_done: "{{ trigger.event.data.mop_master_done | default(false) }}"
          chores_done: "{{ trigger.event.data.chores_done | default([]) }}"
          chores_overdue: "{{ trigger.event.data.chores_overdue | default([]) }}"
          generated_at: "{{ now().isoformat() }}"

# Weekly vacuum coverage: how many times each daily "ran" flag turned on this
# week. Both flags reset at 08:00 daily (see guides/vacuum_cleaning_routine.md),
# so the week starts Monday 08:05: an earlier start would catch Sunday night's
# still-on flag (it clears a fraction of a second after 08:00) as a Monday run.
sensor:
  - platform: history_stats
    name: Household Vacuum Day Runs This Week
    unique_id: household_vacuum_day_runs_this_week
    entity_id: input_boolean.vacuum_ran_daytime
    state: "on"
    type: count
    start: >-
      {% set s = today_at('08:05') - timedelta(days=now().weekday()) %}
      {{ s if s <= now() else s - timedelta(days=7) }}
    end: "{{ now() }}"
  - platform: history_stats
    name: Household Vacuum Night Runs This Week
    unique_id: household_vacuum_night_runs_this_week
    entity_id: input_boolean.vacuum_ran_evening
    state: "on"
    type: count
    start: >-
      {% set s = today_at('08:05') - timedelta(days=now().weekday()) %}
      {{ s if s <= now() else s - timedelta(days=7) }}
    end: "{{ now() }}"

  # Overnight activity for the morning briefing's house recap: counts since the
  # most recent 10 PM. history_stats counts transitions into the state, so a
  # door left open all night counts once.
  - platform: history_stats
    name: Household Doors Opened Overnight
    unique_id: household_doors_opened_overnight
    entity_id: binary_sensor.household_exterior_doors_open
    state: "on"
    type: count
    start: &overnight >-
      {{ today_at('22:00') - timedelta(days=1) if now() < today_at('22:00') else today_at('22:00') }}
    end: "{{ now() }}"
  - platform: history_stats
    name: Household Garage Opened Overnight
    unique_id: household_garage_opened_overnight
    entity_id: cover.garage_door_opener_door
    state: "open"
    type: count
    start: *overnight
    end: "{{ now() }}"
  - platform: history_stats
    name: Household Internet Drops Overnight
    unique_id: household_internet_drops_overnight
    entity_id: binary_sensor.utility_room_firewalla_gold_se_wan_buckeye_broadband_status
    state: "off"
    type: count
    start: *overnight
    end: "{{ now() }}"
  - platform: history_stats
    name: Household Generator Runs Overnight
    unique_id: household_generator_runs_overnight
    entity_id: sensor.outside_home_generator_status
    state: "Running"
    type: count
    start: *overnight
    end: "{{ now() }}"
```

### 4. Create the scripts and the schedule

Create from the mirrors in `ha/scripts/` and `ha/automations/`:

| Script / automation | Fields generated | Runs |
|---|---|---|
| Household: AI Briefing (`script.household_ai_briefing`) | `headline` (≤ 90), `tip` (≤ 200), `icon` (weather list); mornings also `house` (≤ 200) | Schedule; Refresh button in `#ai` |
| Household: AI Weekly Digest (`script.household_ai_weekly_digest`) | `headline` (≤ 70), `story` (≤ 300); the figures are computed by the script | Sundays 18:00 |
| Household: AI Insights Schedule (`automation.household_ai_insights_schedule`) | — | 06:30, 12:00, 17:00 briefing; Sun 18:00 digest (category Routines) |

Both scripts are `mode: single` with `max_exceeded: silent`. The schedule starts them with
`script.turn_on` so a slow API call never holds the automation.

**Briefing.** The focus follows the time of day: before 11:00 it covers today, before 16:00
the rest of today and tonight, otherwise tonight and tomorrow. The headline gives the shape
of that period (a cold start that turns warm, when rain comes and goes); the tip adds what
the headline left out and what it means in practice. The tip is the practical call in a friend's voice (what to
wear, when to go out). Its drama stays in proportion to the season: strong words (cold snap,
bundle up) are reserved for frost, a 15° drop, a heat advisory, or heavy rain. A temperature comparison appears only when the gap is 8° or more and
fits the period (today vs yesterday, or tomorrow vs today in the evening), and calls out only what matters: rain 30%+, gusts 25 mph+, UV 6+, AQI over
100, frost (34° or below), feels-like 90°+.

**Morning house recap.** Runs before 11:00 (or with the script's `morning: true` field, for
testing). It looks back first (doors and garage opened since 10 PM and the last door time,
internet drops, generator runs, leaks, yesterday's electricity and heating/cooling against a
typical day of the past week, laundry left waiting, and, before 08:00 when the flags reset,
whether the vacuum ran), then ahead (chores due today or overdue). The headline picks the
single most useful item from the weather or the house. The sensor keeps the recap through the
midday and evening runs, so `#ai` shows it as "This morning" until the next morning.

**Digest.** "This week" is the 7 days ending now, "last week" the 7 before, and the average
the 28 days before this week, scaled to 7 days by how many days have data (so a sensor
younger than five weeks still averages fairly). The story leads with the most notable of:
electricity against last week and the average; heating and cooling hours against degree
days; the refrigerator, only when 15% off its average; vacuuming and chores only when
clearly missed.

**Voice** (both prompts): a sharp, good-humored local — conversational, a light touch of wit,
never cutesy, no emoji; facts stay precise and no cause is invented.

### 5. Seen marker

Create **Household AI Seen** (`input_button.household_ai_seen`, `mdi:eye-check-outline`).
The `#ai` pop-up presses it on open and on close; the AI chip is amber while the digest's
`generated_at` is newer than the last press.

### 6. Dashboard

See `guides/home_dashboard.md`: the greeting markdown card shows the briefing headline, the
AI chip opens `#ai`, and `#ai` holds the briefing with its morning house recap (and a
Refresh button) and the digest.

---

## Security Summary

| Control | Implementation |
|---|---|
| Data minimization | Only the macro allowlist is sent — never all states |
| Never sent | Coordinates, lock codes, network/Firewalla details, camera images, calendars, house status |
| Sent | Briefing: the forecast, current outdoor conditions and AQI, yesterday's outdoor high and low, sunset time. Morning recap: overnight counts of door and garage openings (and the last door time), internet drops and generator runs, the front door lock and garage state, leaks, yesterday's energy and HVAC hours vs typical, laundry waiting, chore names due today. Digest: weekly energy, HVAC runtime, refrigerator and degree-day totals, vacuum counts, chore names |
| Model tools | The Sonnet AI task has web search, web fetch, code execution and user location turned off |
| Abuse/cost limit | Both scripts `mode: single`; the only on-demand trigger is the briefing Refresh button |
| Failure | A failed call fires no event; the sensors keep the last text and the dashboard shows its age |
| Credential | The Anthropic API key lives in the integration's config entry, not in this repo |
| Worst case | A leaked key exposes only API spend; the facts sent are weather and household totals |

Cost: Claude Sonnet, 3 calls a day plus one a week — around $1.30/month; the morning recap rides on the 06:30 call.

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Household AI Briefing | `sensor.household_ai_briefing` | Trigger-based template sensor (package) |
| Household AI Weekly Digest | `sensor.household_ai_weekly_digest` | Trigger-based template sensor (package) |
| Household Vacuum Day Runs This Week | `sensor.household_vacuum_day_runs_this_week` | `history_stats` count (package) |
| Household Vacuum Night Runs This Week | `sensor.household_vacuum_night_runs_this_week` | `history_stats` count (package) |
| Household Doors Opened Overnight | `sensor.household_doors_opened_overnight` | `history_stats` count since 10 PM (package) |
| Household Garage Opened Overnight | `sensor.household_garage_opened_overnight` | `history_stats` count since 10 PM (package) |
| Household Internet Drops Overnight | `sensor.household_internet_drops_overnight` | `history_stats` count since 10 PM (package) |
| Household Generator Runs Overnight | `sensor.household_generator_runs_overnight` | `history_stats` count since 10 PM (package) |
| Household: AI Briefing | `script.household_ai_briefing` | Script |
| Household: AI Weekly Digest | `script.household_ai_weekly_digest` | Script |
| Household: AI Insights Schedule | `automation.household_ai_insights_schedule` | Automation |
| Household AI Seen | `input_button.household_ai_seen` | Helper |
| Claude Sonnet AI Task | `ai_task.claude_sonnet_ai_task` | AI Task (Anthropic) |
| AI Insights | `int_ai_insights` | Label |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/packages/ai_insights.yaml` | `/config/packages/ai_insights.yaml` | Result-storing sensors, weekly vacuum and overnight counters |
| `ha/custom_templates/ai_insights.jinja` | `/config/custom_templates/ai_insights.jinja` | `weather_facts()`, `house_facts()`, `window_total()`, `vs()` allowlist macros |

---

## Related Documents

- `guides/home_dashboard.md` — where the text is shown
- `standards/dashboards.md` §11 — conventions for AI-generated content on dashboards
- `guides/reminders.md`, `guides/vacuum_cleaning_routine.md`, `guides/energy_monitoring.md`,
  `guides/hvac_monitoring.md` — sources of the facts

---

## Troubleshooting

- **A sensor stays `unknown` or stale:** open the script's trace. A failure at the
  `ai_task.generate_data` step (API error, timeout) stops the run before the event, by
  design. Calls take 10–25 s.
- **The text states something false:** check the rendered facts in the script trace
  (the `facts` variable, or the digest's instructions) first — wrong output is almost always
  an ambiguous or missing fact, or a comparison left for the model to work out. Fix it in
  the macro rather than the prompt.
