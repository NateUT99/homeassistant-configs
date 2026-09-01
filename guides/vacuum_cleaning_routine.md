# Vacuum Cleaning Routine

*Last updated: September 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two independent schedules: a quiet pass over shared common areas in the evening, and a full-speed pass over the remaining rooms during the day when the house empties out. Each schedule targets a fixed set of rooms, tracks its own daily completion state, and never references the other's progress.

The evening pass is its own automation (*Household: Vacuum Evening Cleaning*). The daytime pass is **not** a standalone automation — it is a block inside *Household: Last Leaves Home*, so it rides the same departure trigger, the same 5-minute debounce, and the Immediate Departure override as the rest of the leave-home routine (garage, locks, thermostat). Docking the vacuum when someone comes home mid-run, and clearing the routine-pause flag on arrival, likewise live in *Household: First Arrives Home* alongside the other confirmed-arrival actions. This mirrors how the old apartment folded both the vacuum start and the arrival dock into its presence automations; the rebuild briefly split them into dedicated vacuum automations, then folded them back once they proved to share nothing with the evening run.

The old apartment's version of this automation started the vacuum when the last person left and docked it when the first person arrived, then simply restarted the whole-house clean from scratch on every subsequent departure — using a "best single attempt cleared 50% progress" threshold to decide the day was done, never actually resuming an interrupted job. This rebuild set out to improve on that with genuine resume, which testing then proved isn't possible on this hardware (see [Why resume isn't used](#why-resume-isnt-used)); the two-zone schedule below is what replaced that goal.

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
        │ living, entrance,   │        │ master bed, master bath,│
        │ kitchen             │        │ master closet, utility, │
        │                     │        │ pantry                  │
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

The two zones were originally named for the rooms they cover (Common Areas / Remaining Rooms). That was accurate but not intuitive — "remaining" in particular didn't communicate anything on its own — so the helpers, `active_zone` values, and automation aliases all use time-of-day naming instead: **evening** = common areas (Office, Dining room, Living room, Entrance, Kitchen), **daytime** = the rest (Bedroom, Bathroom, Master bedroom, Master Bathroom, Utility Room, Pantry). Which physical rooms each zone covers lives in this guide and in each automation's `description`, not in the entity names.

### Why resume isn't used

This rebuild's original goal was for an interrupted job to pick up where it left off, rather than restarting from scratch as the old apartment did. Live testing on this unit (2026-08-25) ruled that out conclusively: **any manually issued dock command cancels the active cleaning job**, whether it was paused first or not, and whether the job was a whole-house clean or a room-scoped segment clean. Three separate tests confirmed this — see `LESSONS.md` → *Vacuum & Roborock* for the details and Roborock's own documentation, which states the same thing.

A follow-up design tracked which rooms a segment clean had *already* finished, so an interrupted job could resume at room granularity next time. That also broke down: `sensor.<vacuum>_current_room` flips back and forth between adjacent open-plan rooms every 30–120 seconds within a single run, so "the robot just left this room" is not a reliable signal that the room is done.

### Why two fixed zones instead of one adaptive schedule

An earlier draft had the evening run act as a fallback only when the daytime run failed, with the daytime run then "topping up" whatever the evening run had missed. This reintroduced the same problem as room-level resume: partial-completion state that has to persist across the 08:00 reset boundary while daytime departures are unpredictable — sometimes the daytime run never fires because nobody leaves.

The final design sidesteps this by never tracking leftovers at all. **Evening** and **Daytime** are fixed, non-overlapping room sets, each with its own trigger, its own completion flag, and its own max-progress tracker. Bedrooms and bathrooms can only ever be reached during the day regardless of design — noise rules out cleaning them in the evening — so the two-zone split isn't a workaround, it's just naming a constraint that was already there.

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` entity available
- Room map built in the Roborock app, with segment IDs known (`roborock.get_maps` service)
- `binary_sensor.avery_home_today`, `input_boolean.everyone_sleeping`, `input_boolean.avery_sleeping` already existing as part of the household sleep/presence system
- `zone.home` as the presence source (matches the rest of this instance's household automations; see the Coordinated Change note in `standards/automations.md` §3.2 about the eventual migration to `sensor.household_people_home`). The daytime run's departure trigger and 5-minute debounce belong to *Household: Last Leaves Home*, not this routine — see `guides/presence_tracking.md`.

## Steps

### 1. Map rooms to zones

Room segment IDs are read from the Roborock app's map, not derived from anything in HA. As of the last map rebuild:

| Zone | Rooms | Segment IDs |
|---|---|---|
| Evening (common areas) | Office, Living room, Entrance, Kitchen (Kitchen absorbed the former Dining room) | 18, 22, 25, 26 |
| Daytime (remaining rooms) | Bedroom, Bathroom, Master bedroom, Master Bathroom, Master Closet, Utility Room, Pantry | 16, 17, 19, 20, 21, 23, 24 |

Segment 20 (Master Closet) was originally believed to be a gap in the ID sequence — it was actually an already-mapped room the Roborock app had generically labeled "Room," not surfaced by `roborock.get_maps`' named-room dict until renamed. Confirmed by sending a single-segment test clean (`app_segment_clean`, `segments: [20]`) and visually observing the robot enter the closet — `sensor.living_room_vacuum_current_room` could not confirm it directly; see `LESSONS.md` → *Vacuum & Roborock*.

On 2026-08-26, Kitchen and Dining room were merged into one room in the Roborock app. The merge landed on segment ID **22** (absorbing the old Dining room's footprint) and retired the old Kitchen ID, **27**, entirely rather than renaming it — `roborock.get_maps` briefly showed 22 still as "Dining room" and 27 still as "Kitchen" for hours after the app-side edit, and a functional test against 27 during that lag window actually worked (it was still valid at that moment). Don't trust a single `get_maps` snapshot as final during a pending merge/rename — confirm the *current* segment ID by testing whether `app_segment_clean` targeting it actually starts a job (`state` → `cleaning`); a retired ID silently no-ops instead of erroring. The same map sync also surfaced a new, previously-unmapped segment **28 ("Stairs")**. This is a physical flight of stairs — a fall hazard, not an oversight — and is **deliberately excluded from both zones and must never be added to a `segments:` list**. A virtual wall is also placed in front of it in the Roborock app as a hardware-level backstop independent of this automation.

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app, segment IDs can change. Re-run `roborock.get_maps` and update the `segments:` list in both places — the evening list in *Household: Vacuum Evening Cleaning*, the daytime list in the "Start daytime vacuum" block of *Household: Last Leaves Home*. A stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Five helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_evening_max_progress`, `input_number.vacuum_daytime_max_progress` — running maximum progress seen in each zone since the last reset. Needed because a commanded dock resets live progress to 0, but "best coverage achieved today" has to survive that.
- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags.
- `input_select.vacuum_active_zone` (`evening` / `daytime`) — set the moment a job is commanded (by *Vacuum Evening Cleaning* for evening, by the *Last Leaves Home* daytime block for daytime). Exists because live progress and the `returning` trigger are shared across both zones; without recording which zone commanded the current job, the tracking and completion automations couldn't tell a 5-room job's 100% from an 11-room job's 100%.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically on arrival rather than surviving to block a later real departure.

### 3. Build the automations

Four standalone vacuum automations (*Vacuum Evening Cleaning*, *Vacuum Track Max Progress*, *Vacuum Mark Area Complete*, *Vacuum Daily Reset*), plus two blocks folded into the presence automations: the daytime-start block in *Household: Last Leaves Home* and the arrival dock + routine-pause clear in *Household: First Arrives Home*. All described in the architecture diagram above. Live YAML for each is in `ha/automations/` — this guide does not reproduce it; fetch via `ha_config_get_automation` for the current version. Key design points not obvious from the YAML alone:

- **The two starts are split, not combined.** Evening cleaning is its own automation (*Household: Vacuum Evening Cleaning*, single `everyone_sleeping` trigger). Daytime cleaning is a block inside *Household: Last Leaves Home* — it has nothing operationally in common with the evening run (different trigger, zone, settings, completion flag) and everything in common with the rest of the leave-home routine, so it lives there and inherits that automation's 5-minute departure debounce and Immediate Departure override. An earlier rebuild draft merged both starts into one `choose` keyed on `condition: trigger, id: ...`; that only ever coupled two things that don't interact.
- **The daytime block's guards double as re-run protection.** *Last Leaves Home* fires twice on an immediate departure (once instantly, once when the 5-minute trigger elapses). The daytime block's `vacuum_ran_daytime` off + "not currently cleaning" conditions make the second pass a no-op — no second job, no duplicate notification.
- The evening automation's trigger is deliberately *just* "everyone's been asleep for 1 hour," with no clock-time restriction. An earlier draft added a 21:00–05:00 window to guard against a daytime nap accidentally triggering an evening-flavored run — dropped once confirmed `everyone_sleeping` is only ever used at actual bedtime, never naps, so the guard protected against a scenario that can't happen while risking blocking a genuinely early or late bedtime.
- **The arrival dock** (in *Household: First Arrives Home*) does not call `vacuum.pause` before `vacuum.return_to_base`. Testing showed pausing first makes no difference to whether the job survives — it doesn't, either way — so the extra call and delay were dropped.
- **There is no "someone woke mid-evening-run" dock.** An earlier *Vacuum Stops For Occupants* automation also docked the robot when `everyone_sleeping` went `off` during an evening run. It was dropped when that automation was retired: the window it covers (someone up within the ~40 min quiet common-areas pass) is rare, the pass is low-noise, and a manual dock from the app or a voice command handles it when it matters. Docking now only happens on a confirmed arrival.
- **Vacuum Mark Area Complete** uses different thresholds per zone: Evening requires >95% (open-plan, should reliably finish end-to-end when uninterrupted), Daytime requires >65% (several of those rooms have doors that may be closed, capping achievable progress in a way retrying won't fix). Originally set to 50% to match the old apartment's tuned value; raised to 65% on 2026-08-26 after a real run confirmed 2 of 6 rooms (Utility Room, Pantry — both door-closed) still cleared 91%, since progress is area-weighted rather than room-count-weighted and small rooms cost only a few points each when inaccessible. Still based on limited real-world data — revisit if daytime runs start landing below 65% on door-closed days.
- **Segment order in `app_segment_clean` does not determine cleaning route.** Confirmed via trace: a job commanded `[16,17,19,21,23,24]` was actually visited 19 → 21 → 17 → 16 (23/24 skipped, doors closed) — the robot path-plans from its own position, not the array order. No need to sort segment lists for routing.
- **Vacuum Daily Reset** fires at 08:00, not midnight. An evening run that starts just after midnight must still see *yesterday's* ran-today flags; a midnight reset would collide with that window, since a typical bedtime plus the 1-hour hold can land right at or after midnight. The two zones' flags are otherwise fully independent — the evening branch never checks whether the daytime branch succeeded, or vice versa.

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
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability) this design is built around
- `snapshot/2026-07-27-pre-move/automations/automation.household_vacuum_daily_max_progress.yaml` — the old apartment's max-progress tracking pattern this routine revives, split by zone

## Troubleshooting

**Evening run doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the evening window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts — but this was not exhaustively verified against every firmware update. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run (which would un-mute voice prompts mid-run).

**A zone's `ran_*` flag never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Track Max Progress* / *Vacuum Mark Area Complete* will silently attribute progress to whichever zone the helper happened to already be set to.
