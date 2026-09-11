# Vacuum Cleaning Routine

*Last updated: September 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two
independent schedules: a quiet pass over shared common areas in the evening, and a
full-speed pass over the remaining rooms during the day when the house empties out. Each
schedule targets a fixed set of rooms and records its own daily completion; the two never
reference each other's progress or state.

The evening pass is its own automation (*Household: Vacuum Evening Cleaning*). The daytime
pass is a block inside *Household: Last Leaves Home*, so it rides that automation's departure
trigger, 5-minute debounce, and Immediate Departure override alongside the garage/lock/
thermostat actions. Docking the vacuum when someone returns mid-run lives in *Household:
First Arrives Home* with the other confirmed-arrival actions. Clearing the routine-pause
flag on arrival is its own automation (*Household: Vacuum Pause Auto-Clear*), triggered by
any rise in `zone.home` occupancy rather than by a confirmed arrival, so it still fires
when someone was already home and no house-empty edge occurred.

Two more automations backstop both schedules against an edge that never arrives. *Household:
Vacuum Midday Prompt* catches a departure the daytime block missed entirely (before 08:00, or
between 08:00 and its 09:00 window) with an opt-out notification. *Household: Vacuum Away
Catch-Up* covers an extended absence, where the evening pass never has a bedtime to trigger on
and the daytime pass's departure edge is long past: once the house has been empty 18 hours, it
runs a single whole-house pass at max fan every day until someone is home, standing in for both
zones at once rather than running either one on its own schedule.

