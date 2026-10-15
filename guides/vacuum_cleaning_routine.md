# Vacuum Cleaning Routine

*Last updated: October 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) around two fixed room lists:
a quiet nightly pass over the common areas once everyone has been asleep for an hour, and a
daytime pass over the rest of the house when the last person leaves. Once a week, on whatever
night Avery is away, the nightly pass becomes a mop pass over every hard-floor common room,
followed the next morning by a short master-suite mop while the pad is still fitted, and the
day after skips both vacuum passes. A noon prompt backstops a missed departure or a long
absence, arrival asks before docking a running job, and the dock empties only while nobody
is home. Each automation owns one trigger source (bedtime, wake, departure, arrival, noon, a
job ending, a fixed clock time, the vacuum getting stuck) rather than one room set.

---

## Architecture

```
                         ROBOROCK APP (device-side settings)
    room map + segment IDs · Stairs virtual wall · no-mop zones over rugs/doormat
    carpet boost · DND 20:00-08:00 · auto-empty OFF
                                     │
       ┌─────────────────────────────┼──────────────────────────────┐
       ▼                             ▼                              ▼
 NIGHT (bedtime)               DAY (departure)                 NOON BACKSTOP
 Household: Vacuum             Household: Last Leaves Home     Household: Vacuum
 Evening Cleaning              daytime block                   Midday Prompt
 everyone_sleeping on 1h       zone.home -> 0 for 5m           12:00, nobody home,
 (+ HA-restart recheck)        (or immediate override),        daytime not run
       │                       09:00-19:00, daytime not run         │
       ├─ mop-eligible night?        │                              ▼
       │   yes -> script.household_  ▼                         Yes/No push
       │   vacuum_mop_now          fan max                     (5m timeout = Yes)
       │   (6 hard-floor rooms)    16 17 19 20 21 23 24 26          │
       │   + mopped_overnight                                       ▼
       │   no  -> fan quiet                                    fan max, whole map
       │          18 22 25                                     marks both zones ran
       ▼
 MORNING (wake, same automation)          ARRIVAL: Household: First Arrives Home
 everyone_sleeping off 20s, after a       mid-run -> Dock now / Let it finish push
 mop night: 15m grace TTS + push,         (2m no answer = dock; stuck = re-alert,
 then mop 19 21 at fan balanced           never dock); routine-pause question
 11:00 push offers a manual start         runs in parallel

 DAILY STATE: Household: Vacuum Reset     DOCK: Household: Vacuum Dock Emptying
 08:00 clears ran-today flags, pause,     job ends -> empty pending; empties only
 mop-skip (or sets ran-today after a      while zone.home is 0 (at job end, or
 mop night); Mon 12:00 clears the         7m after everyone leaves)
 weekly mop flags

 PAD LIFECYCLE: Household: Vacuum Mop     OBSERVERS
 Pad Reminders -- 20:00+ prep TTS,        Household: Vacuum Live Activity (Lock
 cleanup push + hourly TTS after the      Screen card; marks daytime ran at 65%)
 follow-up, latches Avery-tonight         binary_sensor.vacuum_stuck -> Household:
 Household: Vacuum Setting Defaults       Vacuum Stuck Alert (TTS if home + awake)
 (pad on -> mop intensity high)
```

### Design decisions

- **Fixed room lists, no presence gate on either vacuum pass.** Kitchen, Living Room, and
  Office sit clear of the bedroom hall, so they run at night; every room near the bedroom hall
  runs during the day, when the house is empty. Only the mop pass depends on Avery, because its
  list includes the Bathroom and Entrance.
