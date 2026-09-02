# Vacuum Cleaning Routine

*Last updated: September 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two
independent schedules: a quiet pass over shared common areas in the evening, and a
full-speed pass over the remaining rooms during the day when the house empties out. Each
schedule targets a fixed set of rooms, tracks its own daily completion state, and never
references the other's progress.

The evening pass is its own automation (*Household: Vacuum Evening Cleaning*). The daytime
pass is a block inside *Household: Last Leaves Home*, so it rides that automation's departure
trigger, 5-minute debounce, and Immediate Departure override alongside the garage/lock/
thermostat actions. Docking the vacuum when someone returns mid-run, and clearing the
routine-pause flag on arrival, likewise live in *Household: First Arrives Home* with the
other confirmed-arrival actions.

The two zones are fixed and non-overlapping because the constraint is physical: the evening
pass has to be quiet enough to run with the house asleep, so it covers only the rooms clear
of Avery's Room (Office, Living room, Kitchen) and runs regardless of who is home. The
daytime pass takes everything else — bedrooms, bathrooms, and the Entrance, which is the one
common-area room within earshot of the bedroom hall. Interrupted jobs restart rather than
resume: a commanded dock always cancels the active Roborock job, and
`sensor.<vacuum>_current_room` is too noisy to track room-level completion — see
`LESSONS.md` → *Vacuum & Roborock*.

## Architecture

```
     ┌──────────────────────────┐   ┌────────────────────────────────┐
     │ Household: Vacuum         │   │ Household: Last Leaves Home     │
     │ Evening Cleaning          │   │ "Start daytime vacuum" block    │
     └────────────┬─────────────┘   └───────────────┬────────────────┘
                  │                                 │
   everyone_sleeping                     zone.home -> 0 for 5m
   on for 1h                             (or immediate, override armed)
                  ▼                                 ▼
        ┌─────────────────────┐        ┌─────────────────────────┐
        │ fan: quiet          │        │ fan: max                │
        │ mop: off            │        │ mop: medium             │
        │ segments: office,   │        │ segments: bedroom, bath,│
        │ living, kitchen     │        │ master bed, master bath,│
        │                     │        │ master closet, utility, │
        │                     │        │ pantry, entrance        │
        └──────────┬──────────┘        └──────────┬──────────────┘
                   │                              │
                   ▼                              ▼
              input_select.vacuum_active_zone = evening | daytime
                         │
                         ▼
        ┌────────────────────────────────────────────────┐
        │  Household: Vacuum Track Max Progress            │
        │  (every progress tick, choose by active_zone)     │
        │  -> input_number.vacuum_{zone}_max_progress       │
        └────────────────────────────────────────────────┘
                         │
                         ▼  vacuum enters "returning"
        ┌────────────────────────────────────────────────┐
        │  Household: Vacuum Mark Area Complete             │
        │  if max_progress clears the zone's threshold:     │
        │    evening -> vacuum_ran_evening = on              │
        │    daytime -> vacuum_ran_daytime = on              │
        └────────────────────────────────────────────────┘

  Household: First Arrives Home                   Household: Vacuum Daily Reset
  (confirmed-arrival block)                       trigger: 08:00 daily
  docks the vacuum if mid-run (cancels the        clears both ran-today flags,
  job -- expected on this hardware) and           both max-progress numbers,
  clears vacuum_routine_pause                     and the routine-pause flag
```

### Why "evening" and "daytime" rather than room-set names

The helpers, `active_zone` values, and automation aliases use time-of-day naming — **evening**
= common areas clear of the bedroom hall (Office, Living room, Kitchen), **daytime** = the
rest (Bedroom, Bathroom, Master bedroom, Master Bathroom, Master Closet, Utility Room,
Pantry, Entrance). Which physical rooms each zone covers lives in this guide and in each
automation's `description`, not in the entity names — a room-set name like "remaining rooms"
carries no meaning on its own.

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` entity available
- Room map built in the Roborock app, with segment IDs known (`roborock.get_maps` service)
- `input_boolean.everyone_sleeping` already existing as part of the household sleep/presence system
- `zone.home` as the presence source (matches the rest of this instance's household automations; see the Coordinated Change note in `standards/automations.md` §3.2 about the eventual migration to `sensor.household_people_home`). The daytime run's departure trigger and 5-minute debounce belong to *Household: Last Leaves Home*, not this routine — see `guides/presence_tracking.md`.

## Steps

### 1. Map rooms to zones

Room segment IDs are read from the Roborock app's map, not derived from anything in HA:

| Zone | Rooms | Segment IDs |
|---|---|---|
| Evening (common areas) | Office, Living room, Kitchen (Kitchen absorbed the former Dining room) | 18, 22, 26 |
| Daytime (remaining rooms) | Bedroom, Bathroom, Master bedroom, Master Bathroom, Master Closet, Utility Room, Pantry, Entrance | 16, 17, 19, 20, 21, 23, 24, 25 |

Segment **28 ("Stairs")** is a physical flight of stairs — a fall hazard — and is
**deliberately excluded from both zones and must never be added to a `segments:` list**. A
virtual wall is also placed in front of it in the Roborock app as a hardware-level backstop
independent of this automation.

When confirming a segment ID, don't trust a single `roborock.get_maps` snapshot: after an
app-side merge or rename it can lag reality by hours, and a merge retires the old ID rather
than aliasing it (a retired ID silently no-ops instead of erroring). Confirm the *current* ID
by testing whether `app_segment_clean` targeting it actually starts a job (`state` →
`cleaning`). A room the app labels generically ("Room") may not appear in `get_maps`' named-
room dict until renamed — send a single-segment test clean and watch the robot to verify.
See `LESSONS.md` → *Vacuum & Roborock*.

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app, segment IDs can change. Re-run `roborock.get_maps` and update the `segments:` list in both places — the evening list in *Household: Vacuum Evening Cleaning*, the daytime list in the "Start daytime vacuum" block of *Household: Last Leaves Home*. A stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Five helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_evening_max_progress`, `input_number.vacuum_daytime_max_progress` — running maximum progress seen in each zone since the last reset. Needed because a commanded dock resets live progress to 0, but "best coverage achieved today" has to survive that.
- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags.
- `input_select.vacuum_active_zone` (`evening` / `daytime`) — set the moment a job is commanded (by *Vacuum Evening Cleaning* for evening, by the *Last Leaves Home* daytime block for daytime). Live progress and the `returning` trigger are shared across both zones; without recording which zone commanded the current job, the tracking and completion automations couldn't tell a 5-room job's 100% from an 11-room job's 100%.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically on arrival rather than surviving to block a later real departure.

