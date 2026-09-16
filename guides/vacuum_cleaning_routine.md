# Vacuum Cleaning Routine

*Last updated: September 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two
independent schedules: a quiet pass over shared common areas in the evening, and a
whole-house pass during the day whenever the house is empty and hasn't been cleaned yet. Once
a week, on whatever night Avery is away, the evening pass doubles as a mop pass, followed the
next morning by a short master-suite mop while the pad is still fitted. Six standalone
automations plus two blocks folded into the presence automations implement the whole routine,
each covering one trigger source (bedtime, wake, departure, arrival, noon, or a fixed clock
time) rather than one physical zone, so that automations doing tightly-coupled or same-signal
work share one entity instead of duplicating conditions across two. Interrupted daytime jobs
restart rather than resume: a commanded dock always cancels the
active Roborock job, and `sensor.<vacuum>_current_room` is too noisy to track room-level
completion — see `LESSONS.md` → *Vacuum & Roborock*.

## Architecture

```
     ┌──────────────────────────┐   ┌────────────────────────────────┐
     │ Household: Vacuum         │   │ Household: Last Leaves Home     │
     │ Evening Cleaning          │   │ "Start daytime vacuum" block    │
     │ (nightly branch)          │   └───────────────┬────────────────┘
     └────────────┬─────────────┘                   │
                  │                       zone.home -> 0 for 5m
   everyone_sleeping                     (or immediate, override armed)
   on for 1h, or HA restart                          ▼
   recheck after the fact                  ┌─────────────────────────┐
                  ▼                        │ fan: max, mop: off       │
        ┌─────────────────────┐            │ segments: bedroom, bath, │
        │ fan: quiet          │            │ office, master closet,  │
        │ mop: off unless     │            │ + entrance + master bed/│
        │ mop-eligible tonight│            │ bath unless mopped today│
        │ segments: kitchen,  │            └──────────┬──────────────┘
        │ living, pantry,     │                       │
        │ utility, bathroom,  │                       ▼
        │ entrance (mop night)│        ┌────────────────────────────────────┐
        │ or kitchen/living/  │        │ Household: Vacuum Progress Tracking │
        │ pantry/utility +    │        │ progress ticks -> raise the stored  │
        │ entrance/bath if    │        │ daytime max; returning -> mark      │
        │ Avery away tonight  │        │ vacuum_ran_daytime if max > 65%     │
        └──────────┬──────────┘        │ (merged from two automations)      │
                   │                    └────────────────────────────────────┘
                   ▼
        input_select.vacuum_active_zone = evening | daytime | away | master_mop

     ┌──────────────────────────────────────────────┐
     │ Household: Vacuum Evening Cleaning              │
     │ (morning branch -- same automation, second       │
     │ trigger: everyone_sleeping on -> off, 20s)        │
     └───────────────────────┬──────────────────────┘
       common-area mop already ran this week, master
       suite not yet, pad still on, water not short
                             ▼
              announce 15m grace, re-check pad/water/tank, then:
              fan: balanced, mop: high, vac_and_mop
              segments: master bedroom (19), master bathroom (21)
                             ▼
              active_zone = master_mop; vacuum_mop_master_suite_done_this_week = on;
              input_datetime.vacuum_master_mop_last_run = today
                             │
                             └─ read by Household: Last Leaves Home's segment-list
                                variable: drops 19 and 21 from that day's daytime run

  Household: Vacuum Reset                          Household: Vacuum Mop Pad Reminders
  trigger: 08:00 daily (+ Mondays)                 triggers: every 30m from prep_check,
  clears both ran-today flags, routine-pause,       vacuum re-dock, 17:00, pad removed
  mop-skip-today, daytime max progress; on          latches vacuum_avery_home_tonight every
  Mondays also clears both weekly mop flags         19:55-23:59 tick; brackets mop night with
  (merged from two same-time automations)           a prep nudge and a cleanup nudge

  Household: First Arrives Home                    Household: Vacuum Live Activity
  (confirmed-arrival block)                        trigger: vacuum state change, error sensor,
  docks the vacuum if mid-run, clears the           every 5 min; reconciles ->
  vacuum routine-pause flag                         running/paused/done/error/clear,
                                                     suppressed while everyone_sleeping
     ┌──────────────────────────┐
     │ Household: Vacuum          │
     │ Midday Prompt              │
     └────────────┬─────────────┘
                  │
   12:00 daily, nobody home, daytime zone not run,
   vacuum docked, pad not attached
                  ▼
        actionable Yes/No prompt (5 min timeout = Yes)
                  ▼
        active_zone = away; fan: max, mop: off;
        vacuum.start (whole map -- no segment list,
        Stairs excluded by the app's virtual wall only);
        marks BOTH vacuum_ran_daytime and vacuum_ran_evening
        (one daily noon check covers both a missed departure
        edge and an absence of any length, since nothing else
        clears vacuum_ran_daytime except a real clean)
```

