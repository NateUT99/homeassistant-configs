# Vacuum Cleaning Routine

*Last updated: August 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two independent schedules: a quiet overnight pass over shared common areas, and a full-speed pass over the remaining rooms when the house empties out during the day. Each schedule targets a fixed set of rooms, tracks its own daily completion state, and never references the other's progress.

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
        on for 1h          │                │  (or simulate_away on)
                           ▼                ▼
              ┌─────────────────────┐  ┌─────────────────────────┐
              │ Common Areas branch │  │ Remaining Rooms branch  │
              │ fan: quiet          │  │ fan: max                │
              │ mop: off            │  │ mop: medium              │
              │ segments: office,   │  │ segments: bedroom, bath, │
              │ dining, living,     │  │ master bed, master bath, │
              │ entrance, kitchen   │  │ utility, pantry          │
              └──────────┬──────────┘  └──────────┬──────────────┘
                         │                         │
                         ▼                         ▼
              input_select.vacuum_active_zone = common | remaining
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
        │    common -> vacuum_common_areas_ran_today = on   │
        │    remaining -> vacuum_ran_today = on              │
        └────────────────────────────────────────────────┘

  Household: Vacuum Stops For Occupants           Household: Vacuum Daily Reset
  triggers: arrival, simulated arrival,            trigger: 08:00 daily
            someone wakes mid-run                  clears both ran-today flags,
  docks the vacuum (cancels the job --              both max-progress numbers,
  expected on this hardware) and clears             and the routine-pause flag
  vacuum_routine_pause
```

### Why resume isn't used

The original design goal was "pick up where it left off after an interruption," matching the old apartment. Live testing on this unit (2026-08-25) ruled that out conclusively: **any manually issued dock command cancels the active cleaning job**, whether it was paused first or not, and whether the job was a whole-house clean or a room-scoped segment clean. Three separate tests confirmed this — see `LESSONS.md` → *Vacuum & Roborock* for the details and Roborock's own documentation, which states the same thing.

A follow-up design tracked which rooms a segment clean had *already* finished, so an interrupted job could resume at room granularity next time. That also broke down: `sensor.<vacuum>_current_room` flips back and forth between adjacent open-plan rooms every 30–120 seconds within a single run, so "the robot just left this room" is not a reliable signal that the room is done.

### Why two fixed zones instead of one adaptive schedule

An earlier draft had the night run act as a fallback only when the day run failed, with the day run then "topping up" whatever the night run had missed. This reintroduced the same problem as room-level resume: partial-completion state that has to persist across the 08:00 reset boundary while daytime departures are unpredictable — sometimes the day run never fires because nobody leaves.

The final design sidesteps this by never tracking leftovers at all. **Common Areas** and **Remaining Rooms** are fixed, non-overlapping room sets, each with its own trigger, its own completion flag, and its own max-progress tracker. Bedrooms and bathrooms can only ever be reached during the day regardless of design — noise rules out cleaning them overnight — so the two-zone split isn't a workaround, it's just naming a constraint that was already there.

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
| Common Areas | Office, Dining room, Living room, Entrance, Kitchen | 18, 22, 25, 26, 27 |
| Remaining Rooms | Bedroom, Bathroom, Master bedroom, Master Bathroom, Utility Room, Pantry | 16, 17, 19, 21, 23, 24 |

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app, segment IDs can change. Re-run `roborock.get_maps` and update the `segments:` list in both branches of *Household: Vacuum Start Cleaning* — a stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Six helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_common_areas_max_progress`, `input_number.vacuum_remaining_rooms_max_progress` — running maximum progress seen in each zone since the last reset. Needed because a commanded dock resets live progress to 0, but "best coverage achieved today" has to survive that.
- `input_boolean.vacuum_common_areas_ran_today`, and the pre-existing `input_boolean.vacuum_ran_today` (repurposed as the Remaining Rooms flag) — per-zone daily completion flags.
- `input_select.vacuum_active_zone` (`common` / `remaining`) — set by *Vacuum Start Cleaning* the moment it commands a job. Exists because live progress and the `returning` trigger are shared across both zones; without recording which zone commanded the current job, the tracking and completion automations couldn't tell a 5-room job's 100% from an 11-room job's 100%.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically on arrival rather than surviving to block a later real departure.

