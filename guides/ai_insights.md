# AI Insights

*Last updated: October 2026*

---

## Overview

Claude (Anthropic integration, `ai_task.claude_haiku_ai_task`) writes three pieces of text for
the `home-main` dashboard: a daily **briefing** shown under the chip strip, an on-demand
**house summary**, and a Sunday **weekly digest**. Scripts gather an explicit allowlist of
house facts, call `ai_task.generate_data` with a typed `structure`, and fire a `*_ready` event;
trigger-based template sensors in a package store the result. The dashboard only reads those
sensors — it never calls Claude.

---

## Architecture

```
AI Insights Schedule ──06:30/12:00/17:00──▶ script.household_ai_briefing ─┐
  (automation)        ──Sun 18:00─────────▶ script.household_ai_weekly_digest ─┤
#ai pop-up buttons ───────────────────────▶ script.household_ai_house_summary ─┤
                                                                              │
   facts: house_facts() macro (ai_insights.jinja)  ← weather.get_forecasts    │
          weekly stats (recorder.get_statistics, chore sensors)               │
                                                                              ▼
                              ai_task.generate_data (structure: typed fields)
                                                                              │
                                   event household_ai_*_ready ◀────────────────┘
                                                                              │
                     ha/packages/ai_insights.yaml (trigger-based template sensors)
                                                                              │
          sensor.household_ai_briefing / _house_summary / _weekly_digest ◀────┘
                                                                              │
                home-main: greeting line, AI chip, #ai pop-up ◀───────────────┘
```

**Design decisions:**

- **Scripts generate, a package stores.** Each script is traceable and runs on demand; the
  trigger-based sensors survive restarts and keep the last good text when a call fails,
  because a failed call fires no event.
- **One allowlist macro.** `house_facts()` in `ha/custom_templates/ai_insights.jinja` is the
  only thing the briefing and summary send. Anything not in it is never sent, and the macro
  is the single place to review or extend.
- **Typed output, enforced twice.** `structure:` asks for named fields (the house summary's
  two lists are `text` selectors with `multiple: true`); the store step also truncates
  every field and caps list lengths, and checks the icon against an allowed list, so a
  model that ignores the limits can't break a card.
- **Claude writes words, not numbers.** The weekly digest's figures come from
  `recorder.get_statistics`, the vacuum counters, and the mop flags, computed in the
  script and stored as attributes; Claude writes only the one-line headline. Numbers a
  model restates can drift; numbers the dashboard renders directly cannot.
- **The briefing stays true for hours.** It refreshes three times a day, so its prompt
  forbids anything that changes minute to minute (appliances running, open doors, who is
  home). Live status belongs to the chips and the house summary.
- **Facts name what they mean.** "People physically home" is the presence count;
  "Avery's scheduled days with us" is schedule only. An ambiguous label invites the model to
  infer something false, so labels say exactly what they measure and the prompts forbid
  connecting unrelated facts.

---

## Prerequisites

- Anthropic integration with an AI Task subentry (`ai_task.claude_haiku_ai_task`, Claude Haiku)
- `/config/packages/` included from `configuration.yaml` (see `guides/vacuum_cleaning_routine.md`)
- `weather.outside_waterville_oh_usa`, the Chore Calendar integration, the Eagle energy sensor,
  and `sensor.household_hvac_*_runtime_today` (see their guides)
- `home-main` dashboard (see `guides/home_dashboard.md`)

---

## Steps

### 1. Create the label

Create `int_ai_insights` (create with the ID as the name, then rename to **AI Insights**,
purple, `mdi:creation` — see `standards/automations.md` §3.2). It is applied to the three
scripts, the automation, and the three sensors.

### 2. Deploy the facts macro

```bash
scp ha/custom_templates/ai_insights.jinja ha:/config/custom_templates/ai_insights.jinja
```

Then call `homeassistant.reload_custom_templates`. Check it in **Developer Tools → Template**:

```jinja
{% from 'ai_insights.jinja' import house_facts %}{{ house_facts([], []) }}
```

### 3. Deploy the package

```bash
scp ha/packages/ai_insights.yaml ha:/config/packages/ai_insights.yaml
```

Then call `template.reload` and `history_stats.reload`. The three AI sensors read `unknown`
until their first event. The two `history_stats` counters count how many times each daily
vacuum "ran" flag turned on since Monday 08:05. The flags reset at 08:00, so a start any
earlier would count Sunday night's still-on flag as a Monday run.