### Why "evening" and "daytime" rather than room-set names

The helpers, `active_zone` values, and automation aliases use time-of-day naming — **evening**
= the rooms that clean well at quiet fan speed and sit clear of the bedroom hall (Kitchen,
Living room, Pantry, Utility Room), **daytime** = the rest (Bedroom, Bathroom, Office, Master
bedroom, Master Bathroom, Master Closet, Entrance). The Bathroom and Entrance are the exception
to a fixed zone assignment — both belong to daytime by default but join evening's segment list
instead on a night Avery is away, so the same two rooms are never wet-mopped and then
dry-vacuumed (or vice versa) the same vacuum-day. Which physical rooms each zone covers lives in
this guide and in each automation's `description`, not in the entity names.

## Prerequisites

- Roborock integration configured, with `vacuum.living_room_vacuum` entity available
- Room map built in the Roborock app, with segment IDs known (`roborock.get_maps` service)
- `input_boolean.everyone_sleeping` already existing as part of the household sleep/presence system
- `binary_sensor.avery_home_today` (a template sensor over `calendar.avery`'s "Avery @ Nate's"
  all-day events) and the Roborock-exposed hardware sensors this design depends on:
  `binary_sensor.living_room_vacuum_mop_attached`, `_water_box_attached`, `_water_shortage`,
  `_cleaning`, and `sensor.living_room_vacuum_cleaning_progress`
- `script.household_tts_announce` for the mop-night prep/cleanup/grace-window announcements
  (see `guides/chime_tts.md`)