### 3. Build the automations

Four standalone vacuum automations (*Vacuum Evening Cleaning*, *Vacuum Track Max Progress*, *Vacuum Mark Area Complete*, *Vacuum Daily Reset*), plus two blocks folded into the presence automations: the daytime-start block in *Household: Last Leaves Home* and the arrival dock + routine-pause clear in *Household: First Arrives Home*. All described in the architecture diagram above. Live YAML for each is in `ha/automations/` — this guide does not reproduce it. Key design points not obvious from the YAML alone:

- **The two starts are split, not combined.** Evening cleaning is its own automation (single `everyone_sleeping` trigger). Daytime cleaning is a block inside *Household: Last Leaves Home* — it shares nothing operationally with the evening run (different trigger, zone, settings, completion flag) and everything with the rest of the leave-home routine, so it lives there and inherits that automation's 5-minute departure debounce and Immediate Departure override.
- **The daytime block's guards double as re-run protection.** *Last Leaves Home* fires twice on an immediate departure (once instantly, once when the 5-minute trigger elapses). The daytime block's `vacuum_ran_daytime` off + "not currently cleaning" conditions make the second pass a no-op — no second job, no duplicate notification.
- **The evening trigger is just "everyone's been asleep for 1 hour," with no clock-time window.** `everyone_sleeping` is only ever used at actual bedtime, never naps, so a time window would only risk blocking a genuinely early or late bedtime.
- **The evening run has no presence gate.** Every room in the evening zone (Office, Living room, Kitchen) is acoustically clear of Avery's Room, so the quiet common-areas pass runs every night regardless of who is home. The Entrance — the one common-area room within earshot of the bedroom hall — sits in the daytime zone for that reason, not because it can't be cleaned at night. The cost is that on a day the house never fully empties, the front-door area goes uncleaned; front-door dirt is the most frequent-cleaning argument there is, and it's accepted as the price of a gate-free evening run. `binary_sensor.avery_home_today` still exists for other automations; this routine no longer reads it.
- **The arrival dock** (in *Household: First Arrives Home*) does not call `vacuum.pause` before `vacuum.return_to_base` — pausing first makes no difference to whether the job survives a dock (it doesn't, either way).
- **Docking only happens on a confirmed arrival.** There is no "someone woke mid-evening-run" dock: the window it would cover (someone up within the ~40 min quiet common-areas pass) is rare and low-noise, and a manual dock from the app or a voice command handles it when it matters.
- **Vacuum Mark Area Complete** uses different thresholds per zone: Evening requires >95% (open-plan, should reliably finish end-to-end when uninterrupted), Daytime requires >65% (several of those rooms have doors that may be closed, capping achievable progress in a way retrying won't fix — progress is area-weighted, so a closed small room costs only a few points). Still based on limited real-world data — revisit if daytime runs start landing below 65% on door-closed days.
- **Segment order in `app_segment_clean` does not determine cleaning route.** The robot path-plans from its own position, not the array order — no need to sort segment lists.
- **Vacuum Daily Reset** fires at 08:00, not midnight. An evening run that starts just after midnight (a typical bedtime plus the 1-hour hold can land there) must still see *yesterday's* ran-today flags; a midnight reset would collide with that window. The two zones' flags are otherwise fully independent.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Evening Cleaning | `automation.household_vacuum_evening_cleaning` | Automation |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation (contains the daytime-start block) |
| Household: First Arrives Home | `automation.household_first_arrives_home` | Automation (contains the arrival dock + routine-pause clear) |
| Household: Vacuum Track Max Progress | `automation.household_vacuum_track_max_progress` | Automation |
| Household: Vacuum Mark Area Complete | `automation.household_vacuum_mark_area_complete` | Automation |
| Household: Vacuum Daily Reset | `automation.household_vacuum_daily_reset` | Automation |
| Vacuum Evening Max Progress | `input_number.vacuum_evening_max_progress` | Helper |
| Vacuum Daytime Max Progress | `input_number.vacuum_daytime_max_progress` | Helper |
| Vacuum Ran Evening | `input_boolean.vacuum_ran_evening` | Helper |
| Vacuum Ran Daytime | `input_boolean.vacuum_ran_daytime` | Helper |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |

## Related Documents

- `standards/automations.md` — automation naming, category, and label conventions applied here
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability, `get_maps` merge lag) this design is built around
- `snapshot/2026-07-27-pre-move/automations/automation.household_vacuum_daily_max_progress.yaml` — the max-progress tracking pattern this routine revives, split by zone

## Troubleshooting

**Evening run doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the evening window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run.

**A zone's `ran_*` flag never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Track Max Progress* / *Vacuum Mark Area Complete* will silently attribute progress to whichever zone the helper happened to already be set to.
