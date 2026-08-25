# Vacuum Cleaning Routine

*Last updated: August 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two independent schedules: a quiet pass over shared common areas in the evening, and a full-speed pass over the remaining rooms during the day when the house empties out. Each schedule targets a fixed set of rooms, tracks its own daily completion state, and never references the other's progress.

This design replaces the old apartment's "start on last-leaves, dock on first-arrives, resume where it left off" pattern. That pattern is not achievable on this hardware — see [Why resume isn't used](#why-resume-isnt-used) below — so the routine instead guarantees the whole house gets covered across two scheduled windows rather than one continuous job.

## Architecture

```
                    ┌─────────────────────────────┐
                    │  Household: Vacuum Start     │
                    │  Cleaning                    │
                    │  (choose, keyed by trigger)  │
                    └──────┬────────────────┬───────┘
                           │                │
        everyone_sleeping  │                │  zone.home -> 0
        on for 1h          │                │  for 2m30s
                           ▼                ▼
              ┌─────────────────────┐  ┌─────────────────────────┐
              │ Evening branch      │  │ Daytime branch          │
              │ fan: quiet          │  │ fan: max                │
              │ mop: off            │  │ mop: medium              │
              │ segments: office,   │  │ segments: bedroom, bath, │
              │ dining, living,     │  │ master bed, master bath, │
              │ entrance, kitchen   │  │ utility, pantry          │
              └──────────┬──────────┘  └──────────┬──────────────┘
                         │                         │
                         ▼                         ▼
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

  Household: Vacuum Stops For Occupants           Household: Vacuum Daily Reset
  triggers: arrival, someone wakes mid-run        trigger: 08:00 daily
  docks the vacuum (cancels the job --            clears both ran-today flags,
  expected on this hardware) and clears           both max-progress numbers,
  vacuum_routine_pause                            and the routine-pause flag
```

### Why "evening" and "daytime" rather than room-set names

The two zones were originally named for the rooms they cover (Common Areas / Remaining Rooms). That was accurate but not intuitive — "remaining" in particular didn't communicate anything on its own — so the helpers, `active_zone` values, and automation aliases all use time-of-day naming instead: **evening** = common areas (Office, Dining room, Living room, Entrance, Kitchen), **daytime** = the rest (Bedroom, Bathroom, Master bedroom, Master Bathroom, Utility Room, Pantry). Which physical rooms each zone covers lives in this guide and in each automation's `description`, not in the entity names.

### Why resume isn't used

The original design goal was "pick up where it left off after an interruption," matching the old apartment. Live testing on this unit (2026-08-25) ruled that out conclusively: **any manually issued dock command cancels the active cleaning job**, whether it was paused first or not, and whether the job was a whole-house clean or a room-scoped segment clean. Three separate tests confirmed this — see `LESSONS.md` → *Vacuum & Roborock* for the details and Roborock's own documentation, which states the same thing.

A follow-up design tracked which rooms a segment clean had *already* finished, so an interrupted job could resume at room granularity next time. That also broke down: `sensor.<vacuum>_current_room` flips back and forth between adjacent open-plan rooms every 30–120 seconds within a single run, so "the robot just left this room" is not a reliable signal that the room is done.

### Why two fixed zones instead of one adaptive schedule

An earlier draft had the evening run act as a fallback only when the daytime run failed, with the daytime run then "topping up" whatever the evening run had missed. This reintroduced the same problem as room-level resume: partial-completion state that has to persist across the 08:00 reset boundary while daytime departures are unpredictable — sometimes the daytime run never fires because nobody leaves.

The final design sidesteps this by never tracking leftovers at all. **Evening** and **Daytime** are fixed, non-overlapping room sets, each with its own trigger, its own completion flag, and its own max-progress tracker. Bedrooms and bathrooms can only ever be reached during the day regardless of design — noise rules out cleaning them in the evening — so the two-zone split isn't a workaround, it's just naming a constraint that was already there.

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` entity available
- Room map built in the Roborock app, with segment IDs known (`roborock.get_maps` service)
- `binary_sensor.avery_home_today`, `input_boolean.everyone_sleeping`, `input_boolean.avery_sleeping` already existing as part of the household sleep/presence system
- `zone.home` as the presence source (matches the rest of this instance's household automations; see the Coordinated Change note in `standards/automations.md` §3.2 about the eventual migration to `sensor.household_people_home`)

## Steps

### 1. Map rooms to zones

Room segment IDs are read from the Roborock app's map, not derived from anything in HA. As of the last map rebuild:

| Zone | Rooms | Segment IDs |
|---|---|---|
| Evening (common areas) | Office, Dining room, Living room, Entrance, Kitchen | 18, 22, 25, 26, 27 |
| Daytime (remaining rooms) | Bedroom, Bathroom, Master bedroom, Master Bathroom, Utility Room, Pantry | 16, 17, 19, 21, 23, 24 |

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app, segment IDs can change. Re-run `roborock.get_maps` and update the `segments:` list in both branches of *Household: Vacuum Start Cleaning* — a stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Five helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_evening_max_progress`, `input_number.vacuum_daytime_max_progress` — running maximum progress seen in each zone since the last reset. Needed because a commanded dock resets live progress to 0, but "best coverage achieved today" has to survive that.
- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags.
- `input_select.vacuum_active_zone` (`evening` / `daytime`) — set by *Vacuum Start Cleaning* the moment it commands a job. Exists because live progress and the `returning` trigger are shared across both zones; without recording which zone commanded the current job, the tracking and completion automations couldn't tell a 5-room job's 100% from an 11-room job's 100%.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically on arrival rather than surviving to block a later real departure.

### 3. Build the automations

Five automations, described in the architecture diagram above. Live YAML for each is in `ha/automations/` — this guide does not reproduce it; fetch via `ha_config_get_automation` for the current version. Key design points not obvious from the YAML alone:

- **Vacuum Start Cleaning** merges what could have been two automations (evening start, daytime start) into one `choose` block keyed on `condition: trigger, id: ...`. This is a deliberate departure from an earlier project-wide "avoid combining automations on opposite-state triggers" guideline that no longer reflects the author's preference — see `LESSONS.md` if that guidance resurfaces elsewhere.
- The evening branch's trigger is deliberately *just* "everyone's been asleep for 1 hour," with no clock-time restriction. An earlier draft added a 21:00–05:00 window to guard against a daytime nap accidentally triggering an evening-flavored run — dropped once confirmed `everyone_sleeping` is only ever used at actual bedtime, never naps, so the guard protected against a scenario that can't happen while risking blocking a genuinely early or late bedtime.
- **Vacuum Stops For Occupants** does not call `vacuum.pause` before `vacuum.return_to_base`. Testing showed pausing first makes no difference to whether the job survives — it doesn't, either way — so the extra call and delay were dropped.
- **Vacuum Mark Area Complete** uses different thresholds per zone: Evening requires >95% (open-plan, should reliably finish end-to-end when uninterrupted), Daytime requires >50% (several of those rooms have doors that may be closed, capping achievable progress in a way retrying won't fix — matches the threshold the old apartment's equivalent automation used).
- **Vacuum Daily Reset** fires at 08:00, not midnight. An evening run that starts just after midnight must still see *yesterday's* ran-today flags; a midnight reset would clear them an hour before the evening automation checks them, making it fire every single night regardless of whether the daytime run had already succeeded.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Start Cleaning | `automation.household_vacuum_start_cleaning` | Automation |
| Household: Vacuum Stops For Occupants | `automation.household_vacuum_stops_for_occupants` | Automation |
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