- **Zones are named for time of day, not room sets.** Helpers, `active_zone` values, and
  aliases say `evening` / `daytime`; which rooms each covers lives in [Step 1](#1-map-rooms-to-zones)
  and each automation's `description`, so a room moving between passes renames nothing.
- **The daytime start lives in *Household: Last Leaves Home*.** It shares that automation's
  trigger, 5-minute departure debounce, and Immediate Departure override, and nothing
  operationally with the nightly pass.
- **One automation owns the whole weekly mop event.** *Household: Vacuum Evening Cleaning*
  holds the nightly pass and the morning master-suite follow-up as trigger-keyed `choose`
  branches, since both ride the same pad and tank fill.
- **Every job-starting path sets its own fan speed.** Nightly `quiet`, master-suite
  `balanced`, daytime and whole-house `max` — nothing depends on what a previous job left
  behind. Mop intensity has no equivalent start moment, so *Household: Vacuum Setting
  Defaults* forces `high` whenever the pad clips on.
- **Interrupted jobs restart, they don't resume.** A commanded dock always cancels the job
  (`LESSONS.md` → *Vacuum & Roborock*), so arrival asks before docking, and a daytime job that
  docked before 65% progress runs again on the next departure.
- **The dock empties on HA's schedule, not the robot's.** Auto-empty is off in the app;
  *Household: Vacuum Dock Emptying* fires the manual empty only while nobody is home, because
  emptying is the loudest part of the routine. See [Dock Emptying](#dock-emptying).
- **Stuck detection doesn't trust the fault sensor alone.** `binary_sensor.vacuum_stuck` adds
  a stall check because a trapped fault can clear while the robot is still caught
  (`LESSONS.md` → *Vacuum & Roborock*). Arrival, the Live Activity, and the stuck alert all key
  off it.

---

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` and these Roborock
  entities available: `binary_sensor.living_room_vacuum_mop_attached`, `_water_box_attached`,
  `_water_shortage`, `_cleaning`; `sensor.living_room_vacuum_cleaning_progress`;
  `switch.living_room_vacuum_dock_dust_emptying`; `select.living_room_vacuum_mop_intensity`
- `input_boolean.everyone_sleeping` from the household sleep/presence system
- `binary_sensor.avery_home_today` — template sensor over `calendar.avery`'s "Avery @ Nate's"
  all-day events
- `zone.home` as the presence source, matching the rest of this instance's household
  automations (see the coordinated-change note in `standards/automations.md` §3.2). It tracks
  Nate and, when toggled, a guest — not Avery. Departure debounce and confirmed arrival belong
  to `guides/presence_tracking.md`.
- `script.household_tts_announce` (`guides/chime_tts.md`) and `script.household_live_activity`
  (`guides/live_activities.md`)
- The mop cloth + mount and the 350 ml water tank on hand for the weekly mop pass

---

## Steps

### 1. Map rooms to zones

Segment IDs come from the Roborock app's map, not from anything in HA:

| Pass | Rooms | Segment IDs | Set in |
|---|---|---|---|
| Nightly vacuum | Office, Kitchen, Living Room | 18, 22, 25 | *Household: Vacuum Evening Cleaning* |
| Daytime vacuum | Avery's Room, Bathroom, Master Bedroom, Master Closet, Master Bathroom, Utility Room, Pantry, Entrance | 16, 17, 19, 20, 21, 23, 24, 26 | *Household: Last Leaves Home* |
| Nightly mop | Bathroom, Kitchen, Utility Room, Pantry, Living Room, Entrance | 17, 22, 23, 24, 25, 26 | `script.household_vacuum_mop_now` |
| Morning mop | Master Bedroom, Master Bathroom | 19, 21 | *Household: Vacuum Evening Cleaning* |
| Whole-house backstop | Entire map | — (`vacuum.start`) | *Household: Vacuum Midday Prompt* |

The mop lists are hard floor only: the Office (18) and Master Closet (20) are carpeted and are
never mopped. The whole-house backstop uses `vacuum.start` rather than a segment list, so a
stale segment ID can't silently shrink it.

Segment **28 ("Stairs")** is a flight of stairs — a fall hazard — and must never be added to
any `segments:` list. A virtual wall in the Roborock app backstops it independently of HA.

Confirm a segment ID by checking that `app_segment_clean` targeting it actually starts a job
(`state` → `cleaning`); a single `roborock.get_maps` snapshot can lag an app-side merge or
rename by hours, and a retired ID no-ops silently (`LESSONS.md` → *Vacuum & Roborock*).
Segment order in the list doesn't set the route — the robot path-plans from its own position.

> **Coordinated change:** segment IDs are hardcoded in the three places named in the *Set in*
> column. If the map is rebuilt or rooms are re-split in the app, update all of them — a stale
> ID cleans the wrong room or nothing at all.

### 2. Configure the Roborock app

These live on the device, not in HA:

| Setting | Value | Why |
|---|---|---|
| Virtual wall | In front of Stairs (28) | Hardware backstop for the fall hazard |
| No-mop zones | Over every rug and the entrance doormat, a few inches oversize | The Q8 Max has no mop lift; with the pad on, the robot won't enter a no-mop zone (`LESSONS.md` → *Vacuum & Roborock*) |
| Carpet boost | On | Raises suction on the Office carpet despite the nightly `quiet` fan |
| Clean along floor direction | On | — |
| Do Not Disturb | 20:00–08:00 | Mutes voice prompts during the nightly pass; commanded starts still run |
| Auto-empty | Off | HA owns emptying — see [Dock Emptying](#dock-emptying) |

`select.living_room_vacuum_cleaning_mode` and `mop_mode` are left at their defaults and never
set by the routine; the pad sensor alone decides whether a job mops (`LESSONS.md` →
*Vacuum & Roborock*).

### 3. Create the helpers

All under the `int_vacuum_cleaning_routine` label:

| Helper | Role |
|---|---|
| `input_boolean.vacuum_ran_daytime` | Daytime pass done today. Set by *Vacuum Live Activity* once live progress clears 65% on a `daytime` job, or by *Vacuum Midday Prompt* on command |
| `input_boolean.vacuum_ran_evening` | Nightly vacuum done today. Set on command by the nightly pass, the mop branch, or the noon whole-house clean. Gates only the vacuum-only branch, never the mop |
| `input_select.vacuum_active_zone` | `evening` / `daytime` / `away` / `master_mop`, written when a job is commanded. Only `daytime` is read (the 65% check and the amber "will restart" card); the rest record which path started the last job |
| `input_boolean.vacuum_routine_pause` | Manual "stepping out briefly, don't start" toggle, set before a departure. Blocks every automatic start and the prep reminder; arrival asks whether to keep it |
| `input_boolean.vacuum_mop_common_areas_done_this_week` | The nightly mop ran this week. Set by `script.household_vacuum_mop_now` |
| `input_boolean.vacuum_mop_master_suite_done_this_week` | The morning master-suite mop ran this week |
| `input_boolean.vacuum_mopped_overnight` | Hand-off from the scheduled mop branch to the next 08:00 reset, which turns the following day into a [skip day](#skip-day-after-a-mop-night) |
| `input_boolean.vacuum_mop_skip_today` | Cancels tonight's prep reminder without changing mop eligibility |
| `input_boolean.vacuum_avery_home_tonight` | `binary_sensor.avery_home_today` latched every 30 min from 19:55 to 23:59, for the two mop-night decisions that can run after midnight (`LESSONS.md` → *Presence & Device Trackers*) |
| `input_boolean.vacuum_dock_empty_pending` | The robot's bin has dirt the dock hasn't taken yet |

*Household: Vacuum Reset* owns the clock-based clears: at 08:00 it clears both ran-today
flags, the routine pause, and mop-skip-today; at 12:00 on Mondays it clears both weekly mop
flags. The weekly clear is at noon, not 08:00, so a Sunday-night mop's follow-up isn't cut off
by a late wake.

### 4. Deploy the stuck sensor package

`binary_sensor.vacuum_stuck` is a trigger-based template sensor, which needs YAML. It is on
when the vacuum or its fault sensor reports an error, or when the vacuum has been `cleaning`
for 3+ minutes with `sensor.living_room_vacuum_cleaning_area` unchanged for that same window.
Requiring both 3-minute dwells keeps the first seconds of a new job — when the area sensor
still carries the previous job's timestamp — from reading as a stall.

`ha/packages/vacuum_stuck.yaml`, deployed to `/config/packages/vacuum_stuck.yaml`:

```yaml
template:
  - trigger:
      - trigger: time_pattern
        minutes: "/1"
        alias: Recheck every minute in case cleaning has stalled
      - trigger: state
        entity_id: vacuum.living_room_vacuum
        alias: Vacuum state changed
      - trigger: state
        entity_id: sensor.living_room_vacuum_vacuum_error
        alias: Fault sensor changed
      - trigger: state
        entity_id: sensor.living_room_vacuum_cleaning_area
        alias: Cleaned area changed
    binary_sensor:
      - name: "Vacuum Stuck"
        unique_id: living_room_vacuum_stuck
        device_class: problem
        state: >-
          {{ is_state('vacuum.living_room_vacuum', 'error')
             or states('sensor.living_room_vacuum_vacuum_error') not in
             ['none', 'unknown', 'unavailable']
             or (is_state('vacuum.living_room_vacuum', 'cleaning')
                 and has_value('sensor.living_room_vacuum_cleaning_area')
                 and (as_timestamp(now()) -
                      as_timestamp(states.vacuum.living_room_vacuum.last_changed))
                     > 180
                 and (as_timestamp(now()) -
                      as_timestamp(states.sensor.living_room_vacuum_cleaning_area.last_changed))
                     > 180) }}
```

```bash
scp ha/packages/vacuum_stuck.yaml ha:/config/packages/vacuum_stuck.yaml
```

Then run `template.reload` to load it.

### 5. Build the automations

Live YAML for every automation and script is in `ha/automations/` and `ha/scripts/`; this
guide does not reproduce it. The sections below cover behavior and the reasons behind it.

| Automation / script | Owns |
|---|---|
| *Household: Vacuum Evening Cleaning* | [Nightly pass](#nightly-pass), [weekly mop](#weekly-mop-pass) branch, [master-suite follow-up](#master-suite-follow-up) |
| *Household: Last Leaves Home* (block) | [Daytime pass](#daytime-pass) |
| *Household: Vacuum Midday Prompt* | [Noon backstop](#noon-backstop) |
| *Household: First Arrives Home* (block) | [Arrival](#arrival) dock question and routine-pause question |
| *Household: Vacuum Reset* | Clock-based flag clears ([Step 3](#3-create-the-helpers)) |
| *Household: Vacuum Mop Pad Reminders* | [Pad reminders](#pad-reminders) and the Avery-tonight latch |
| *Household: Vacuum Setting Defaults* | Mop intensity `high` on pad attach |
| *Household: Vacuum Dock Emptying* | [Dock emptying](#dock-emptying) |
| *Household: Vacuum Live Activity* | Lock Screen card and the daytime 65% check ([Monitoring](#monitoring)) |
| *Household: Vacuum Stuck Alert* | TTS when stuck ([Monitoring](#monitoring)) |
| `script.household_vacuum_mop_now` | The six-room mop job ([Ad Hoc Mop Pass](#ad-hoc-mop-pass)) |

---

## Daily Passes

### Nightly pass

*Household: Vacuum Evening Cleaning* fires once `everyone_sleeping` has been `on` for an hour.
There is no clock window — `everyone_sleeping` is only used at real bedtime, so a window would
only block an early or late night. A `homeassistant: start` trigger re-checks after a restart,
since a restart during the hour leaves the `for:` trigger unarmed.

Both branches require the routine not paused and the vacuum not already `cleaning`. Then:

- **Mop branch** — taken on a [mop-eligible night](#weekly-mop-pass).
- **Vacuum-only branch** — `vacuum_ran_evening` off and the pad off: `active_zone: evening`,
  `fan: quiet`, segments 18, 22, 25, then `vacuum_ran_evening` on. Marked on command, since
  nothing docks the nightly pass partway.
- **Neither** — with the pad on and a pass due, the night is skipped rather than dragging a wet
  pad through the vacuum pass, with a passive push *"Nightly clean skipped — the mop pad is
  attached"* (tag `vacuum_mop_cleanup`, cleared when the pad comes off).

### Daytime pass

The daytime block in *Household: Last Leaves Home* runs on that automation's departure
trigger, between 09:00 and 19:00, when `vacuum_ran_daytime` is off, the routine isn't paused,
the vacuum isn't `cleaning`, the pad is off, and the dustbin module is seated. It sets
`active_zone: daytime` and `fan: max` and cleans the daytime list. The 09:00 start keeps the
school drop-off window clear.

The block pushes when a clean that was otherwise due (not run, not paused, within hours) is
blocked by hardware:

| Blocked by | Push | Tag |
|---|---|---|
| Mop pad still attached | *Daytime clean skipped — the mop pad is still attached.* | `vacuum_mop_cleanup` |
| Dustbin module out (`water_box_attached` off) | *Daytime clean skipped — the dustbin is not installed.* | `vacuum_dustbin_missing` |

On the Q8 Max the dustbin and water tank are one module, so `water_box_attached` is also the
dustbin check; a start without it faults with `no_dustbin`.

`vacuum_ran_daytime` is set by *Vacuum Live Activity* once live progress clears 65% on a
`daytime` job, not on command — closed doors cap achievable progress, and a job docked early
should run again (`LESSONS.md` → *Vacuum & Roborock*). If a daytime job docks below 65%, the
Live Activity's done card turns amber with *"will restart when everyone leaves again"*.

### Noon backstop

*Household: Vacuum Midday Prompt* fires at 12:00 when nobody is home, `vacuum_ran_daytime` is
off, the routine isn't paused, the vacuum is exactly `docked` with `binary_sensor.living_room_vacuum_cleaning`
off, and the pad is off. It pushes a Yes/No prompt; Yes or no answer within 5 minutes starts a
whole-house clean (`active_zone: away`, `fan: max`, `vacuum.start`) and marks both ran-today
flags. One check covers a departure outside the 09:00–19:00 window and an absence of any
length, since nothing but a real clean clears `vacuum_ran_daytime`. `away`, not `daytime`, keeps
the 65% check — calibrated to the daytime room list — off a whole-map job.

### Arrival

On a confirmed arrival (`guides/presence_tracking.md`), *Household: First Arrives Home* runs two
questions in a `parallel` block so neither 2-minute wait delays the other:

- **Vacuum mid-run** — pushes *"Vacuum is still cleaning (N%). Docking ends the job."* with
  **Dock now** / **Let it finish**. Dock now or no answer within 2 minutes docks it; leaving
  again before answering lets it finish. Before docking it re-checks the vacuum is still
  cleaning and not stuck. If `binary_sensor.vacuum_stuck` is on, it never docks — it re-runs
  *Vacuum Live Activity* to re-alert the stuck card instead.
- **Routine paused** — pushes **Keep paused** / **Resume**. Resume or no answer clears the
  pause, so it never outlives the trip it was set for; Keep paused, or leaving again before
  answering, keeps it for the next departure.

Button IDs carry the run's `context.id`, so a tap on a stale push from an earlier arrival can't
answer the current one.

---

## Weekly Mop Pass

Any night Avery is away, the nightly pass mops instead — there is no fixed weekday. The mop
branch of *Household: Vacuum Evening Cleaning* runs only when all of these hold:

- Avery is away tonight (`input_boolean.vacuum_avery_home_tonight` off)
- This week's nightly mop hasn't run (`vacuum_mop_common_areas_done_this_week` off)
- The pad is fitted, the dustbin + water module is seated, and the tank isn't empty
  (`mop_attached` on, `water_box_attached` on, `water_shortage` off)

`vacuum_ran_evening` is not on the list, so a noon whole-house clean doesn't cancel the mop.
The fitted pad is the opt-in: without it the night falls back to the vacuum-only branch and the
week's mop waits for the next night Avery is away. The Live Activity card title reads
*Mop & Vacuum* while the pad is on, confirming which branch ran.

The branch calls `script.household_vacuum_mop_now` for the job itself, then turns on
`vacuum_ran_evening` and `vacuum_mopped_overnight`. Those two flags stay in the branch, not the
script, so an ad hoc mop neither marks the nightly vacuum done nor triggers a skip day.

Weekly is maintenance-level mopping — it keeps a film from building on hard floor — and the
most that holds up when the pad and tank are fitted by hand.

The nightly mop and the morning follow-up share one 350 ml fill, and the only water signal is
the binary `water_shortage`. If the tank runs dry before the follow-up finishes, drop mop
intensity to `medium` by hand; *Vacuum Setting Defaults* re-forces `high` only on the next pad
attach.

### Master suite follow-up

The morning after a mop night, the same automation mops the Master Bedroom and Master Bathroom
with the pad still fitted. It fires 20 seconds after `everyone_sleeping` turns off, and runs
when this week's nightly mop ran, this week's follow-up hasn't, the pad, module, and tank are
ready, the routine isn't paused, and the vacuum isn't mid-job.

1. Announces *"Master suite mop in 15 minutes. Refill the tank and clear the floor."* on the
   master bedroom HomePod via `script.turn_on`, so a TTS failure can't abort the branch.
2. Pushes the same text with a **Start now** button (tag `vacuum_master_mop_grace`) — a TTS
   fallback push can't carry a button.
3. Waits 15 minutes or until Start now, then clears the push.
4. Re-checks pad, module, tank, pause, and mid-job — 15 minutes is long enough to pull the
   module for a refill and not reseat it.
5. Sets `active_zone: master_mop`, `fan: balanced`, cleans segments 19 and 21, and turns on
   `vacuum_mop_master_suite_done_this_week`. If a re-check fails, it pushes the reason instead.

At 11:00, if the nightly mop ran but the follow-up hasn't, someone is up, and the pad is still
on, a push offers **Mop master suite now** (tag `vacuum_master_mop_missed`), which re-enters the
same branch, grace window included.

### Skip day after a mop night

The mop pass vacuums as it mops, so the next day runs no vacuum passes. At 08:00,
*Household: Vacuum Reset* sees `vacuum_mopped_overnight`, turns both ran-today flags **on**
instead of off, and clears the hand-off. Every start path already skips on those flags, so
none of them carries mop-night logic; the following 08:00 reset reopens both. The cost is that
Avery's Room and the Master Closet go two days between passes and the Office three nights.

### Pad reminders

*Household: Vacuum Mop Pad Reminders* runs the pad lifecycle (`mode: queued`, since its hourly
and 30-minute ticks coincide on the hour):

| Trigger | Conditions | Action |
|---|---|---|
| Every 30 min, from 20:00 | Mop-eligible night (Avery away tonight, week not mopped), not bedtime, pad off, someone home, not skipped, not paused | TTS prep reminder (`target: auto`); no push |
| Vacuum docked for 1 min | Follow-up ran this week, pad still on, docked, not everyone asleep | Cleanup push (tag `vacuum_mop_cleanup`), plus TTS 06:00–21:00 with someone home |
| Hourly on the hour | Same as re-dock | TTS only, same window |
| Pad removed | — | Clears `vacuum_mop_cleanup` and `vacuum_master_mop_missed` |

Prep is TTS-only because clipping the pad on is the acknowledgement that ends the loop.
Cleanup repeats hourly until the pad comes off, since a pad left on blocks every later pass.
The `docked` condition matters because `vacuum_mop_master_suite_done_this_week` turns on when
the follow-up starts, not when it finishes. The same 30-minute tick latches
`vacuum_avery_home_tonight` between 19:55 and 23:59.

---

## Ad Hoc Mop Pass

`script.household_vacuum_mop_now` is the only implementation of the six-room mop job — the
mop branch calls it, and it can be run from a dashboard button or the Companion App. It checks
that the pad is attached, the module is seated, the tank isn't empty, and the vacuum isn't
`cleaning`, and pushes the failed check by name instead of silently doing nothing. On success
it sets `active_zone: evening`, `fan: quiet`, `mop_intensity: high`, cleans segments 17, 22,
23, 24, 25, 26, and turns on `vacuum_mop_common_areas_done_this_week`, so any run counts as the
week's mop. It doesn't touch `vacuum_ran_evening` or `vacuum_mopped_overnight` (see
[Weekly Mop Pass](#weekly-mop-pass)), and the morning follow-up stays tied to an actual mop
night.

---

## Dock Emptying

With auto-empty off in the app, *Household: Vacuum Dock Emptying* decides when the dock
empties:

| Trigger | Action |
|---|---|
| `binary_sensor.living_room_vacuum_cleaning` `on` → `off` for 1 min (any job ended, completed or docked) | Set `vacuum_dock_empty_pending`, then empty if the house is empty |
| `zone.home` → `0` for 7 min | Empty if one is pending |
| `switch.living_room_vacuum_dock_dust_emptying` → `on` (any empty, including one from the app) | Clear `vacuum_dock_empty_pending` |

An empty runs only when it is pending, nobody is home, the vacuum is `docked` and not mid-job,
and the dustbin module is seated. The 7-minute departure trigger lands after *Last Leaves
Home*'s 5-minute daytime start: if that pass starts, the vacuum is busy, and the job-end
trigger empties the bin when it finishes with nobody home.

The empty isn't confirmed inline — HA can see it anywhere from instantly to a minute or more
late (`LESSONS.md` → *Vacuum & Roborock*). The `→ on` trigger clears the flag whenever it
lands; if an empty never happens, the flag stays on and the next trigger retries. The
automation runs `mode: queued` so that trigger isn't dropped when it fires before the run
that started the empty has finished.

In practice, a daytime pass empties when it finishes; nightly passes and runs that finish
while someone is home leave the flag set until the next departure. If nobody leaves for
several days, the robot's onboard bin carries several nightly passes.

---

## Monitoring

*Household: Vacuum Live Activity* drives the iOS Lock Screen card for every job regardless of
which path started it (`guides/live_activities.md` owns the card contract and colours).
Running and returning cards are suppressed while everyone is asleep, and the done card lands
silently overnight. On any of its triggers, it marks `vacuum_ran_daytime` once live progress
clears 65% while `active_zone` is `daytime`; progress resets about 20 seconds after the
relevant state change, so sampling at every transition reliably beats the reset
(`LESSONS.md` → *Vacuum & Roborock*).

*Household: Vacuum Stuck Alert* speaks *"The vacuum is stuck. Go check on it."* when
`binary_sensor.vacuum_stuck` turns on, if someone is home and awake. The Live Activity's stuck
update already sends the push.

---

## Consumable Resets

The Roborock integration's four reset buttons (`button.living_room_vacuum_reset_*_consumable`)
are disabled by default and are enabled in the entity registry.
`script.household_vacuum_reset_consumable` takes `consumable` (`air_filter`, `main_brush`,
`side_brush`, `sensor`, `filter_clean`), presses the matching button, waits 2 s, and refreshes
the matching `sensor.living_room_vacuum_*_time_left` — otherwise the reset shows only on the
next poll. Holding a Maintenance card in the `home-main` `#vacuum` pop-up calls it with no
confirmation (`guides/home_dashboard.md`).

**Filter cleaning.** The filter's 150 h life splits into three 50 h intervals: clean at 100 h
and 50 h left, replace at 0 h. `input_number.living_room_vacuum_filter_left_at_last_clean`
stores hours left at the last clean; `filter_clean` writes it, and `air_filter` writes it after
the reset so the clean timer restarts with a new filter. Template helper Living Room Vacuum
Filter Clean Time Left (`sensor.living_room_vacuum_filter_clean_time_left`) reports
`50 − (stored − current)`, or the filter's hours left (minimum 0) + 50 once replacement comes
first, so a replace-due filter never also shows a clean due. A filter reset done in the app
doesn't update the stored reading; hold *Filter clean* once afterward to realign it.

**Maintenance chores.** *Household: Vacuum Maintenance Chores* puts due maintenance on the
household chore list (`guides/reminders.md`):

| Counter reaches 0 h | Chore |
|---|---|
| `sensor.living_room_vacuum_filter_time_left` | Replace Vacuum Filter |
| `sensor.living_room_vacuum_filter_clean_time_left` | Clean Vacuum Filter |
| `sensor.living_room_vacuum_main_brush_time_left` | Replace Vacuum Main Brush |
| `sensor.living_room_vacuum_side_brush_time_left` | Replace Vacuum Side Brush |
| `sensor.living_room_vacuum_sensor_time_left` | Clean Vacuum Sensors |

- **Due:** a counter dropping to 0 h (or at 0 h on HA start) creates a one-off chore due now,
  unless it's already open.
- **Completed:** marking the chore done (`chore_calendar_status_changed`, `to_status:
  completed`) runs the reset script for that counter and deletes the chore. Mark it done only
  after the maintenance.
- **Reset elsewhere:** a counter rising above 0 h deletes its open chore.

Chores are matched by name, so these names must not be reused for other chores.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Evening Cleaning | `automation.household_vacuum_evening_cleaning` | Automation |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation (daytime block) |
| Household: Vacuum Midday Prompt | `automation.household_vacuum_midday_prompt` | Automation |
| Household: First Arrives Home | `automation.household_first_arrives_home` | Automation (arrival dock and pause questions) |
| Household: Vacuum Reset | `automation.household_vacuum_reset` | Automation |
| Household: Vacuum Mop Pad Reminders | `automation.household_vacuum_mop_pad_reminders` | Automation |
| Household: Vacuum Setting Defaults | `automation.household_vacuum_setting_defaults` | Automation |
| Household: Vacuum Dock Emptying | `automation.household_vacuum_dock_emptying` | Automation |
| Household: Vacuum Live Activity | `automation.household_vacuum_live_activity` | Automation |
| Household: Vacuum Stuck Alert | `automation.household_vacuum_stuck_alert` | Automation |
| Household: Vacuum Maintenance Chores | `automation.household_vacuum_maintenance_chores` | Automation |
| Household: Vacuum Mop Now | `script.household_vacuum_mop_now` | Script |
| Household: Vacuum Reset Consumable | `script.household_vacuum_reset_consumable` | Script |
| Live Activity dispatch | `script.household_live_activity` | Script |
| TTS dispatch | `script.household_tts_announce` | Script |
| Vacuum Stuck | `binary_sensor.vacuum_stuck` | Template sensor (package) |
| Living Room Vacuum Filter Clean Time Left | `sensor.living_room_vacuum_filter_clean_time_left` | Template helper |
| Living Room Vacuum Filter Left At Last Clean | `input_number.living_room_vacuum_filter_left_at_last_clean` | Helper |
| Vacuum Ran Daytime | `input_boolean.vacuum_ran_daytime` | Helper |
| Vacuum Ran Evening | `input_boolean.vacuum_ran_evening` | Helper |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |
| Vacuum Mop Common Areas Done This Week | `input_boolean.vacuum_mop_common_areas_done_this_week` | Helper |
| Vacuum Mop Master Suite Done This Week | `input_boolean.vacuum_mop_master_suite_done_this_week` | Helper |
| Vacuum Mopped Overnight | `input_boolean.vacuum_mopped_overnight` | Helper |
| Vacuum Mop Skip Today | `input_boolean.vacuum_mop_skip_today` | Helper |
| Vacuum Avery Home Tonight | `input_boolean.vacuum_avery_home_tonight` | Helper |
| Vacuum Dock Empty Pending | `input_boolean.vacuum_dock_empty_pending` | Helper |
| Reset air filter / main brush / side brush / sensor consumable | `button.living_room_vacuum_reset_*_consumable` | Button ×4 (enabled) |

---

## Related Files

| Repo Path | Deployed Location | Purpose |
|---|---|---|
| `ha/packages/vacuum_stuck.yaml` | `/config/packages/vacuum_stuck.yaml` | `binary_sensor.vacuum_stuck` — repo-authoritative, see [Step 4](#4-deploy-the-stuck-sensor-package) |

---

## Related Documents

- `standards/automations.md` — naming, category, and label conventions applied here
- `guides/presence_tracking.md` — `zone.home`, the departure debounce, and confirmed arrival
- `guides/live_activities.md` — `script.household_live_activity` contract and status palette
- `guides/chime_tts.md` — `script.household_tts_announce` contract
- `guides/home_dashboard.md` — the `#vacuum` pop-up and maintenance cards
- `LESSONS.md` → *Vacuum & Roborock* — Roborock behavior this design is built around
- `LESSONS.md` → *Presence & Device Trackers* — the midnight rollover the Avery-tonight latch
  works around

---

## Troubleshooting

**`vacuum_ran_daytime` never turns on although the vacuum finished.** Check
`input_select.vacuum_active_zone` when the job ran. A job started outside these automations
(the Roborock app) doesn't update it, so the 65% check attributes the job to whatever zone was
last written.

**The mop branch ran on the wrong night for Avery's calendar.** Compare
`input_boolean.vacuum_avery_home_tonight` with `binary_sensor.avery_home_today` at the time the
pass fired. If they disagree, the 19:55–23:59 latch missed its ticks (a restart or reload across
the window); it corrects itself the next evening.

**Midday Prompt asks every day of a long trip.** Intended — the noon check is the only
mechanism for an extended absence and keeps no memory of a previous No.

**Midday Prompt doesn't start although the vacuum looks idle.** The vacuum must be exactly
`docked` with `binary_sensor.living_room_vacuum_cleaning` off. `vacuum.start` sends a dock
command while `returning`, and a mid-job recharge reads `docked` with the cleaning sensor still
on (`LESSONS.md` → *Vacuum & Roborock*).

**The master-suite follow-up skips with "the water module isn't seated."** The module was
pulled to refill and not reseated within the 15-minute grace window. The 11:00 push offers a
manual start.

**Arrival didn't dock a running vacuum.** It docks only on Dock now or no answer within 2
minutes; Let it finish or leaving again leaves it running. Otherwise check
`binary_sensor.vacuum_stuck` — a stuck vacuum is never docked; clear the obstruction, and the
sensor drops within a minute of real progress.

**The dock never empties.** Check `input_boolean.vacuum_dock_empty_pending`. If it's on, the
house hasn't been empty with the vacuum docked and idle since the last job ended — the next
departure empties it. If an empty ran but the flag stayed on, HA hasn't polled the dock since;
it clears on the next update.