### 3. Build the automations

Five automations, described in the architecture diagram above. Live YAML for each is in `ha/automations/` — this guide does not reproduce it; fetch via `ha_config_get_automation` for the current version. Key design points not obvious from the YAML alone:

- **Vacuum Start Cleaning** merges what could have been two automations (night start, day start) into one `choose` block keyed on `condition: trigger, id: ...`. This is a deliberate departure from an earlier project-wide "avoid combining automations on opposite-state triggers" guideline that no longer reflects the author's preference — see `LESSONS.md` if that guidance resurfaces elsewhere.
- **Vacuum Stops For Occupants** does not call `vacuum.pause` before `vacuum.return_to_base`. Testing showed pausing first makes no difference to whether the job survives — it doesn't, either way — so the extra call and delay were dropped.
- **Vacuum Mark Area Complete** uses different thresholds per zone: Common Areas requires >95% (open-plan, should reliably finish end-to-end when uninterrupted), Remaining Rooms requires >50% (several of those rooms have doors that may be closed, capping achievable progress in a way retrying won't fix — matches the threshold the old apartment's equivalent automation used).
- **Vacuum Daily Reset** fires at 08:00, not midnight. An overnight run that starts just after midnight must still see *yesterday's* ran-today flags; a midnight reset would clear them an hour before the overnight automation checks them, making it fire every single night regardless of whether the day run had already succeeded.

### 4. Testing without leaving the house

`input_boolean.vacuum_simulate_away` drives the same trigger paths as the real presence triggers (`on` = departure, `off` = arrival) without touching `zone.home`, so the routine can be exercised from a phone without physically leaving. Kept permanently rather than deleted after initial validation, since the Roborock integration's resume/dock behavior has changed more than once upstream and this is the cheapest way to re-verify after an HA update.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Start Cleaning | `automation.household_vacuum_start_cleaning` | Automation |
| Household: Vacuum Stops For Occupants | `automation.household_vacuum_stops_for_occupants` | Automation |
| Household: Vacuum Track Max Progress | `automation.household_vacuum_track_max_progress` | Automation |
| Household: Vacuum Mark Area Complete | `automation.household_vacuum_mark_area_complete` | Automation |
| Household: Vacuum Daily Reset | `automation.household_vacuum_daily_reset` | Automation |
| Vacuum Common Areas Max Progress | `input_number.vacuum_common_areas_max_progress` | Helper |
| Vacuum Remaining Rooms Max Progress | `input_number.vacuum_remaining_rooms_max_progress` | Helper |
| Vacuum Common Areas Ran Today | `input_boolean.vacuum_common_areas_ran_today` | Helper |
| Vacuum Ran Today | `input_boolean.vacuum_ran_today` | Helper (repurposed: Remaining Rooms flag) |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |
| Vacuum Simulate Away | `input_boolean.vacuum_simulate_away` | Helper |

## Related Documents

- `standards/automations.md` — automation naming, category, and label conventions applied here
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability) this design is built around
- `snapshot/2026-07-27-pre-move/automations/automation.household_vacuum_daily_max_progress.yaml` — the old apartment's max-progress tracking pattern this routine revives, split by zone

## Troubleshooting

**Overnight run doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the overnight window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts — but this was not exhaustively verified against every firmware update. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run (which would un-mute voice prompts mid-run).

**A zone's `ran_today` flag never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Track Max Progress* / *Vacuum Mark Area Complete* will silently attribute progress to whichever zone the helper happened to already be set to.