```yaml
# Stores the Claude-generated text shown on the home-main dashboard: the daily
# briefing, the on-demand house summary, and the weekly digest. Generation lives
# in script.household_ai_briefing / _house_summary / _weekly_digest, which call
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
          generated_at: "{{ now().isoformat() }}"

  - trigger:
      - trigger: event
        event_type: household_ai_house_summary_ready
        alias: A new house summary was generated
    sensor:
      - name: Household AI House Summary
        unique_id: household_ai_house_summary
        # State is a short status the dashboard gates on; the items live in list
        # attributes so the pop-up can render them as two lists.
        state: "{{ 'attention' if trigger.event.data.attention_items | default([]) | count > 0 else 'ok' }}"
        icon: "{{ 'mdi:alert-circle-outline' if trigger.event.data.attention_items | default([]) | count > 0 else 'mdi:check-circle-outline' }}"
        attributes:
          attention_items: "{{ trigger.event.data.attention_items | default([]) }}"
          ok_items: "{{ trigger.event.data.ok_items | default([]) }}"
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
        # Claude, so they are exact; Claude only writes the one-line headline.
        attributes:
          headline: "{{ trigger.event.data.headline | default('') }}"
          energy_kwh: "{{ trigger.event.data.energy_kwh | default(0) }}"
          energy_prev_kwh: "{{ trigger.event.data.energy_prev_kwh | default(0) }}"
          energy_cost: "{{ trigger.event.data.energy_cost | default(0) }}"
          heating_h: "{{ trigger.event.data.heating_h | default(0) }}"
          cooling_h: "{{ trigger.event.data.cooling_h | default(0) }}"
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
```

### 4. Create the scripts and the schedule

Create from the mirrors in `ha/scripts/` and `ha/automations/`:

| Script / automation | Fields generated | Runs |
|---|---|---|
| Household: AI Briefing (`script.household_ai_briefing`) | `headline` (≤ 90), `tip` (≤ 160), `icon` (allowed list) | Schedule; Refresh button |
| Household: AI House Summary (`script.household_ai_house_summary`) | `attention_items` (0–4), `ok_items` (1–3), each under 60 chars | Refresh button in `#ai`; skipped within 2 min of the last summary |
| Household: AI Weekly Digest (`script.household_ai_weekly_digest`) | `headline` (≤ 70); the figures are computed by the script | Sundays 18:00 |
| Household: AI Insights Schedule (`automation.household_ai_insights_schedule`) | — | 06:30, 12:00, 17:00 briefing; Sun 18:00 digest (category Routines) |

All three scripts are `mode: single` with `max_exceeded: silent`. The schedule starts them
with `script.turn_on` so a slow API call never holds the automation.

**Voice** (in every prompt): friendly and a little playful, a good-humored house manager —
courteous and clear first, a touch of wit or attitude when something has clearly been
ignored; never snarky about people, never cutesy, no emoji; facts stay precise. Briefing
priority: major issues (leak, internet down, generator running, a fault) → chores overdue or
due today and overdue vacuum maintenance → plan-changing weather → a weather note. Nothing
that changes minute to minute. The
briefing tip must come from the facts, not generic how-to advice. The digest may not
explain why a number changed unless a fact says so.

### 5. Dashboard

See `guides/home_dashboard.md`: the greeting markdown card shows the briefing headline, the
AI chip opens `#ai`, and `#ai` holds the briefing, the house summary with its button, and
the digest.

---

## Security Summary

| Control | Implementation |
|---|---|
| Data minimization | Only the `house_facts()` allowlist and weekly aggregates are sent — never all states |
| Never sent | Coordinates, lock codes, network/Firewalla details, camera images, calendars |
| Sent | Weather, AQI, indoor temps, thermostat/fireplace mode, lock and door/garage states, open openings by name, people-home count, guest/sleep flags, Avery's schedule flag, chore names, vacuum/laundry/dishwasher status, leak, generator, internet up/down, weekly energy/HVAC/vacuum totals |
| Abuse/cost limit | House summary skips if one was generated in the last 2 minutes; all scripts `mode: single` |
| Failure | A failed call fires no event; the sensors keep the last text and the dashboard shows its age |
| Credential | The Anthropic API key lives in the integration's config entry, not in this repo |
| Worst case | A leaked key exposes only API spend; the facts sent are household status, not secrets |

Cost: Claude Haiku, about 4 calls a day plus on-demand summaries — well under $1/month.

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Household AI Briefing | `sensor.household_ai_briefing` | Trigger-based template sensor (package) |
| Household AI House Summary | `sensor.household_ai_house_summary` | Trigger-based template sensor (package) |
| Household AI Weekly Digest | `sensor.household_ai_weekly_digest` | Trigger-based template sensor (package) |
| Household Vacuum Day Runs This Week | `sensor.household_vacuum_day_runs_this_week` | `history_stats` count (package) |
| Household Vacuum Night Runs This Week | `sensor.household_vacuum_night_runs_this_week` | `history_stats` count (package) |
| Household: AI Briefing | `script.household_ai_briefing` | Script |
| Household: AI House Summary | `script.household_ai_house_summary` | Script |
| Household: AI Weekly Digest | `script.household_ai_weekly_digest` | Script |
| Household: AI Insights Schedule | `automation.household_ai_insights_schedule` | Automation |
| Claude Haiku AI Task | `ai_task.claude_haiku_ai_task` | AI Task (Anthropic) |
| AI Insights | `int_ai_insights` | Label |

---

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/packages/ai_insights.yaml` | `/config/packages/ai_insights.yaml` | Result-storing sensors, weekly vacuum counters |
| `ha/custom_templates/ai_insights.jinja` | `/config/custom_templates/ai_insights.jinja` | `house_facts()` allowlist macro |

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
- **The text states something false:** check the rendered `house_facts()` output in
  Developer Tools first — wrong output is almost always an ambiguous or missing fact, fixed
  in the macro rather than the prompt.