- For the weekly mop pass: no-mop zones drawn in the Roborock app over every rug and the entrance doormat (see [Weekly Mop Pass](#weekly-mop-pass)), carpet boost and clean-along-floor-direction enabled, and the mop cloth + mount and 350 ml water tank on hand
- `zone.home` as the presence source (matches the rest of this instance's household automations; see the Coordinated Change note in `standards/automations.md` §3.2 about the eventual migration to `sensor.household_people_home`). The daytime run's departure trigger and 5-minute debounce belong to *Household: Last Leaves Home*, not this routine — see `guides/presence_tracking.md`.

## Steps

### 1. Map rooms to zones

Room segment IDs are read from the Roborock app's map, not derived from anything in HA:

| Zone | Rooms (in segment-ID order) | Segment IDs |
|---|---|---|
| Evening (common areas) | Kitchen (absorbed the former Dining room), Utility Room, Pantry, Living room, + Bathroom (17) and Entrance (26) on a night Avery is away | 22, 23, 24, 25, [17, 26] |
| Daytime (remaining rooms) | Bedroom, Office, Master bedroom, Master closet, Master Bathroom, + Bathroom (17) and Entrance (26) on a day Avery is home | 16, 18, 19, 20, 21, [17, 26] |
| Master suite follow-up (morning after mop night, subset of daytime) | Master bedroom, Master Bathroom | 19, 21 |
| Whole-house (Midday Prompt's daily backstop) | Entire map, no segment list | — |

The Bathroom (17) and Entrance (26) are never in both lists on the same vacuum-day: the
daytime side reads `binary_sensor.avery_home_today` live (it always runs during the day,
before the date can roll over), and the evening side reads the 19:55-latched
`input_boolean.vacuum_avery_home_tonight` instead — see the midnight-rollover note below and
`LESSONS.md` → *Presence & Device Trackers*.

The master-suite follow-up is not a fourth physical zone — it is two daytime-zone rooms (both
hard floor) that get mopped the morning after mop night while the pad is still fitted, then
dropped from that same day's daytime pass so they aren't cleaned twice. Master closet (20)
stays daytime-only; it's carpeted, so a wet pad can never touch it. Which day counts as "today"
for that drop is a date compare against `input_datetime.vacuum_master_mop_last_run`, not the
`active_zone` helper — see [Step 2](#2-create-the-helpers).

*Household: Vacuum Midday Prompt*'s whole-house branch cleans the entire map and carries no
segment list at all — see [Step 3](#3-build-the-automations) for why.

Segment **28 ("Stairs")** is a physical flight of stairs — a fall hazard — and is
**deliberately excluded from every zone and must never be added to a `segments:` list**. A
virtual wall is also placed in front of it in the Roborock app as a hardware-level backstop
independent of this automation.

When confirming a segment ID, don't trust a single `roborock.get_maps` snapshot: after an
app-side merge or rename it can lag reality by hours, and a merge retires the old ID rather
than aliasing it (a retired ID silently no-ops instead of erroring). Confirm the *current* ID
by testing whether `app_segment_clean` targeting it actually starts a job (`state` →
`cleaning`). See `LESSONS.md` → *Vacuum & Roborock*.

> **Coordinated change:** if the map is rebuilt or rooms are re-split in the Roborock app,
> segment IDs can change. Re-run `roborock.get_maps` and update the `segments:` list everywhere
> a segment ID is hardcoded — both branches of *Household: Vacuum Evening Cleaning*'s nightly
> half, the daytime list in *Household: Last Leaves Home*, and the two-segment list in *Household:
> Vacuum Evening Cleaning*'s morning (master-suite) half. A stale ID silently cleans the wrong
> room or nothing at all.

### 2. Create the helpers

Ten helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_number.vacuum_daytime_max_progress` — running maximum progress seen in the daytime zone since the last reset. Needed because a commanded dock (someone arriving home mid-run) resets live progress to 0, but "best coverage achieved today" has to survive that. The evening zone has no equivalent — nothing docks it mid-run, so it is marked done on command rather than on verified coverage.
- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags. `vacuum_ran_daytime` is set by *Vacuum Progress Tracking* once coverage clears the threshold, or on command by *Vacuum Midday Prompt*; `vacuum_ran_evening` is set on command by *Vacuum Evening Cleaning* or *Vacuum Midday Prompt*'s whole-house branch. Both are daily, cleared at 08:00 — separate from the weekly mop-completion flags below.
- `input_select.vacuum_active_zone` (`evening` / `daytime` / `away` / `master_mop`) — set the moment a job is commanded. Live progress and the `returning` trigger are shared across all four values; *Vacuum Progress Tracking* gates on `daytime` specifically, so a job commanded under `evening`, `away`, or `master_mop` can't bump `vacuum_daytime_max_progress` or flip `vacuum_ran_daytime` through that path.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag, cleared automatically by *Household: First Arrives Home* on the next confirmed arrival, so it never survives to block a later real departure.
- `input_boolean.vacuum_mop_common_areas_done_this_week`, `input_boolean.vacuum_mop_master_suite_done_this_week` — the two weekly mop-completion flags. Since mop night floats to whatever night Avery is away rather than a fixed weekday, these (not a calendar condition) are what stop each half of the mop pass from running more than once a week. *Household: Vacuum Reset* clears both every Monday at 08:00.
- `input_datetime.vacuum_master_mop_last_run` (date only) — the date the master-suite follow-up last completed. *Household: Last Leaves Home* compares this against today's date to drop segments 19/21 from that day's daytime pass. A date, not the `active_zone` select: that select gets overwritten by the very next job commanded (including the daytime pass itself), so it can't reliably answer "did this happen today" once a second job has started.
- `input_boolean.vacuum_mop_skip_today` — cancels that night's prep reminder loop (*Household: Vacuum Mop Pad Reminders*) without touching whether the mop pass itself is eligible. Cleared daily at 08:00 by *Vacuum Reset* so a cancel never bleeds into the next mop-eligible night.
- `input_boolean.vacuum_avery_home_tonight` — the 19:55-latched snapshot of `binary_sensor.avery_home_today`, read by the two automations that can run past midnight (*Vacuum Evening Cleaning*'s nightly branch, *Vacuum Mop Pad Reminders*'s prep nudge). The live sensor is calendar-derived and flips at exactly `00:00:00`; a post-midnight run reading it live would answer for the wrong night. See the coordinated-change note in [Step 1](#1-map-rooms-to-zones) and `LESSONS.md` → *Presence & Device Trackers*.

### 3. Build the automations

Six standalone vacuum automations (*Vacuum Evening Cleaning*, *Vacuum Progress Tracking*,
*Vacuum Reset*, *Vacuum Midday Prompt*, *Vacuum Mop Pad Reminders*, *Vacuum Live Activity*),
plus two blocks folded into the presence automations: the daytime-start block in *Household:
Last Leaves Home* and the arrival dock + routine-pause clear in *Household: First Arrives
Home*. All described in the architecture diagram above. Live YAML for each is in
`ha/automations/` — this guide does not reproduce it. Key design points not obvious from the
YAML alone:

- **The two starts are split, not combined.** Evening cleaning's nightly branch has its own trigger (`everyone_sleeping` on for 1h). Daytime cleaning is a block inside *Household: Last Leaves Home* — it shares nothing operationally with the evening run (different trigger, zone, settings, completion flag) and everything with the rest of the leave-home routine, so it lives there and inherits that automation's 5-minute departure debounce and Immediate Departure override.
- **Vacuum Evening Cleaning owns both halves of the weekly mop event: a nightly branch (common-area pass, sometimes the mop) and a morning branch (the master-suite follow-up).** Both live in one automation with two independently-triggered branches, since they share the same pad/tank cycle and nothing else. A `choose` keyed on trigger id keeps the two branches' conditions from leaking into each other.
- **A restart-recovery trigger backstops the nightly branch** against a state trigger left unarmed by a reload — see that trigger's own `note` in the live YAML for the mechanism.
- **The evening trigger is just "everyone's been asleep for 1 hour," with no clock-time window.** `everyone_sleeping` is only ever used at actual bedtime, never naps, so a time window would only risk blocking a genuinely early or late bedtime.
- **The nightly branch's four fixed segments have no presence gate.** Kitchen, Living room, Pantry, and Utility Room are on hard flooring that cleans well at quiet fan speed and sits clear of the bedroom hall, so those four run every night regardless of who is home. The Bathroom and Entrance are the two segments gated on presence: the daytime side reads `binary_sensor.avery_home_today` directly (always evaluated during the day), the nightly side reads `input_boolean.vacuum_avery_home_tonight` (latched before the date can roll over) — landing in exactly one list per vacuum-day either way.
- **Vacuum Midday Prompt fires daily at noon whenever the house is empty and the daytime zone hasn't run — one check that covers both a missed departure edge and an absence of any length.** A departure before 08:00 or in the 08:00-09:00 window falls outside *Last Leaves Home*'s block, and nothing else ever clears `vacuum_ran_daytime` except a real clean, so the same noon check catches both. It runs a whole-house `vacuum.start` (see that action's own `note` for the docked/segment-list caveats) rather than a segmented daytime-only clean, since the check can't tell a brief gap from a multi-day absence apart.
- **Vacuum Progress Tracking and Vacuum Reset each combine two automations' worth of tightly-coupled or same-signal work into one entity.** Progress Tracking combines what writes the daytime max-progress number with what reads it to mark the zone done; Reset combines the daily 08:00 flag-clear with the Monday-only weekly mop-flag clear, since both fire at the identical boundary for the identical reason (a run landing just after midnight must still see yesterday's/last week's flags as done).
- **The master-suite follow-up's segment-list read happens before the next daytime pass overwrites the signal it depends on.** *Household: Last Leaves Home* builds `daytime_segments` from `input_datetime.vacuum_master_mop_last_run` compared against today's date, immediately before setting `active_zone` to `daytime` — the date helper isn't touched by that write, so ordering no longer matters the way it did under the old `active_zone`-based check.
- **The arrival dock and the routine-pause clear both live in *Household: First Arrives Home***, on the same confirmed-arrival trigger, rather than the pause-clear having its own automation watching raw `zone.home` — this household tracks only Nate (and, when toggled, a guest) via `zone.home`, so `arrival_confirmed` already covers every arrival that matters here.
- **Vacuum Mop Pad Reminders also owns the Avery-tonight latch**, piggybacked on the `time_pattern` trigger it already runs every 30 minutes — see that action's own `note` for the window and why it's self-healing.
- **Segment order in `app_segment_clean` does not determine cleaning route.** The robot path-plans from its own position, not the array order — no need to sort segment lists.

## Weekly Mop Pass

Any night Avery is away, the evening pass mops the common areas' hard floor instead of only
vacuuming it — there is no fixed mop weekday. It is folded into *Household: Vacuum Evening
Cleaning*'s nightly branch as a second `choose` branch, not a separate automation — same
trigger, same fan speed, same "evening" zone and completion flag.

**What decides which branch runs.** The mop branch is taken only when *all* of these hold: it's
a night Avery is away (`input_boolean.vacuum_avery_home_tonight` is `off`), this week's
common-area mop hasn't happened yet (`input_boolean.vacuum_mop_common_areas_done_this_week` is
`off`), the mop pad is fitted (`binary_sensor.living_room_vacuum_mop_attached`), the 2-in-1
dustbin + water module is seated (`binary_sensor.living_room_vacuum_water_box_attached`), and
the tank is not empty (`binary_sensor.living_room_vacuum_water_shortage` is `off`). The pad
sensor is the opt-in on a mop-eligible night — forget to prep and the run silently falls back
to the vacuum-only branch, and that week's mop opportunity is gone until the next night Avery
is away. The push message names which branch ran, so the notification itself confirms whether
prep landed. On the Q8 Max the dust bin and water tank are one combined module and the
integration exposes no dedicated "dust bin installed" sensor, so `water_box_attached` doubles
as the check that the rear cavity is occupied.

**Rooms.** Segments `[17, 22, 23, 24, 25, 26]` — Kitchen, Utility Room, Pantry, Living room,
Bathroom, and Entrance — all six, unconditionally. Unlike the vacuum-only branch (which shifts
the Bathroom and Entrance between zones based on `vacuum_avery_home_tonight`), the mop branch
needs no such gate: mop-night eligibility already requires Avery to be away, so all six rooms
are always safe to include. Segment 28 (Stairs) is never included. Settings for the branch:
`select.living_room_vacuum_mop_intensity` → `high`,
`select.living_room_vacuum_cleaning_mode` → `vac_and_mop`; `mop_mode` is left at its `standard`
default. Fan stays `quiet` — the house is asleep — and this dock only empties dust, so there
is no wash/dry cycle to worry about.

The intensity here and [the master-suite follow-up](#master-suite-follow-up-the-next-morning)'s
own intensity both draw on the same 350 ml fill, and there is no fill-level sensor — only the
binary `water_shortage` flag. Both are set to `high`; watch `water_shortage` across the full
cycle and drop back to `medium` here if the tank runs dry before the follow-up finishes.

**Why weekly, not more often.** Robot mopping is maintenance-level: it keeps a film from
building on hard floor, it does not replace an occasional real mop. Weekly is also the most
that is sustainable when the pad and tank are manual — a twice-weekly chore is one that gets
skipped. Add a second opportunity before shortening the interval toward daily.

**Rug protection is entirely app-side.** The Q8 Max has no mop lift — ultrasonic carpet
recognition ("Rise"/"Avoid") ships only on the S7/S8/Q Revo lines — so a wet pad drags across
any rug it reaches. Marking carpet on the map only drives suction boost. Protection comes from
**no-mop zones drawn over every rug and the entrance doormat** in the Roborock app, sized a few
inches larger than each rug: with the pad attached the robot will not enter a no-mop zone at
all, so those rugs are skipped on mop night and vacuumed on any other night. This is a manual
prerequisite, not something the automation can do. See `LESSONS.md` → *Vacuum & Roborock*.

**The mop-attached interlock on the other jobs.** A damp pad left on after the mop pass would
be dragged across the carpeted Office and all four bedrooms by the daytime clean. So the
daytime block in *Household: Last Leaves Home*, *Household: Vacuum Midday Prompt*'s whole-house
branch, and its 12:00 gate all check `binary_sensor.living_room_vacuum_mop_attached` being
`off`. The daytime block additionally pushes *"Daytime clean skipped — the mop pad is
still attached"* so the skip is never silent; Midday Prompt self-heals — once the pad comes
off, the noon check runs the clean it skipped. The nightly common-area run needs no interlock:
it forces mop intensity `off` on the default branch and covers hard floor only.

### Master suite follow-up (the next morning)

*Household: Vacuum Evening Cleaning*'s morning branch reuses the pad and water still fitted
from mop night to mop the Master bedroom and Master Bathroom (segments 19, 21) before the pad
comes off for the day. It triggers 20 seconds after `everyone_sleeping` goes `off` —
day-agnostic, since it gates on `input_boolean.vacuum_mop_common_areas_done_this_week` being
`on` (last night's common-area mop actually happened) and
`input_boolean.vacuum_mop_master_suite_done_this_week` being `off` (this week's follow-up
hasn't run yet), not on a weekday. It also checks the same three hardware conditions as the
common-area branch (pad on, water module seated, tank not empty) plus the usual routine-pause
and not-mid-job guards. It announces a 15-minute grace window on the master bedroom HomePod —
asking both to refill the water tank and to clear the floor, since this is the only branch in
the routine that starts while people are awake — then re-checks pad, water module, and water
state (not just before the delay, since fifteen minutes is enough time for someone to pull the
pad off) and starts a segment clean at `fan: balanced` / `mop: high`. Master closet (segment
20) is never included — it's carpeted.

The branch sets `input_select.vacuum_active_zone` to `master_mop` and turns on
`vacuum_mop_master_suite_done_this_week` and stamps `input_datetime.vacuum_master_mop_last_run`
with today's date on success. The zone value keeps *Vacuum Progress Tracking* (gated on
`daytime`) from attributing this run to the daytime zone; the date stamp is what *Household:
Last Leaves Home*'s segment-list template reads to drop segments 19 and 21 from that day's
daytime pass. The done flag is what stops the follow-up from re-attempting later the same week;
*Household: Vacuum Reset* clears it every Monday.

Skipping the master bedroom/bathroom from the daytime pass, rather than also mopping them
there, is deliberate: *Household: Last Leaves Home* builds `daytime_segments` from a one-line
conditional list, so the master suite is vacuumed exactly once per day either way.

**The reminders.** *Household: Vacuum Mop Pad Reminders* owns the pad lifecycle as one state
machine around the mop-attached sensor:

| Trigger | Fires | Action |
|---|---|---|
| Every 30 minutes, from 20:00 | mop-eligible night (Avery away tonight, week not yet mopped) + not bedtime yet + pad off + someone home + not skipped + not paused | TTS-only prep reminder → whoever's home (`target: auto`); no push |
| `mop_attached` → `on` | — | stops the loop (next 30-minute check simply fails the "pad off" condition) |
| Vacuum re-docks | this week's follow-up already ran + pad still on | cleanup nudge → auto-resolved HomePod (kitchen, everyone's up) + push `tag: vacuum_mop_cleanup` |
| Time 17:00 daily | this week's follow-up already ran + pad still on | cleanup nudge → kitchen HomePod + same push tag (repeats daily until the pad comes off) |
| `mop_attached` → `off` | — | clears the `vacuum_mop_cleanup` banner |

The prep half is TTS-only by design — no push, no banner, no action buttons — because
attaching the pad is itself the acknowledgement that stops the loop; a `time_pattern` trigger
re-evaluates every 30 minutes rather than tracking start/stop state, and that same tick is what
latches `input_boolean.vacuum_avery_home_tonight` earlier in the evening (19:55–23:59) —
see [Step 2](#2-create-the-helpers). `input_boolean.vacuum_mop_skip_today` cancels the prep loop
for the rest of the day without affecting whether the mop pass itself is eligible —
*Household: Vacuum Reset* clears it at 08:00. The cleanup half fires once the vacuum re-docks
after the follow-up, with a 17:00 backstop that repeats daily until the pad actually comes off.
TTS goes through `script.household_tts_announce`; the cleanup push reuses one tag so a repeat
replaces the banner rather than stacking.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Evening Cleaning | `automation.household_vacuum_evening_cleaning` | Automation (nightly common-area pass + next-morning master-suite follow-up) |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation (contains the daytime-start block) |
| Household: First Arrives Home | `automation.household_first_arrives_home` | Automation (contains the arrival dock and vacuum routine-pause clear) |
| Household: Vacuum Progress Tracking | `automation.household_vacuum_progress_tracking` | Automation (merged from two: max-progress tracking + completion marking) |
| Household: Vacuum Reset | `automation.household_vacuum_reset` | Automation (merged from two: daily flag reset + Monday-only weekly mop reset) |
| Household: Vacuum Midday Prompt | `automation.household_vacuum_midday_prompt` | Automation (merged from two: the noon prompt + the former whole-house away catch-up) |
| Household: Vacuum Mop Pad Reminders | `automation.household_vacuum_mop_pad_reminders` | Automation (prep + cleanup nudges, plus the Avery-tonight latch) |
| Household: Vacuum Live Activity | `automation.household_vacuum_live_activity` | Automation (iOS Lock Screen card, covers every job-start path) |
| Live Activity dispatch | `script.household_live_activity` | Script |
| TTS dispatch | `script.household_tts_announce` | Script |
| Vacuum Daytime Max Progress | `input_number.vacuum_daytime_max_progress` | Helper |
| Vacuum Ran Evening | `input_boolean.vacuum_ran_evening` | Helper |
| Vacuum Ran Daytime | `input_boolean.vacuum_ran_daytime` | Helper |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |
| Vacuum Mop Common Areas Done This Week | `input_boolean.vacuum_mop_common_areas_done_this_week` | Helper |
| Vacuum Mop Master Suite Done This Week | `input_boolean.vacuum_mop_master_suite_done_this_week` | Helper |
| Vacuum Mop Skip Today | `input_boolean.vacuum_mop_skip_today` | Helper |
| Vacuum Master Mop Last Run | `input_datetime.vacuum_master_mop_last_run` | Helper |
| Vacuum Avery Home Tonight | `input_boolean.vacuum_avery_home_tonight` | Helper |

## Related Documents

- `standards/automations.md` — automation naming, category, and label conventions applied here
- `guides/live_activities.md` — `script.household_live_activity` field contract and status palette used by *Household: Vacuum Live Activity*
- `guides/chime_tts.md` — `script.household_tts_announce` field contract used by the mop-night prep, grace-window, and cleanup announcements
- `guides/presence_tracking.md` — `zone.home` as the presence source and the confirmed-arrival pattern *Household: First Arrives Home* consumes
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability, `get_maps` merge lag, `vacuum.start`'s dock-command overload) this design is built around
- `LESSONS.md` → *Presence & Device Trackers* — the all-day-calendar-event midnight rollover this design's Avery-tonight latch works around

## Troubleshooting

**Evening common-area pass doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the evening window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run.

**`vacuum_ran_daytime` never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Progress Tracking* will silently attribute progress to whichever zone the helper happened to already be set to. (`vacuum_ran_evening` can't hit this the same way — it's set when a job is commanded, not when it finishes.)

**The nightly pass or the mop branch ran on the wrong night relative to Avery's calendar.** Check `input_boolean.vacuum_avery_home_tonight` against `binary_sensor.avery_home_today` at the time the pass fired — if they disagree, the 19:55–23:59 latch window in *Vacuum Mop Pad Reminders* may not have ticked (an HA restart landing exactly at a tick boundary, or a config reload disabling that automation briefly) between the last correct snapshot and the run. The window is self-healing on the next tick; a single missed night should self-correct the following evening.

**Midday Prompt fires every day of a long trip instead of going quiet.** By design — since *Vacuum Away Catch-Up* was folded in, this is the only mechanism left for an extended absence, and it has no memory of a previous "No." Tapping "No" skips that day's cleaning; the next noon prompt asks again regardless of how many days the house has been empty.

**Midday Prompt's whole-house clean doesn't start even though the vacuum looks idle.** Check `vacuum.living_room_vacuum`'s state is exactly `docked`, not merely not-`cleaning` — `vacuum.start` sends a dock command (`APP_CHARGE`) instead of cleaning if the vacuum is `returning`, and an autonomous mid-job recharge also reads `docked` while `binary_sensor.living_room_vacuum_cleaning` stays `on`. Both conditions must hold.

**The master-suite follow-up skips with "the water module isn't seated."** The 2-in-1 dustbin + water module was pulled to refill the tank and hasn't been reseated by the time the 15-minute grace window elapses. Reseat it before the window closes, or wait for the next mop night — the follow-up doesn't retry later the same morning.