Once a week the evening pass doubles as a **mop pass** over the common areas' hard floor. The
mop pad and the robot's 350 ml water tank are both fitted by hand — nothing about it can run
unattended — so the pass only mops when the pad is actually on, and *Household: Vacuum Mop Pad
Reminders* brackets the night with a prep nudge and a next-morning cleanup nudge. Thursday
morning, *Household: Vacuum Master Mop Pass* reuses that same fitted pad and fill for a short
second pass over the Master bedroom and Master bathroom before the pad comes off — the one
part of the daytime zone that is hard floor and worth mopping while the hardware is already
wet. The full design is in [Weekly Mop Pass](#weekly-mop-pass) below.

The two zones are fixed and non-overlapping because the constraint is physical: the evening
pass runs at quiet fan speed with the house asleep, so it covers only rooms that clean well
at that speed and sit clear of the bedroom hall — Kitchen, Living room, Pantry, Utility Room
— and it runs regardless of who is home. The daytime pass runs at max fan speed and takes
everything else: the bedrooms and bathrooms, the Entrance (the one common-area room within
earshot of the bedroom hall), and the Office (carpeted, so it needs max suction — too loud
for the evening pass). Interrupted jobs restart rather than
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
        │ segments: kitchen,  │        │ segments: bedroom, bath,│
        │ living, pantry,     │        │ office, master closet,  │
        │ utility             │        │ entrance, + master bed/ │
        │                     │        │ bath unless master_mop  │
        │                     │        │ zone already ran        │
        └──────────┬──────────┘        └──────────┬──────────────┘
                   │                              │
                   ▼                              ▼
              input_select.vacuum_active_zone = evening | daytime
                         │
                         ├─ evening: Vacuum Evening Cleaning sets
                         │           vacuum_ran_evening = on the moment it
                         │           commands the job. Nothing docks the
                         │           evening run, so there is no progress
                         │           tracking or completion check.
                         │
                         └─ daytime:
                         ▼
        ┌────────────────────────────────────────────────┐
        │  Household: Vacuum Track Max Progress            │
        │  every progress tick, if active_zone = daytime:  │
        │  raise input_number.vacuum_daytime_max_progress  │
        └────────────────────────────────────────────────┘
                         │
                         ▼  vacuum enters "returning"
        ┌────────────────────────────────────────────────┐
        │  Household: Vacuum Mark Area Complete             │
        │  if daytime and max_progress > 65%:              │
        │    vacuum_ran_daytime = on                        │
        └────────────────────────────────────────────────┘

     ┌───────────────────────────────────────────────────┐
     │ Household: Vacuum Master Mop Pass                    │
     └───────────────────────┬───────────────────────────┘
                             │
       everyone_sleeping on -> off, Thursday, pad still on
       from Wednesday's mop pass, water not short
                             ▼
              announce 5m grace, re-check pad/water, then:
              fan: balanced, mop: high, vac_and_mop
              segments: master bedroom (19), master bathroom (21)
                             ▼
              active_zone = master_mop
                             │
                             └─ read by the daytime block's segment-list
                                variable (Last Leaves Home, Midday Prompt):
                                drops 19 and 21 from that run's segments

  Household: First Arrives Home                   Household: Vacuum Daily Reset
  (confirmed-arrival block)                       trigger: 08:00 daily
  docks the vacuum if mid-run (cancels the        clears both ran-today flags,
  job -- expected on this hardware)               the daytime max-progress number,
                                                  and the routine-pause flag

  Household: Vacuum Pause Auto-Clear
  trigger: zone.home occupancy rises
  clears vacuum_routine_pause on any arrival

     ┌──────────────────────────┐   ┌────────────────────────────────┐
     │ Household: Vacuum         │   │ Household: Vacuum Away          │
     │ Midday Prompt             │   │ Catch-Up                        │
     └────────────┬─────────────┘   └───────────────┬────────────────┘
                  │                                 │
   12:00, nobody home,                   11:00 daily, zone.home = 0
   daytime zone not run,                 for 18h, docked & not cleaning
   not yet an 18h absence                          │
                  ▼                                 ▼
        actionable Yes/No prompt          fan: max, mop: off
        (5 min timeout = Yes)             vacuum.start (whole map --
                  │                       no segment list; Stairs excluded
                  ▼                       by the app's virtual wall only)
        same daytime-zone actions                   │
        as the block above                          ▼
                                          active_zone = away; marks BOTH
                                          vacuum_ran_daytime and
                                          vacuum_ran_evening on command
```

### Why "evening" and "daytime" rather than room-set names

The helpers, `active_zone` values, and automation aliases use time-of-day naming — **evening**
= the rooms that clean well at quiet fan speed and sit clear of the bedroom hall (Kitchen,
Living room, Pantry, Utility Room), **daytime** = the rest (Bedroom, Bathroom, Office, Master
bedroom, Master Bathroom, Master Closet, Entrance). Which physical rooms each zone covers
lives in this guide and in each
automation's `description`, not in the entity names — a room-set name like "remaining rooms"
carries no meaning on its own.

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` entity available
- Room map built in the Roborock app, with segment IDs known (`roborock.get_maps` service)
- `input_boolean.everyone_sleeping` already existing as part of the household sleep/presence system
- For the weekly mop pass: no-mop zones drawn in the Roborock app over every rug and the entrance doormat (see [Weekly Mop Pass](#weekly-mop-pass)), carpet boost and clean-along-floor-direction enabled, and the mop cloth + mount and 350 ml water tank on hand
- `zone.home` as the presence source (matches the rest of this instance's household automations; see the Coordinated Change note in `standards/automations.md` §3.2 about the eventual migration to `sensor.household_people_home`). The daytime run's departure trigger and 5-minute debounce belong to *Household: Last Leaves Home*, not this routine — see `guides/presence_tracking.md`.

## Steps

### 1. Map rooms to zones

Room segment IDs are read from the Roborock app's map, not derived from anything in HA:

| Zone | Rooms (in segment-ID order) | Segment IDs |
|---|---|---|
| Evening (common areas) | Kitchen (absorbed the former Dining room), Utility Room, Pantry, Living room | 22, 23, 24, 25 |
| Daytime (remaining rooms) | Bedroom, Bathroom, Office, Master bedroom, Master closet, Master Bathroom, Entrance | 16, 17, 18, 19, 20, 21, 26 |
| Master mop (Thursday morning, subset of daytime) | Master bedroom, Master Bathroom | 19, 21 |

These IDs are confirmed against `roborock.get_maps`; the app's numbering runs Kitchen 22, Utility Room 23, Pantry 24, Living room 25, Entrance 26.

The master mop set is not a fourth physical zone — it is two daytime-zone rooms (both hard
floor) that get mopped Thursday morning while the pad is still fitted from Wednesday night,
then dropped from that same day's daytime pass so they aren't cleaned twice. Master closet
(20) stays daytime-only; it's carpeted, so a wet pad can never touch it.

*Household: Vacuum Away Catch-Up* cleans the whole map and carries no segment list at all — see
[Step 3](#3-build-the-automations) for why.

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

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app, segment IDs can change. Re-run `roborock.get_maps` and update the `segments:`/`daytime_segments:` list everywhere a segment ID is hardcoded — the evening list in *Household: Vacuum Evening Cleaning*, the daytime list in the "Start daytime vacuum" block of *Household: Last Leaves Home*, the identical daytime list in *Household: Vacuum Midday Prompt*, and the two-segment list in *Household: Vacuum Master Mop Pass*. A stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Five helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_daytime_max_progress` — running maximum progress seen in the daytime zone since the last reset. Needed because a commanded dock (someone arriving home mid-run) resets live progress to 0, but "best coverage achieved today" has to survive that. The evening zone has no equivalent — nothing docks it mid-run, so it is marked done on command rather than on verified coverage.
- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags. `vacuum_ran_daytime` is set by *Vacuum Mark Area Complete* once coverage clears the threshold, or on command by *Vacuum Midday Prompt* or *Vacuum Away Catch-Up*; `vacuum_ran_evening` is set on command by *Vacuum Evening Cleaning* or *Vacuum Away Catch-Up*.
- `input_select.vacuum_active_zone` (`evening` / `daytime` / `away` / `master_mop`) — set the moment a job is commanded. Live progress and the `returning` trigger are shared across all four values; the daytime tracking and completion automations gate on `daytime` specifically, so a job commanded under `evening`, `away`, or `master_mop` can't bump `vacuum_daytime_max_progress` or flip `vacuum_ran_daytime` through that path. `master_mop` doubles as the flag the daytime block's segment-list template reads to drop the master bedroom/bathroom from that day's daytime run — no separate "ran today" boolean was added for the master mop pass, since `Vacuum Daily Reset`'s 08:00 clear would wipe it before the 09:00 daytime window could read it.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically by *Household: Vacuum Pause Auto-Clear* the next time anyone arrives home, so it never survives to block a later real departure.

### 3. Build the automations

Eight standalone vacuum automations (*Vacuum Evening Cleaning*, *Vacuum Track Max Progress*, *Vacuum Mark Area Complete*, *Vacuum Daily Reset*, *Vacuum Pause Auto-Clear*, *Vacuum Midday Prompt*, *Vacuum Away Catch-Up*, *Vacuum Master Mop Pass*), plus two blocks folded into the presence automations: the daytime-start block in *Household: Last Leaves Home* and the arrival dock in *Household: First Arrives Home*. All described in the architecture diagram above. Live YAML for each is in `ha/automations/` — this guide does not reproduce it. Key design points not obvious from the YAML alone:

- **The two starts are split, not combined.** Evening cleaning is its own automation (single `everyone_sleeping` trigger). Daytime cleaning is a block inside *Household: Last Leaves Home* — it shares nothing operationally with the evening run (different trigger, zone, settings, completion flag) and everything with the rest of the leave-home routine, so it lives there and inherits that automation's 5-minute departure debounce and Immediate Departure override.
- **The daytime block's guards double as re-run protection.** *Last Leaves Home* fires twice on an immediate departure (once instantly, once when the 5-minute trigger elapses). The daytime block's `vacuum_ran_daytime` off + "not currently cleaning" conditions make the second pass a no-op — no second job, no duplicate notification.
- **The evening trigger is just "everyone's been asleep for 1 hour," with no clock-time window.** `everyone_sleeping` is only ever used at actual bedtime, never naps, so a time window would only risk blocking a genuinely early or late bedtime.
- **The evening run has no presence gate.** Every room in the evening zone (Kitchen, Living room, Pantry, Utility Room) is on hard flooring that cleans well at quiet fan speed and sits clear of the bedroom hall, so the pass runs every night regardless of who is home. Two common-area rooms sit in the daytime zone instead: the Entrance, which is within earshot of the bedroom hall, and the Office, which is carpeted and needs max suction — too loud to run with the house asleep. The cost is that on a day the house never fully empties, the front-door area and the Office go uncleaned; front-door dirt is the most frequent-cleaning argument there is, and it's accepted as the price of a gate-free evening run. The routine reads `binary_sensor.avery_home_today` in exactly one place — the weekly mop pass adds the Entrance (segment 26, otherwise daytime-only because it borders Avery's room) when she is away for the night.
- **The arrival dock** (in *Household: First Arrives Home*) does not call `vacuum.pause` before `vacuum.return_to_base` — pausing first makes no difference to whether the job survives a dock (it doesn't, either way).
- **Docking only happens on a confirmed arrival.** There is no "someone woke mid-evening-run" dock: the window it would cover (someone up within the ~40 min quiet common-areas pass) is rare and low-noise, and a manual dock from the app or a voice command handles it when it matters.
- **The routine-pause clear is a standalone automation, not part of the confirmed-arrival block.** *Vacuum Pause Auto-Clear* triggers on any increase in `zone.home` occupancy, so it fires on a plain arrival even when another person was already home and no house-empty / confirmed-first-arrival edge ever occurred — the case a solo errand with a guest at home would otherwise miss, leaving the flag to wrongly suppress the next full-household departure. A pause is meant to cover exactly one departure; this guarantees it. `Vacuum Daily Reset`'s 08:00 clear stays as the backstop for a pause set on a day nobody comes home. HA has no native "value increased" trigger, so the "occupancy went up" check is a one-line template comparing `trigger.to_state` to `trigger.from_state`.
- **The evening zone is marked done on command, not on verified coverage.** *Vacuum Evening Cleaning* flips `vacuum_ran_evening` immediately after issuing the segment clean. Nothing in the automation set docks the evening run mid-way (no arrival dock for it, naps excluded from `everyone_sleeping`), so "commanded" and "completed" are effectively the same event — a max-progress helper and a `returning`-time threshold check would add machinery with almost nothing to catch. The flag still matters as a guard: an HA restart re-primes the `everyone_sleeping` "on for 1h" trigger, so without a persistent "already ran today" flag a 2am restart plus an hour of continued sleep would start a second clean overnight. `Vacuum Daily Reset` clears it at 08:00.
- **Vacuum Mark Area Complete only handles the daytime zone**, which *can* be cut short by an arrival dock. It flips `vacuum_ran_daytime` when the vacuum starts `returning` if `vacuum_daytime_max_progress` is >65%. The threshold sits below 100 because several daytime rooms have doors that may be closed, capping achievable coverage in a way retrying won't fix — progress is area-weighted, so a closed small room costs only a few points. Still based on limited real-world data — revisit if daytime runs start landing below 65% on door-closed days.
- **Segment order in `app_segment_clean` does not determine cleaning route.** The robot path-plans from its own position, not the array order — no need to sort segment lists.
- **Vacuum Daily Reset** fires at 08:00, not midnight. An evening run that starts just after midnight (a typical bedtime plus the 1-hour hold can land there) must still see *yesterday's* ran-today flags; a midnight reset would collide with that window. It clears both `vacuum_ran_*` flags, the routine-pause flag, and `vacuum_daytime_max_progress` (the evening zone has no max-progress figure). The two zones' flags are otherwise fully independent.
- **The daytime block's 09:00–19:00 window and the 08:00 reset leave a gap.** A departure before 08:00 is blocked by yesterday's still-set `vacuum_ran_daytime`; one between 08:00 and 09:00 falls outside the time window. Either way there is no second departure edge that day to catch it, so the daytime zone goes uncleaned. *Vacuum Midday Prompt* exists to close this gap, independent of the extended-absence case below.
- **Vacuum Midday Prompt fires at 12:00, opt-out, 5-minute timeout counts as Yes** — reviving the pre-move apartment's `automation.household_vacuum_midday_prompt` against the current two-zone design. It reads `zone.home below 1` (the old `sensor.household_people_home` workaround was never recreated — see `standards/automations.md` §3.2) and gates on `vacuum_ran_daytime` rather than the old tri-state `input_select.vacuum_ran_today`. Its start action is the same fan/mop/segment sequence as the daytime block in *Last Leaves Home*, not a bare `vacuum.start` — `LESSONS.md` records that `vacuum.start` sends a dock command (`APP_CHARGE`) when the robot is `returning`, which the original snapshot automation was exposed to. It uses `notify.mobile_app_nates_iphone`, not the `notify.send_message` path the rest of this routine uses, because only the native mobile_app service carries actionable buttons and the `tag`/`clear_notification` pattern (`LESSONS.md`).
- **Tapping "No" is also how a longer trip is flagged.** HA cannot distinguish a workday-out noon from a vacation-departure noon, so the prompt necessarily fires on both. Dismissing it skips the partial daytime-only clean, leaving the next morning's whole-house Away Catch-Up (below) as the day's one cleaning cycle instead of two partial ones.
- **Vacuum Away Catch-Up handles the case Midday Prompt doesn't: an absence long enough that the house is empty at 11:00 the *next* day.** Its `zone.home = 0 for 18 hours` condition is what keeps the two automations structurally exclusive — 18 hours from an 11:00 run means "empty since before 17:00 yesterday," which also stops a normal workday-out from tripping a whole-house run and wrongly marking the evening zone done. Once triggered, it repeats every day at 11:00 for as long as the house stays empty; there is no rate limit and no separate handoff back to the normal schedule — the moment `zone.home` shows someone home, the condition simply stops passing.
- **Away Catch-Up marks both `vacuum_ran_daytime` and `vacuum_ran_evening`**, since one whole-house pass stands in for both zones on a day neither would otherwise run, and sets `input_select.vacuum_active_zone` to `away` so *Vacuum Track Max Progress* and *Vacuum Mark Area Complete* (both gated on `daytime`) correctly ignore it.
- **Away Catch-Up disables mopping.** The dock empties dust only — there is no dock water tank to refill the onboard 350 ml one — so a run repeating daily against an empty house would run the mop pad dry with nobody there to refill it. It also gates on `binary_sensor.living_room_vacuum_mop_attached` being `off`, so leaving on a trip with the pad still fitted can't trigger a whole-house wet-mop of every bedroom. Dry-vac only while away.
- **Away Catch-Up uses `vacuum.start`, not `app_segment_clean`, and deliberately carries no segment list.** It is the only job in the routine that wants the entire map, and per `LESSONS.md` an app-side map merge *retires* a segment ID rather than aliasing it — a stale list would silently clean nothing on a day nobody is there to notice. `vacuum.start` is immune to that drift. Segment 28 ("Stairs") is excluded from this run by the virtual wall placed in front of it in the Roborock app, not by software — the same wall that already backstops both segment lists above. Because `vacuum.start` is otherwise state-overloaded (see above, `APP_CHARGE` on `returning`), the automation additionally requires `vacuum.living_room_vacuum` to be `docked`; that alone doesn't rule out a mid-job autonomous recharge, which also reads `docked`, so `binary_sensor.living_room_vacuum_cleaning` (reflects `status.in_cleaning`, survives a recharge per `LESSONS.md`) gates alongside it.
- **Vacuum Master Mop Pass is its own automation, not a third branch of Evening Cleaning**, because its trigger (`everyone_sleeping` off, not on) and its zone (a two-room subset of daytime, not evening) share nothing with that automation's structure. It announces a 5-minute grace window before starting — the only pass in the routine that warns ahead of time, since it is the only one that starts while people are awake and might have things on the floor. It re-checks the pad/water/pause conditions after the delay, not only before, since five minutes is enough time for someone to pull the pad off. `fan: balanced` (not `quiet`, not `max`) reflects that the house is awake but both rooms are hard floor; `mop: high` reflects that it is only two small segments, with the actual tank margin resting on Wednesday's intensity, not a Thursday refill — unverified until watched on a live run.
- **The daytime block's segment-list template is the only thing that knows about the master mop pass**, not a condition on the block itself. `Household: Last Leaves Home` and `Household: Vacuum Midday Prompt` each build `daytime_segments` from `active_zone` immediately before setting `active_zone` to `daytime` — order matters, since a `variables:` step renders once, top-to-bottom, and reading `active_zone` after it's been overwritten would always see `daytime`.

## Weekly Mop Pass

One night a week the evening pass mops the common areas' hard floor instead of only vacuuming
it. It is folded into *Household: Vacuum Evening Cleaning* as a second `choose` branch, not a
separate automation — same trigger, same fan speed, same "evening" zone and completion flag.

**What decides which branch runs.** The mop branch is taken only when *all* of these hold on
the scheduled night: the mop pad is fitted (`binary_sensor.living_room_vacuum_mop_attached`),
the 2-in-1 dustbin + water module is seated (`binary_sensor.living_room_vacuum_water_box_attached`),
and the tank is not empty (`binary_sensor.living_room_vacuum_water_shortage` is `off`). The
pad sensor *is* the opt-in — forget to prep and the run silently falls back to the vacuum-only
branch. The push message names which branch ran, so the notification itself confirms whether
prep landed. On the Q8 Max the dust bin and water tank are one combined module and the
integration exposes no dedicated "dust bin installed" sensor, so `water_box_attached` doubles
as the check that the rear cavity is occupied.

**Rooms.** Segments `[22, 23, 24, 25]` — Kitchen, Utility Room, Pantry, Living room — plus the
Entrance (`26`) on nights `binary_sensor.avery_home_today` is `off`. The Entrance is otherwise
daytime-only because it borders Avery's room; the segment list is built in a `variables:` step
so the Avery gate is a one-line change, not a second branch. Segment 28 (Stairs) is never
included. Settings for the branch: `select.living_room_vacuum_mop_intensity` → `high`,
`select.living_room_vacuum_cleaning_mode` → `vac_and_mop`; `mop_mode` is left at its `standard`
default. Fan stays `quiet` — the house is asleep — and this dock only empties dust, so there
is no wash/dry cycle to worry about.

The intensity here and [Household: Vacuum Master Mop Pass](#master-mop-pass-thursday-morning)'s
own intensity both draw on the same 350 ml fill, and there is no fill-level sensor — only the
binary `water_shortage` flag. A run at `medium` here plus a `high` Thursday pass both cleared
without tripping it, so this is now `high` on both nights to see whether one fill still
covers both; watch `water_shortage` across the full Wednesday-to-Thursday cycle and drop back
to `medium` here if the tank runs dry before Thursday's pass finishes.

**Why weekly, not more often.** Robot mopping is maintenance-level: it keeps a film from
building on hard floor, it does not replace an occasional real mop. Weekly is also the most
that is sustainable when the pad and tank are manual — a twice-weekly chore is one that gets
skipped. Add a second night before shortening the interval toward daily.

**Rug protection is entirely app-side.** The Q8 Max has no mop lift — ultrasonic carpet
recognition ("Rise"/"Avoid") ships only on the S7/S8/Q Revo lines — so a wet pad drags across
any rug it reaches. Marking carpet on the map only drives suction boost. Protection comes from
**no-mop zones drawn over every rug and the entrance doormat** in the Roborock app, sized a few
inches larger than each rug: with the pad attached the robot will not enter a no-mop zone at
all, so those rugs are skipped on mop night and vacuumed on the other six. This is a manual
prerequisite, not something the automation can do. See `LESSONS.md` → *Vacuum & Roborock*.

**The mop-attached interlock on the other jobs.** A damp pad left on after the mop pass would
be dragged across the carpeted Office and all four bedrooms by the daytime clean. So the
daytime block in *Household: Last Leaves Home*, *Household: Vacuum Midday Prompt*, and
*Household: Vacuum Away Catch-Up* all gate on `binary_sensor.living_room_vacuum_mop_attached`
being `off`. The daytime block additionally pushes *"Daytime clean skipped — the mop pad is
still attached"* so the skip is never silent; Midday Prompt self-heals — once the pad comes
off, the noon check runs the daytime clean it skipped that morning. The nightly evening runs
need no interlock: they force mop intensity `off` on the default branch and cover hard floor
only.

### Master Mop Pass (Thursday morning)

*Household: Vacuum Master Mop Pass* reuses the pad and water still fitted from Wednesday
night to mop the Master bedroom and Master Bathroom (segments 19, 21) before the pad comes off
for the day. It triggers on `everyone_sleeping` going `off` on a Thursday, gated on the same
three hardware checks as the Wednesday branch (pad on, water module seated, tank not empty)
plus the usual routine-pause and not-mid-job guards. It announces a 5-minute grace window on
the master bedroom HomePod, then re-checks pad and water state (not just before the delay) and
starts a segment clean at `fan: balanced` / `mop: high`. Master closet (segment 20) is never
included — it's carpeted.

The pass sets `input_select.vacuum_active_zone` to `master_mop`, a fourth value alongside
`evening`/`daytime`/`away`. That value does two jobs: it keeps *Vacuum Track Max Progress* and
*Vacuum Mark Area Complete* (both gated on `daytime`) from attributing this run to the daytime
zone, and it's what the daytime block's segment-list template reads to drop segments 19 and 21
from that day's daytime pass — see [Step 3](#3-build-the-automations) for why the template has
to run before the zone select overwrites it.

Skipping the master bedroom/bathroom from the daytime pass, rather than also mopping them
there, is deliberate: `Household: Last Leaves Home` and `Household: Vacuum Midday Prompt` both
build `daytime_segments` from a one-line conditional list, so the master suite is vacuumed
exactly once per day either way.

**The reminders.** *Household: Vacuum Mop Pad Reminders* owns the pad lifecycle as one state
machine around the mop-attached sensor:

| Trigger | Fires | Action |
|---|---|---|
| Time 20:00 on mop night | weekday + someone home + pad off + not paused | prep nudge → kitchen HomePod + push `tag: vacuum_mop_prep` |
| `everyone_sleeping` → `on` that night | weekday + pad off + not paused | prep nudge → master-bedroom HomePod + same push tag |
| `mop_attached` → `on` | — | clears the `vacuum_mop_prep` banner |
| Vacuum re-docks (Thursday) | morning-after weekday + pad still on | cleanup nudge → auto-resolved HomePod (kitchen, everyone's up) + push `tag: vacuum_mop_cleanup` |
| Time 17:00 next day | morning-after weekday + pad still on | cleanup nudge → kitchen HomePod + same push tag (backstop) |
| `mop_attached` → `off` | — | clears the `vacuum_mop_cleanup` banner |

`everyone_sleeping` is set and cleared by hand, so it is the reliable "bedtime" edge; the
bedtime nudge lands with exactly one hour of lead before the run (the run triggers on the same
flag, `for: 1h`). The cleanup nudge moved off the `everyone_sleeping` → `off` edge once the
Master Mop Pass began using that same edge to *start* mopping — it now fires once the vacuum
re-docks after the master mop pass finishes, so the "pull the pad off" announcement can't land
while the robot is still using it. Attaching or removing the pad is the acknowledgement —
there are no action buttons. TTS goes through `script.household_tts_announce`; both push paths
reuse one tag per phase so a repeat replaces the banner rather than stacking.

> **Coordinated change:** the mop night and its reminders are gated on a weekday `or` block
> (Wednesday, or Thursday before 08:00, to cover a past-midnight bedtime). If the mop night
> moves, update the `or` block in the mop branch of *Household: Vacuum Evening Cleaning*, both
> prep/cleanup weekday conditions in *Household: Vacuum Mop Pad Reminders*, and the Thursday
> condition in *Household: Vacuum Master Mop Pass*.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Evening Cleaning | `automation.household_vacuum_evening_cleaning` | Automation |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation (contains the daytime-start block) |
| Household: First Arrives Home | `automation.household_first_arrives_home` | Automation (contains the arrival dock) |
| Household: Vacuum Track Max Progress | `automation.household_vacuum_track_max_progress` | Automation |
| Household: Vacuum Mark Area Complete | `automation.household_vacuum_mark_area_complete` | Automation |
| Household: Vacuum Daily Reset | `automation.household_vacuum_daily_reset` | Automation |
| Household: Vacuum Pause Auto-Clear | `automation.household_vacuum_pause_auto_clear` | Automation |
| Household: Vacuum Midday Prompt | `automation.household_vacuum_midday_prompt` | Automation |
| Household: Vacuum Away Catch-Up | `automation.household_vacuum_away_catch_up` | Automation |
| Household: Vacuum Master Mop Pass | `automation.household_vacuum_master_mop_pass` | Automation |
| Household: Vacuum Mop Pad Reminders | `automation.household_vacuum_mop_pad_reminders` | Automation (prep + cleanup nudges for the weekly mop pass) |
| Vacuum Daytime Max Progress | `input_number.vacuum_daytime_max_progress` | Helper |
| Vacuum Ran Evening | `input_boolean.vacuum_ran_evening` | Helper |
| Vacuum Ran Daytime | `input_boolean.vacuum_ran_daytime` | Helper |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |

## Related Documents

- `standards/automations.md` — automation naming, category, and label conventions applied here
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability, `get_maps` merge lag) this design is built around
- `snapshot/2026-07-27-pre-move/automations/automation.household_vacuum_daily_max_progress.yaml` — the max-progress tracking pattern this routine revives for the daytime zone

## Troubleshooting

**Evening run doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the evening window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run.

**`vacuum_ran_daytime` never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Track Max Progress* / *Vacuum Mark Area Complete* will silently attribute progress to whichever zone the helper happened to already be set to. (`vacuum_ran_evening` can't hit this — it is set when the job is commanded, not when it finishes.)

**Away Catch-Up doesn't fire on the expected day of a trip, or fires a day later than expected.** `condition: state` with `for:` reads the entity's `last_changed`, which an HA restart resets to boot time — a restart partway through an absence makes the house look newly empty for up to 18 more hours, during which Away Catch-Up is suppressed and Midday Prompt may fire in its place instead. The result is one unnecessary partial daytime clean and one prompt notification while away; it self-corrects once 18 hours have passed since the restart. Check `ha_get_automation_traces` for which condition failed before assuming something else is wrong.

**Midday Prompt fires every day of a long trip instead of going quiet after the first day.** By design — it has no memory of a previous "No." Its own `for: {hours: 18}` NOT-condition should take over from Away Catch-Up's matching 18-hour condition the day after departure; if it doesn't, check the same restart scenario above, and check `vacuum_ran_daytime` — Away Catch-Up sets it, and Midday Prompt gates on it being `off`.
