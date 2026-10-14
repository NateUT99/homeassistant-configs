# AI Insights

*Last updated: October 2026*

---

## Overview

Claude writes three pieces of text for the `home-main` dashboard, all on Claude Haiku
(`ai_task.claude_haiku_ai_task`). A **weather briefing** three times a day covers what is
left of today: its headline sits in the greeting, its tip in the `#weather` pop-up. A
**Climate insight** and an **Energy insight** run every morning and say what in yesterday's
data (and, on Sundays, the past week's) is worth a look; they show as the AI Insight card on
the Climate and Energy views, with an amber navbar badge until reviewed. Fixed rules in Jinja
decide whether an insight has anything to say; Claude is called only when they flag
something, and writes the explanation. Scripts build an allowlist of facts, call
`ai_task.generate_data` with a typed `structure`, and fire a `*_ready` event that
trigger-based template sensors store. The dashboard only reads those sensors.

---

## Architecture

```
AI Insights Schedule ──06:30/12:00/17:00──▶ script.household_ai_briefing
  (automation)        ──07:00 daily───────▶ script.household_ai_climate_insight
                                            script.household_ai_energy_insight
                                                   │
  facts (ha/custom_templates/ai_insights.jinja)    │
    weather_facts()   ← hourly forecast for the rest of today, yesterday's high
    climate_insight() ← 36 days of room, HVAC, outdoor and occupancy statistics
    energy_insight()  ← 36 days of electricity, refrigerator, HVAC, occupancy
                        └─▶ {"flags": [...], "facts": "..."}
                                                   │
                     no flags ──▶ "Nothing notable" (no Claude call)
                     flags ─────▶ ai_task.generate_data (+ the week's earlier notes)
                                                   │
                         event household_ai_*_ready
                                                   │
           ha/packages/ai_insights.yaml (trigger-based sensors, 7-day history)
                                                   │
  home-main: greeting + #weather (briefing) · AI Insight cards (Climate, Energy)
             · amber navbar badge until ✓ presses input_button.household_ai_*_seen
```

**Design decisions:**

- **Claude only where it adds something.** The model turns a lot of numbers into a short
  story: a day of hourly forecast, five weeks of room and consumption statistics. Exact
  current status (doors, chores, appliances) already lives on the chips and badges, so no
  AI text restates it.
- **Jinja decides what is notable; Claude writes.** Thresholds in the macros raise the
  flags, so a badge follows a rule you can check in a trace, not the model's opinion, and a
  quiet day costs nothing. Claude gets the flags plus the surrounding facts as context.
- **Each insight sees only its own data.** A narrow prompt and short facts keep the model on
  one job, and each note sits beside the graphs it describes.
- **Jinja does the arithmetic.** Highs and lows with their times, rain windows, degree days,
  expected runtimes and every comparison ("47% less", "about the same" within 10%, "about 3
  times as much" from doubling up, "none" for a drop to zero) are computed before the call.
  A model left to compare raw numbers will sometimes reverse a direction.
- **Weather against degree days.** HVAC runtime is compared with what recent home days'
  hours per degree day predict for the weather, so a hot week's long AC runs read as
  expected and only runtime beyond the weather flags.
- **Occupancy-aware baselines.** `sensor.household_occupied_today` splits days into home,
  partial and away; only home days set baselines or raise flags, so time away neither drags
  "typical" down nor makes a return day's catch-up heating look like a fault.
- **The briefing stays inside today.** It is read as "what's today like", so the facts carry
  only the hours left in today and no tomorrow figures. The daily forecast line is left out
  because today's rain chance still counts hours already past.
- **Haiku is enough.** On the same facts Haiku 5.5 matches Sonnet 5.5 on timings and
  comparisons at a twentieth of the price, and effort `medium` buys the judgment calls. The
  AI task has a version-free entity ID, so a model upgrade is a settings change, not a script
  edit.
- **Typed output, enforced twice.** `structure:` asks for named fields; the store step also
  truncates every field and checks the icon against an allowed list.

---

## Prerequisites

- Anthropic integration with an AI Task subentry on `claude-haiku-5-5` (**Claude Haiku AI
  Task**, `ai_task.claude_haiku_ai_task`; thinking effort `medium`, prompt caching off since
  calls are hours apart, max tokens 3000; web search, web fetch, code execution and user
  location off). **Claude Sonnet AI Task** (`ai_task.claude_sonnet_ai_task`,
  `claude-sonnet-5-5`, same settings) is a fallback no script calls: swap the `entity_id` in a
  script to use it
- `/config/packages/` included from `configuration.yaml` (see `guides/vacuum_cleaning_routine.md`)
- `weather.outside_waterville_oh_usa`, `sensor.outside_temperature` (long-term statistics),
  the room climate sensors and thermostat (see `guides/hvac_monitoring.md`), the Eagle energy
  sensor and the refrigerator plug (see `guides/energy_monitoring.md`), and
  `sensor.household_hvac_*_runtime_today`
- `home-main` dashboard with Navbar Card ≥ 1.7 (badge `icon` support) (see `guides/home_dashboard.md`)

---

## Steps

### 1. Create the label

Create `int_ai_insights` (create with the ID as the name, then rename to **AI Insights**,
purple, `mdi:creation` — see `standards/automations.md` §3.2). It is applied to the three
scripts, the automation, the briefing and insight sensors, the occupancy sensor, and the two
seen markers.

### 2. Deploy the facts macros

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

Then call `template.reload` and `history_stats.reload`. The AI sensors read `unknown` until
their first event. **Household Occupied Today** counts hours anyone was home since midnight;
its long-term statistics (daily max) are the lasting record of home and away days.

```yaml
# Stores the Claude-generated text shown on the home-main dashboard: the
# weather briefing (headline in the greeting, tip in #weather) and the Climate
# and Energy insights (the AI Insight card on each view). Generation lives in
# script.household_ai_briefing / _climate_insight / _energy_insight, which
# fire one of the *_ready events below; these trigger-based sensors only store
# the result, so the dashboard never calls Claude itself. Trigger-based
# template sensors restore their last value across restarts, and a failed
# generation fires no event, so the previous text simply stays (the cards show
# its age). See guides/ai_insights.md.
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
          generated_at: "{{ now().isoformat() }}"

  # Section insights (issue #18): one sensor per section, written by
  # script.household_ai_climate_insight / _energy_insight. The state is the
  # latest headline, or "Nothing notable" on a day the fixed rules in
  # ai_insights.jinja flagged nothing. `history` keeps the flagged entries of
  # the last 7 days, newest first (a re-run replaces that day's entry); the
  # scripts send it back to Claude so a continuing item reads as continuing.
  # Each entry's `at` is compared with input_button.household_ai_*_seen to
  # show the amber navbar badge until the note is reviewed.
  - trigger:
      - trigger: event
        event_type: household_ai_climate_insight_ready
        alias: A new climate insight was generated
    sensor:
      - name: Household AI Climate Insight
        unique_id: household_ai_climate_insight
        icon: mdi:home-thermometer
        state: &insight_state >-
          {{ (trigger.event.data.headline | default('') | string)[:250]
             if trigger.event.data.flagged | default(false) else 'Nothing notable' }}
        attributes: &insight_attributes
          story: "{{ trigger.event.data.story | default('') if trigger.event.data.flagged | default(false) else '' }}"
          flagged: "{{ trigger.event.data.flagged | default(false) }}"
          flags: "{{ trigger.event.data.flags | default([]) }}"
          weekly: "{{ trigger.event.data.weekly | default(false) }}"
          date: "{{ trigger.event.data.date | default('') }}"
          history: >-
            {% set d = trigger.event.data %}
            {% set old = this.attributes.history | default([]) if this is defined and this.attributes is defined else [] %}
            {% set cutoff = (now() - timedelta(days=7)).date() | string %}
            {% set new = [{'date': d.date, 'at': now().isoformat(), 'headline': (d.headline | default('') | string)[:80], 'story': (d.story | default('') | string)[:320]}] if d.flagged | default(false) else [] %}
            {{ new + (old | selectattr('date', '>', cutoff) | rejectattr('date', 'eq', d.date) | list) }}
          generated_at: "{{ now().isoformat() }}"

  - trigger:
      - trigger: event
        event_type: household_ai_energy_insight_ready
        alias: A new energy insight was generated
    sensor:
      - name: Household AI Energy Insight
        unique_id: household_ai_energy_insight
        icon: mdi:lightning-bolt
        state: *insight_state
        attributes: *insight_attributes

sensor:
  # Hours anyone was home today, reset at midnight. Its long-term statistics
  # (daily max) let the Climate and Energy insights tell home days from away
  # days, so baselines compare like with like and a return day's catch-up
  # HVAC runtime never raises a flag. Raw history only lasts 10 days, so
  # this sensor is the only lasting record of occupancy. See issue #18.
  - platform: history_stats
    name: Household Occupied Today
    unique_id: household_occupied_today
    entity_id: zone.home
    state: ["1", "2", "3", "4", "5", "6"]
    type: time
    start: "{{ today_at() }}"
    end: "{{ now() }}"
```

### 4. Create the scripts and the schedule

Create from the mirrors in `ha/scripts/` and `ha/automations/`:

| Script / automation | Writes | Runs |
|---|---|---|
| Household: AI Briefing (`script.household_ai_briefing`) | `headline` (≤ 90), `tip` (≤ 200), `icon` (weather list) | 06:30, 12:00, 17:00 |
| Household: AI Climate Insight (`script.household_ai_climate_insight`) | `headline` (≤ 70), `story` (≤ 300), only when flagged | 07:00; weekly pass on Sundays |
| Household: AI Energy Insight (`script.household_ai_energy_insight`) | `headline` (≤ 70), `story` (≤ 300), only when flagged | 07:00; weekly pass on Sundays |
| Household: AI Insights Schedule (`automation.household_ai_insights_schedule`) | — | Starts the scripts with `script.turn_on` (category Routines) |

All three scripts are `mode: single` with `max_exceeded: silent`. The insight scripts take a
`weekly` field and the briefing a `morning` field, for testing at any hour.

**Briefing.** The focus follows the run: today (06:30), the rest of today (12:00), this
evening (17:00); tomorrow is never mentioned. The headline gives the shape of the period; the
tip adds the practical call in a friend's voice (what to wear, when to go out) and never
repeats the headline. Strong words (cold snap, bundle up) are kept for frost, a 15° drop, a
heat advisory or heavy rain. A comparison with yesterday appears only at 8° or more, and only
what matters is called out: rain 30%+, gusts 25 mph+, UV 6+, AQI over 100, frost (34° or
below), feels-like 90°+. Rain timing comes only from the hourly lines, the icon is the weather
that dominates the period, and the style examples set the tone without lending their wording.

**Insights.** Each script fetches 36 days of daily statistics and renders its macro for
yesterday. With no flags it fires `flagged: false` and the sensor reads "Nothing notable".
With flags, Claude gets the flags (the news), the facts (context only), and the earlier
flagged notes of the week, so a continuing item reads as continuing. The prompt allows a
cause only when the facts support it: weather, time away, or which rooms the thermostat
follows (Living Room, Kitchen and Office by day; Avery's Room and Master Bedroom at night),
where a drifting controlled room is offered as a possible vent, door or window.

**Voice** (all prompts): a sharp, good-humored local, conversational, a light touch of wit,
never cutesy, no emoji; facts stay precise and no cause is invented.

### 5. Flag rules

Owned by `climate_insight()` and `energy_insight()`; a re-test of every threshold after a
month of heating season is tracked in issue #18.

| Rule | Flags when |
|---|---|
| HVAC (daily) | Runtime ≥ 1.5 h and ≥ 1.5× + 1 h over the prediction (hours per degree day over the trailing 28 home days × yesterday's degree days, base 65°F); needs 10+ degree days of baseline; only on a home day after a home day |
| HVAC (Sunday) | The week ≥ 3 h and ≥ 1.5× + 2 h over the prediction from the 4 weeks before (20+ degree days of baseline) |
| Room temperature | A room's offset from the house median is ≥ 2.5°F from its usual offset (trailing 14 home days); Utility Room excluded (always ~10°F warm and dry) |
| Humidity | A room's daily mean outside 40–60%; Sunday: 3+ such days in the week |
| Electricity (daily) | ≥ 1.4× and ≥ 6 kWh above the trailing 28 home days' average, on a home day |
| Electricity (Sunday) | The week's per-home-day average ≥ 1.15× the 4 weeks before and ≥ 15 kWh more over a week |
| Refrigerator (Sunday) | The week ≥ 15% and ≥ 1 kWh off the 4 weeks before, scaled to a week |

**Day types** (hours home from the occupancy sensor): home 12 h or more, partial 2–12 h (a
trip's departure or return day), away under 2 h. Days before the sensor existed count as home.

### 6. Seen markers

Create **Household AI Climate Seen** (`input_button.household_ai_climate_seen`) and
**Household AI Energy Seen** (`input_button.household_ai_energy_seen`), both
`mdi:eye-check-outline`. Each history entry carries its `at` time; the navbar badge shows
while the newest entry is newer than the button's last press.

### 7. Dashboard

See `guides/home_dashboard.md`: the greeting shows the briefing headline, `#weather` the tip,
and the Climate and Energy views an **AI Insight** card (italic note, age badge, ✓ button that
presses the seen marker, and a **History (past week)** fold-out) with the amber `mdi:creation`
navbar badge.

---

## Security Summary

| Control | Implementation |
|---|---|
| Data minimization | Only the macro allowlist is sent — never all states |
| Never sent | Coordinates, lock codes, door, garage and network state, camera images, calendars |
| Sent | Briefing: the rest of today's hourly forecast, current outdoor conditions and AQI, yesterday's high, sunset time. Climate: daily room temperature and humidity means, HVAC runtime, outdoor temperatures and degree days, hours anyone was home. Energy: daily electricity and cost, refrigerator energy, HVAC runtime, hours anyone was home |
| Model tools | The AI tasks have web search, web fetch, code execution and user location turned off |
| Abuse/cost limit | All scripts `mode: single`, run only on the schedule; the insights call Claude only on a flagged day |
| Failure | A failed call fires no event; the sensors keep the last text and the dashboard shows its age |
| Credential | The Anthropic API key lives in the integration's config entry, not in this repo |
| Worst case | A leaked key exposes only API spend; the facts sent are weather and household totals |

Cost: Claude Haiku 5.5 — three briefing calls a day plus an insight call only on a flagged
day; well under 10¢ a month.

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Household AI Briefing | `sensor.household_ai_briefing` | Trigger-based template sensor (package) |
| Household AI Climate Insight | `sensor.household_ai_climate_insight` | Trigger-based template sensor with 7-day `history` (package) |
| Household AI Energy Insight | `sensor.household_ai_energy_insight` | Trigger-based template sensor with 7-day `history` (package) |
| Household Occupied Today | `sensor.household_occupied_today` | `history_stats` hours home since midnight (package) |
| Household: AI Briefing | `script.household_ai_briefing` | Script |
| Household: AI Climate Insight | `script.household_ai_climate_insight` | Script |
| Household: AI Energy Insight | `script.household_ai_energy_insight` | Script |
| Household: AI Insights Schedule | `automation.household_ai_insights_schedule` | Automation |
| Household AI Climate Seen | `input_button.household_ai_climate_seen` | Helper |
| Household AI Energy Seen | `input_button.household_ai_energy_seen` | Helper |
| Claude Haiku AI Task | `ai_task.claude_haiku_ai_task` | AI Task (Anthropic) |
| Claude Sonnet AI Task | `ai_task.claude_sonnet_ai_task` | AI Task (Anthropic), unused fallback |
| AI Insights | `int_ai_insights` | Label |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/packages/ai_insights.yaml` | `/config/packages/ai_insights.yaml` | Result-storing sensors, occupancy sensor |
| `ha/custom_templates/ai_insights.jinja` | `/config/custom_templates/ai_insights.jinja` | `weather_facts()`, `vs()`, `climate_insight()`, `energy_insight()`: the allowlist facts and the flag rules |

---

## Related Documents

- `guides/home_dashboard.md` — where the text is shown
- `standards/dashboards.md` §11 — conventions for AI-generated content on dashboards
- `guides/hvac_monitoring.md`, `guides/energy_monitoring.md` — sources of the facts

---

## Troubleshooting

- **A sensor stays `unknown` or stale:** open the script's trace. A failure at the
  `ai_task.generate_data` step (API error, timeout) stops the run before the event, by
  design. Calls take 10–25 s.
- **The text states something false:** check the rendered facts in the script trace (the
  `facts` or `insight` variable) first — wrong output is almost always an ambiguous or
  missing fact, or a comparison left for the model to work out. Fix it in the macro rather
  than the prompt.
- **An insight flags too often or never:** backtest the macro over past days with its
  `days_ago` argument (`{{ climate_insight(stats, 23) }}` for 23 days ago) against a
  `recorder.get_statistics` response, and tune the threshold in the macro.
