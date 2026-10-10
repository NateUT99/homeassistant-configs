# Vacuum Cleaning Routine

*Last updated: October 2026*

## Overview

Automates the Roborock Q8 Max Plus (`vacuum.living_room_vacuum`) to clean the house on two
independent schedules: a quiet pass over shared common areas in the evening, and a
whole-house pass during the day whenever the house is empty and hasn't been cleaned yet. Once
a week, on whatever night Avery is away, the evening pass doubles as a mop pass, followed the
next morning by a short master-suite mop while the pad is still fitted. Seven standalone
automations plus two blocks folded into the presence automations implement the whole routine,
each covering one trigger source (bedtime, wake, departure, arrival, noon, a fixed clock time,
or the vacuum getting stuck) rather than one physical zone, so that automations doing
tightly-coupled or same-signal work share one entity instead of duplicating conditions across
two. Interrupted daytime jobs restart rather than resume: a commanded dock always cancels the
active Roborock job, and `sensor.<vacuum>_current_room` is too noisy to track room-level
completion — see `LESSONS.md` → *Vacuum & Roborock*.

A stall check, not just the device's own fault reporting, determines whether the vacuum is
genuinely stuck: `binary_sensor.vacuum_stuck` (`ha/packages/vacuum_stuck.yaml`) is on when the
Roborock fault sensor is set, or when the vacuum has been `cleaning` for at least 3 minutes with
`sensor.<vacuum>_cleaning_area` unmoved for that same window — the dual dwell requirement (both
the job's own age and the area sensor) keeps a job's first few seconds, when the area sensor
still holds the previous job's stale timestamp, from reading as an instant stall. The Roborock
integration's own fault state can clear while the unit is still mechanically obstructed — see
`LESSONS.md` → *Vacuum & Roborock*. Both the arrival dock command and the Live Activity's stuck
card key off this sensor rather than the raw fault sensor alone.

## Architecture

```
     ┌──────────────────────────┐   ┌────────────────────────────────┐
     │ Household: Vacuum        │   │ Household: Last Leaves Home    │
     │ Evening Cleaning         │   │ "Start daytime vacuum" block   │
     │ (nightly branch)         │   └───────────────┬────────────────┘
     └────────────┬─────────────┘                   │
                  │                       zone.home -> 0 for 5m
   everyone_sleeping                     (or immediate, override armed),
   on for 1h, or HA restart                     09:00-19:00 window
   recheck after the fact                          ▼
                  ▼                        ┌─────────────────────────┐
        ┌─────────────────────┐            │ fan: max, mop: off       │
        │ fan: quiet          │            │ segments: bedroom, bath, │
        │ mop: off unless     │            │ office, master closet,  │
        │ mop-eligible tonight│            │ + entrance + master bed/│
        │ segments: kitchen,  │            │ bath unless mopped today│
        │ living, pantry,     │            └──────────┬──────────────┘
        │ utility, bathroom,  │                       │
        │ entrance (mop night)│                       │
        │ or kitchen/living/  │                       │
        │ pantry/utility +    │                       │
        │ entrance/bath if    │                       │
        │ Avery away tonight  │                       │
        └──────────┬──────────┘                       │
                   │                                   │
                   └───────────────┬───────────────────┘
                                    ▼
        input_select.vacuum_active_zone = evening | daytime | away | master_mop
        (only "daytime" gates a decision -- the others are a debugging breadcrumb)
                                    │
                                    └─ read by Household: Vacuum Live Activity's
                                       daytime-completion check (below) and its
                                       amber "will restart" branch

     ┌──────────────────────────────────────────────┐
     │ Household: Vacuum Evening Cleaning            │
     │ (morning branch -- same automation, second    │
     │ trigger: everyone_sleeping on -> off, 20s)    │
     └───────────────────────┬──────────────────────┘
       common-area mop already ran this week, master
       suite not yet, pad still on, water not short
                             ▼
              announce 15m grace, re-check pad/water/tank, then:
              fan: balanced, mop: high
              segments: master bedroom (19), master bathroom (21)
                             ▼
              active_zone = master_mop; vacuum_mop_master_suite_done_this_week = on;
              input_datetime.vacuum_master_mop_last_run = today
                             │
                             └─ read by Household: Last Leaves Home's segment-list
                                variable: drops 19 and 21 from that day's daytime run

  Household: Vacuum Reset                           Household: Vacuum Mop Pad Reminders
  triggers: 08:00 daily, 12:00 Mondays               triggers: every 30m from prep_check,
  08:00 clears both ran-today flags, routine-        vacuum re-dock, 17:00, pad removed
  pause, mop-skip-today; 12:00 Monday                latches vacuum_avery_home_tonight every
  additionally clears both weekly mop flags --       20:00-23:59 tick (window opens 19:55,
  split off 08:00 so a Sunday mop's morning           first tick lands 20:00); brackets mop
  follow-up survives a late wake                      night with a prep nudge + cleanup nudge

  Household: First Arrives Home                     Household: Vacuum Live Activity
  (confirmed-arrival block)                         trigger: vacuum state change, error sensor,
  docks the vacuum if mid-run and not stuck,         stuck-sensor change, every 5 min; marks the
  asks to keep/clear the routine-pause flag          daytime zone done once live progress clears
                                                      65% (any trigger, gated to daytime), then
                                                      reconciles -> running/paused/done/stuck/clear.
                                                      Running and returning suppressed while
                                                      everyone_sleeping; the done card still posts,
                                                      but silenced via periodic_tick overnight

  Household: Vacuum Setting Defaults                 binary_sensor.vacuum_stuck
  trigger: pad clips on                              (ha/packages/vacuum_stuck.yaml) -- on when the
  resets mop intensity to high -- undoes             fault sensor is set, OR the vacuum has been
  a manual drop to medium                            cleaning for 3+ minutes with cleaning_area
                                                      unmoved for that same window (the dual dwell
                                                      keeps a fresh job's first seconds -- when the
                                                      area sensor still holds the prior job's stale
                                                      timestamp -- from reading as an instant stall)

                                                      Household: Vacuum Stuck Alert
                                                      trigger: stuck sensor -> on
                                                      TTS-only heads-up, only if someone's
                                                      home and awake
     ┌──────────────────────────┐
     │ Household: Vacuum        │
     │ Midday Prompt            │
     └────────────┬─────────────┘
                  │
   12:00 daily, nobody home, daytime zone not run,
   vacuum docked, pad not attached
                  ▼
        actionable Yes/No prompt (5 min timeout = Yes)
                  ▼
        active_zone = away; fan: max; vacuum.start (whole map --
        no segment list, Stairs excluded by the app's virtual wall only);
        marks BOTH vacuum_ran_daytime and vacuum_ran_evening
        (one daily noon check covers both a missed departure
        edge and an absence of any length, since nothing else
        clears vacuum_ran_daytime except a real clean)
```

### Why "evening" and "daytime" rather than room-set names

The helpers, `active_zone` values, and automation aliases use time-of-day naming — **evening**
= the rooms that clean well at quiet fan speed and sit clear of the bedroom hall (Kitchen,
Living Room, Pantry, Utility Room), **daytime** = the rest (Bedroom, Bathroom, Office, Master
Bedroom, Master Bathroom, Master Closet, Entrance). The Bathroom and Entrance are the exception
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
| Evening (common areas) | Kitchen, Utility Room, Pantry, Living Room, + Bathroom (17) and Entrance (26) on a night Avery is away | 22, 23, 24, 25, [17, 26] |
| Daytime (remaining rooms) | Bedroom, Office, Master Bedroom, Master Closet, Master Bathroom, + Bathroom (17) and Entrance (26) on a day Avery is home | 16, 18, 19, 20, 21, [17, 26] |
| Master suite follow-up (morning after mop night, subset of daytime) | Master Bedroom, Master Bathroom | 19, 21 |
| Whole-house (Midday Prompt's daily backstop) | Entire map, no segment list | — |

The Bathroom (17) and Entrance (26) are never in both lists on the same vacuum-day: the
daytime side reads `binary_sensor.avery_home_today` live (it always runs during the day,
before the date can roll over), and the evening side reads the 20:00-latched
`input_boolean.vacuum_avery_home_tonight` instead — see the midnight-rollover note below and
`LESSONS.md` → *Presence & Device Trackers*.

The master-suite follow-up is not a fourth physical zone — it is two daytime-zone rooms (both
hard floor) that get mopped the morning after mop night while the pad is still fitted, then
dropped from that same day's daytime pass so they aren't cleaned twice. Master Closet (20)
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
> a segment ID is hardcoded — the vacuum-only nightly list in *Household: Vacuum Evening
> Cleaning*, the six-room mop list in `script.household_vacuum_mop_now` (the mop branch calls
> this script rather than carrying its own copy), the daytime list in *Household: Last Leaves
> Home*, and the two-segment master-suite list in *Household: Vacuum Evening Cleaning*'s morning
> branch. A stale ID silently cleans the wrong room or nothing at all.

### 2. Create the helpers

Nine helpers back the routine, all under the `int_vacuum_cleaning_routine` label:

- `input_boolean.vacuum_ran_evening`, `input_boolean.vacuum_ran_daytime` — per-zone daily completion flags. `vacuum_ran_daytime` is set by *Vacuum Live Activity*'s daytime-completion check once live progress clears the threshold, or on command by *Vacuum Midday Prompt*; `vacuum_ran_evening` is set on command by *Vacuum Evening Cleaning* or *Vacuum Midday Prompt*'s whole-house branch. Both are daily, cleared at 08:00 — separate from the weekly mop-completion flags below.
- `input_select.vacuum_active_zone` (`evening` / `daytime` / `away` / `master_mop`) — set the moment a job is commanded. Only `daytime` gates a decision: *Vacuum Live Activity*'s daytime-completion check and its amber "will restart" branch both key off it specifically. `evening`, `away`, and `master_mop` are written on every job but never read back for anything — they exist as a debugging breadcrumb (which zone commanded the vacuum's current or most recent job), not as a control input.
- `input_boolean.vacuum_routine_pause` — a per-trip "I'm stepping out briefly, don't start" flag. Nothing in HA arms it; it's a manual toggle (dashboard or Companion App) flipped on right before a departure that shouldn't start a job. On the next confirmed arrival, *Household: First Arrives Home* pushes **Keep paused** / **Resume**: Resume or no answer within 2 minutes clears it so it never survives to block a later real departure; Keep paused, or leaving again before answering (a quick stop), leaves it armed for the departure that follows. The question is dismissed either way.
- `input_boolean.vacuum_mop_common_areas_done_this_week`, `input_boolean.vacuum_mop_master_suite_done_this_week` — the two weekly mop-completion flags. Since mop night floats to whatever night Avery is away rather than a fixed weekday, these (not a calendar condition) are what stop each half of the mop pass from running more than once a week. *Household: Vacuum Reset* clears both at 12:00 every Monday — deliberately not the daily 08:00 reset, so a Sunday-night mop's morning follow-up isn't cut short by a late wake; see [Step 3](#3-build-the-automations).
- `input_datetime.vacuum_master_mop_last_run` (date only) — the date the master-suite follow-up last completed. *Household: Last Leaves Home* compares this against today's date to drop segments 19/21 from that day's daytime pass. A date, not the `active_zone` select: that select gets overwritten by the very next job commanded (including the daytime pass itself), so it can't reliably answer "did this happen today" once a second job has started.
- `input_boolean.vacuum_mop_skip_today` — cancels that night's prep reminder loop (*Household: Vacuum Mop Pad Reminders*) without touching whether the mop pass itself is eligible. Cleared daily at 08:00 by *Vacuum Reset* so a cancel never bleeds into the next mop-eligible night.
- `input_boolean.vacuum_avery_home_tonight` — the 20:00-latched snapshot of `binary_sensor.avery_home_today`, read by the two automations that can run past midnight (*Vacuum Evening Cleaning*'s nightly branch, *Vacuum Mop Pad Reminders*'s prep nudge). The live sensor is calendar-derived and flips at exactly `00:00:00`; a post-midnight run reading it live would answer for the wrong night. See the coordinated-change note in [Step 1](#1-map-rooms-to-zones) and `LESSONS.md` → *Presence & Device Trackers*.

### 3. Build the automations

Seven standalone vacuum automations (*Vacuum Evening Cleaning*, *Vacuum Reset*, *Vacuum Midday
Prompt*, *Vacuum Mop Pad Reminders*, *Vacuum Live Activity*, *Vacuum Setting Defaults*, *Vacuum
Stuck Alert*), plus two blocks folded into the presence
automations: the daytime-start block in *Household: Last Leaves Home* and the arrival dock +
routine-pause prompt in *Household: First Arrives Home*. All described in the architecture
diagram above. Live YAML for each is in
`ha/automations/` — this guide does not reproduce it. Key design points not obvious from the
YAML alone:

- **The two starts are split, not combined.** Evening cleaning's nightly branch has its own trigger (`everyone_sleeping` on for 1h). Daytime cleaning is a block inside *Household: Last Leaves Home* — it shares nothing operationally with the evening run (different trigger, zone, settings, completion flag) and everything with the rest of the leave-home routine, so it lives there and inherits that automation's 5-minute departure debounce and Immediate Departure override.
- **The daytime block requires the dustbin module to be seated.** With `binary_sensor.living_room_vacuum_water_box_attached` `off`, a start faults immediately with `no_dustbin`, so the block skips instead and pushes *"Daytime clean skipped — the dustbin is not installed"* (tag `vacuum_dustbin_missing`). The push is gated on the clean otherwise being due (not yet run, not paused, 9am–7pm), so a departure with the module out after the day's clean has run stays silent.
- **Vacuum Evening Cleaning owns both halves of the weekly mop event: a nightly branch (common-area pass, sometimes the mop) and a morning branch (the master-suite follow-up).** Both live in one automation with two independently-triggered branches, since they share the same pad/tank cycle and nothing else. A `choose` keyed on trigger id keeps the two branches' conditions from leaking into each other.
- **A restart-recovery trigger backstops the nightly branch** against a state trigger left unarmed by a reload — see that trigger's own `note` in the live YAML for the mechanism.
- **The evening trigger is just "everyone's been asleep for 1 hour," with no clock-time window.** `everyone_sleeping` is only ever used at actual bedtime, never naps, so a time window would only risk blocking a genuinely early or late bedtime.
- **The nightly branch's four fixed segments have no presence gate.** Kitchen, Living Room, Pantry, and Utility Room are on hard flooring that cleans well at quiet fan speed and sits clear of the bedroom hall, so those four run every night regardless of who is home. The Bathroom and Entrance are the two segments gated on presence: the daytime side reads `binary_sensor.avery_home_today` directly (always evaluated during the day), the nightly side reads `input_boolean.vacuum_avery_home_tonight` (latched before the date can roll over) — landing in exactly one list per vacuum-day either way.
- **Vacuum Midday Prompt fires daily at noon whenever the house is empty and the daytime zone hasn't run — one check that covers both a missed departure edge and an absence of any length.** A departure before 08:00 or in the 08:00-09:00 window falls outside *Last Leaves Home*'s block, and nothing else ever clears `vacuum_ran_daytime` except a real clean, so the same noon check catches both. It runs a whole-house `vacuum.start` (see that action's own `note` for the docked/segment-list caveats) rather than a segmented daytime-only clean, since the check can't tell a brief gap from a multi-day absence apart.
- **Vacuum Live Activity also owns the daytime zone's completion check**, folded in from the former Vacuum Progress Tracking automation: any of its own triggers (a status transition or the 5-minute tick) checks whether live progress has cleared 65% while `active_zone` is `daytime`, and marks `vacuum_ran_daytime` on if so. No dedicated progress-sensor trigger or stored running-max helper is needed — `sensor.<vacuum>_cleaning_progress` resets roughly 20 seconds *after* the relevant state transition, not before it (`LESSONS.md` → *Vacuum & Roborock*), so sampling at every transition reliably beats the reset, and the write is sticky once made.
- **Vacuum Reset splits its two clears onto different triggers on purpose.** The daily 08:00 boundary (ran-today flags, routine-pause, mop-skip-today) and the Monday weekly-mop-flag clear don't share a trigger — the weekly clear fires at 12:00 instead, since an 08:00 firing can land before a late wake finishes the master-suite follow-up from a Sunday-night mop, clearing `vacuum_mop_common_areas_done_this_week` out from under it.
- **The master-suite follow-up's segment-list read happens before the next daytime pass overwrites the signal it depends on.** *Household: Last Leaves Home* builds `daytime_segments` from `input_datetime.vacuum_master_mop_last_run` compared against today's date, immediately before setting `active_zone` to `daytime` — the date helper isn't touched by that write, so read-before-write ordering is what makes the drop reliable.
- **Fan speed is set explicitly by every job-starting path, not restored from a prior dock.** *Vacuum Evening Cleaning* sets `quiet`, its master-suite branch sets `balanced`, and *Household: Last Leaves Home* and *Vacuum Midday Prompt* both set `max` — each asserts its own value at its own start rather than depending on what an earlier, unrelated job left behind. *Vacuum Setting Defaults* now owns only mop intensity, resetting it to `high` whenever the pad clips on, since there's no equivalent "explicit at start" moment for that setting the way there is for fan speed.
- **The arrival dock and the routine-pause prompt both live in *Household: First Arrives Home***, on the same confirmed-arrival trigger, rather than the pause handling having its own automation watching raw `zone.home` — this household tracks only Nate (and, when toggled, a guest) via `zone.home`, so `arrival_confirmed` already covers every arrival that matters here.
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

**Rooms.** The mop branch calls `script.household_vacuum_mop_now` for the actual six-room clean
rather than carrying its own copy of the segment list and settings — see [Ad Hoc Mop
Pass](#ad-hoc-mop-pass) for what the script does and why it, not this automation, owns them.
*Vacuum Evening Cleaning* keeps only this branch's own eligibility gate (above) and turns on
`vacuum_ran_evening` immediately after the call — the script deliberately doesn't touch that
flag, since a manual mop pass through the same script must not silently mark the night's
ordinary vacuum pass as done too.

This branch's mop intensity and [the master-suite
follow-up](#master-suite-follow-up-the-next-morning)'s draw on the same 350 ml fill, and there is
no fill-level sensor — only the binary `water_shortage` flag. Watch it across the full cycle and
drop back to `medium` manually if the tank runs dry before the follow-up finishes; *Household:
Vacuum Setting Defaults* only re-forces `high` on the next pad attach, so a mid-cycle manual drop
sticks.

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
still attached"* so the skip is never silent, tagged `vacuum_mop_cleanup` so it clears when the
pad comes off; Midday Prompt self-heals — once the pad comes
off, the noon check runs the clean it skipped. The nightly common-area run covers hard floor
only, so a pad on at bedtime is normally that night's mop prep. Once this week's common-area mop
has already run, though, a pad still attached is a leftover, and the nightly pass skips rather
than drag it through the common areas, with a passive (silent) push tagged `vacuum_mop_cleanup`
so it is waiting in the morning and clears when the pad comes off.

### Master suite follow-up (the next morning)

*Household: Vacuum Evening Cleaning*'s morning branch reuses the pad and water still fitted
from mop night to mop the Master Bedroom and Master Bathroom (segments 19, 21) before the pad
comes off for the day. It triggers 20 seconds after `everyone_sleeping` goes `off` —
day-agnostic, since it gates on `input_boolean.vacuum_mop_common_areas_done_this_week` being
`on` (last night's common-area mop actually happened) and
`input_boolean.vacuum_mop_master_suite_done_this_week` being `off` (this week's follow-up
hasn't run yet), not on a weekday. It also checks the same three hardware conditions as the
common-area branch (pad on, water module seated, tank not empty) plus the usual routine-pause
and not-mid-job guards. It announces a 15-minute grace window on the master bedroom HomePod —
asking both to refill the water tank and to clear the floor, since this is the only branch in
the routine that starts while people are awake — via `script.turn_on` rather than a blocking
call, so a playback error inside the TTS script can't abort the branch before the mop starts.
It then re-checks pad, water module, and water
state (not just before the delay, since fifteen minutes is enough time for someone to pull the
pad off) and starts a segment clean at `fan: balanced` / `mop: high`. Master Closet (segment
20) is never included — it's carpeted.

The branch sets `input_select.vacuum_active_zone` to `master_mop` and turns on
`vacuum_mop_master_suite_done_this_week` and stamps `input_datetime.vacuum_master_mop_last_run`
with today's date on success. The zone value keeps *Vacuum Live Activity*'s daytime-completion
check (gated on `daytime`) from attributing this run to the daytime zone; the date stamp is what *Household:
Last Leaves Home*'s segment-list template reads to drop segments 19 and 21 from that day's
daytime pass. The done flag is what stops the follow-up from re-attempting later the same week;
*Household: Vacuum Reset* clears it every Monday.

At 11:00, if this week's common-area mop has run but the follow-up hasn't, someone is up, and
the pad is still on, the same automation pushes a notification with a **Mop master suite now**
action button (`VACUUM_MASTER_MOP_NOW`). Tapping it re-enters the morning branch, warning
announcement and 15-minute grace included, so a manual start gets the same re-checks. This
covers anything that stops the morning branch: an HA restart during the delay, or a run
aborted by an unexpected error.

Skipping the master bedroom/bathroom from the daytime pass, rather than also mopping them
there, is deliberate: *Household: Last Leaves Home* builds `daytime_segments` from a one-line
conditional list, so the master suite is vacuumed exactly once per day either way.

**The reminders.** *Household: Vacuum Mop Pad Reminders* owns the pad lifecycle as one state
machine around the mop-attached sensor:

| Trigger | Fires | Action |
|---|---|---|
| Every 30 minutes, from 20:00 | mop-eligible night (Avery away tonight, week not yet mopped) + not bedtime yet + pad off + someone home + not skipped + not paused | TTS-only prep reminder → whoever's home (`target: auto`); no push |
| `mop_attached` → `on` | — | stops the loop (next 30-minute check simply fails the "pad off" condition) |
| Vacuum re-docks | this week's follow-up already ran + pad still on + vacuum docked + not everyone asleep | push `tag: vacuum_mop_cleanup`; kitchen HomePod TTS if 06:00–21:00 + someone home |
| Hourly on the hour | same as re-dock | kitchen HomePod TTS only, same 06:00–21:00 / someone home gate (repeats until the pad comes off) |
| `mop_attached` → `off` | — | clears the `vacuum_mop_cleanup` banner (cleanup reminder and both pad-blocked skip pushes) and the `vacuum_master_mop_missed` 11:00 push |

The prep half is TTS-only by design — no push, no banner, no action buttons — because
attaching the pad is itself the acknowledgement that stops the loop; a `time_pattern` trigger
re-evaluates every 30 minutes rather than tracking start/stop state, and that same tick is what
latches `input_boolean.vacuum_avery_home_tonight` earlier in the evening (window opens 19:55,
first tick lands 20:00, latch holds through 23:59) — see [Step 2](#2-create-the-helpers). `input_boolean.vacuum_mop_skip_today` cancels the prep loop
for the rest of the day without affecting whether the mop pass itself is eligible —
*Household: Vacuum Reset* clears it at 08:00. The cleanup half fires once the vacuum re-docks
after the follow-up, then repeats hourly on the kitchen HomePod until the pad actually comes off —
a pad left on drags through every later pass, so the reminder is persistent rather than daily.
The whole cleanup branch also requires the vacuum to be `docked`, since
`vacuum_mop_master_suite_done_this_week` turns on when the follow-up starts rather than when it
finishes — otherwise an hourly tick could announce mid-run. It is likewise gated, push included,
on `everyone_sleeping` being off: the evening
pass re-docks around 00:30, and this way the first reminder after a mop night lands when the
morning follow-up re-docks. TTS is further limited to 06:00–21:00 with someone home. The hourly
tick shares the :00 tick with the prep check, so the automation runs `mode: queued` to keep
either from being dropped. Only the re-dock sends the push; it stays on the lock screen until
the pad comes off, so the hourly repeats are spoken only. TTS goes through `script.household_tts_announce`.

## Ad Hoc Mop Pass

`script.household_vacuum_mop_now` is the single implementation of the six-room mop pass —
*Household: Vacuum Evening Cleaning*'s automatic weekly mop branch calls it, and it's equally
callable on demand from a dashboard button or Companion App shortcut, rather than either path
carrying its own copy of the segment list and settings. It checks three hardware interlocks (pad
attached, water module seated, tank not empty) plus one of its own — the vacuum not already
`cleaning` — pushing a message naming which check failed instead of silently no-oping. On
success it sets `active_zone: evening`, `fan: quiet`, and runs `app_segment_clean` on segments
`[17, 22, 23, 24, 25, 26]` (Kitchen, Utility Room, Pantry, Living Room, Bathroom, Entrance — all
six, unconditionally; segment 28/Stairs is never included, backstopped by an app virtual wall).
`mop_mode` is left at its `standard` default, and `select.living_room_vacuum_cleaning_mode` is
never touched — see `LESSONS.md` → *Vacuum & Roborock* for why the select has no observable
effect with the pad off. Mop intensity isn't set here either; *Household: Vacuum Setting
Defaults* forces it to `high` whenever the pad clips on, covering this script along with every
other mop-eligible action in the routine.

The script itself turns `vacuum_mop_common_areas_done_this_week` on, so any run — automatic or
manual — counts as that week's common-area mop. It deliberately leaves `vacuum_ran_evening`
untouched: that flag is the caller's responsibility. *Vacuum Evening Cleaning*'s mop branch turns
it on immediately after the call, so the nightly pass is marked done; a manual run outside that
branch leaves it alone, so that same night's ordinary common-area vacuum pass still runs on its
own schedule. The script does not touch the master-suite follow-up — that stays tied to the pad
still being on the morning after an actual mop night, not to which path started the mop.

## Consumable Resets

The Roborock integration ships four reset buttons (`button.living_room_vacuum_reset_*_consumable`)
disabled by default; they are enabled in the entity registry. `script.household_vacuum_reset_consumable`
takes one field, `consumable` (`air_filter`, `main_brush`, `side_brush`, `sensor`), presses the
matching button, waits 2 s, and calls `homeassistant.update_entity` on the matching
`sensor.living_room_vacuum_*_time_left` — the coordinator otherwise reports the reset only on its
next poll. Holding a Maintenance card in the `home-main` `#vacuum` pop-up calls it, with no
confirmation (see `guides/home_dashboard.md`).

**Filter cleaning** is tracked between replacements. The filter's 150 h life is split into
three 50 h intervals — clean at 100 h and 50 h left, replace at 0 h.
`input_number.living_room_vacuum_filter_left_at_last_clean` stores the filter's hours left at
the last clean; the `filter_clean` option of the script writes it, and the `air_filter`
(replace) option writes it after the reset so the clean timer restarts with a new filter.
Template helper Living Room Vacuum Filter Clean Time Left
(`sensor.living_room_vacuum_filter_clean_time_left`) reports `50 − (stored − current)`. Once
replacement is due or comes before the next clean, it reports the filter's hours left (minimum
0) + 50 instead — the next clean after the replacement — so a replace-due filter never also
shows a clean due. A filter reset done in the Roborock app does not update the stored reading;
hold *Filter clean* once afterward to realign it.

**Maintenance chores.** Household: Vacuum Maintenance Chores
(`automation.household_vacuum_maintenance_chores`) puts due maintenance on the household chore
list (`guides/reminders.md`) so it rides the existing chore surfaces — the Chores badge, the
09:00 push with Mark Done, the chore card:

| Counter reaches 0 h | Chore created |
|---|---|
| `sensor.living_room_vacuum_filter_time_left` | Replace Vacuum Filter |
| `sensor.living_room_vacuum_filter_clean_time_left` | Clean Vacuum Filter |
| `sensor.living_room_vacuum_main_brush_time_left` | Replace Vacuum Main Brush |
| `sensor.living_room_vacuum_side_brush_time_left` | Replace Vacuum Side Brush |
| `sensor.living_room_vacuum_sensor_time_left` | Clean Vacuum Sensors |

- **Due:** a counter dropping to 0 h (or any counter at 0 h on HA start) creates a one-off
  (`oneshot`, not persisted) chore due now, unless that chore is already open.
- **Completed:** the `chore_calendar_status_changed` event (`to_status: completed`) for one of
  these names runs the script for the matching counter, then deletes the chore. Completing
  the chore *is* the reset — mark it done only after the maintenance.
- **Reset elsewhere:** a counter rising above 0 h (dashboard hold, Roborock app) deletes its
  open chore, so a chore never outlives the work.

Chores are matched by name, so the names in the automation's `items` map must not be
reused for other chores.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Vacuum Evening Cleaning | `automation.household_vacuum_evening_cleaning` | Automation (nightly common-area pass + next-morning master-suite follow-up) |
| Household: Vacuum Mop Now | `script.household_vacuum_mop_now` | Script (ad hoc mop pass over the six common-area rooms) |
| Household: Vacuum Maintenance Chores | `automation.household_vacuum_maintenance_chores` | Automation (maintenance due → chore; chore done → reset) |
| Household: Vacuum Reset Consumable | `script.household_vacuum_reset_consumable` | Script (reset one consumable counter, or mark the filter cleaned, and refresh its sensor) |
| Living Room Vacuum Filter Left At Last Clean | `input_number.living_room_vacuum_filter_left_at_last_clean` | Helper (filter hours left recorded at the last clean) |
| Living Room Vacuum Filter Clean Time Left | `sensor.living_room_vacuum_filter_clean_time_left` | Template helper (hours until the filter's next clean) |
| Reset air filter / main brush / side brush / sensor consumable | `button.living_room_vacuum_reset_*_consumable` | Button ×4 (enabled; disabled by default by the integration) |
| Household: Last Leaves Home | `automation.household_last_leaves_home` | Automation (contains the daytime-start block) |
| Household: First Arrives Home | `automation.household_first_arrives_home` | Automation (contains the arrival dock and vacuum routine-pause prompt) |
| Household: Vacuum Reset | `automation.household_vacuum_reset` | Automation (daily 08:00 flag reset + Monday 12:00 weekly mop reset) |
| Household: Vacuum Midday Prompt | `automation.household_vacuum_midday_prompt` | Automation (noon prompt for a whole-house catch-up clean) |
| Household: Vacuum Mop Pad Reminders | `automation.household_vacuum_mop_pad_reminders` | Automation (prep + cleanup nudges, plus the Avery-tonight latch) |
| Household: Vacuum Live Activity | `automation.household_vacuum_live_activity` | Automation (iOS Lock Screen card, covers every job-start path; also marks the daytime zone done) |
| Household: Vacuum Stuck Alert | `automation.household_vacuum_stuck_alert` | Automation (TTS heads-up when the vacuum is stuck and someone's home and awake) |
| Household: Vacuum Setting Defaults | `automation.household_vacuum_setting_defaults` | Automation (resets mop intensity to high on pad attach) |
| Live Activity dispatch | `script.household_live_activity` | Script |
| TTS dispatch | `script.household_tts_announce` | Script |
| Vacuum Stuck | `binary_sensor.vacuum_stuck` | Template sensor (`ha/packages/vacuum_stuck.yaml`, repo-authoritative) |
| Vacuum Ran Evening | `input_boolean.vacuum_ran_evening` | Helper |
| Vacuum Ran Daytime | `input_boolean.vacuum_ran_daytime` | Helper |
| Vacuum Active Zone | `input_select.vacuum_active_zone` | Helper |
| Vacuum Routine Pause | `input_boolean.vacuum_routine_pause` | Helper |
| Vacuum Mop Common Areas Done This Week | `input_boolean.vacuum_mop_common_areas_done_this_week` | Helper |
| Vacuum Mop Master Suite Done This Week | `input_boolean.vacuum_mop_master_suite_done_this_week` | Helper |
| Vacuum Mop Skip Today | `input_boolean.vacuum_mop_skip_today` | Helper |
| Vacuum Master Mop Last Run | `input_datetime.vacuum_master_mop_last_run` | Helper |
| Vacuum Avery Home Tonight | `input_boolean.vacuum_avery_home_tonight` | Helper |

## Related Files

| Repo Path | Deployed Location | Purpose |
|---|---|---|
| `ha/packages/vacuum_stuck.yaml` | `/config/packages/vacuum_stuck.yaml` | `binary_sensor.vacuum_stuck` template sensor — repo-authoritative, deployed via `scp`, see [Source of Truth](../CLAUDE.md#source-of-truth) |

## Related Documents

- `standards/automations.md` — automation naming, category, and label conventions applied here
- `guides/live_activities.md` — `script.household_live_activity` field contract and status palette used by *Household: Vacuum Live Activity*
- `guides/chime_tts.md` — `script.household_tts_announce` field contract used by the mop-night prep, grace-window, and cleanup announcements
- `guides/presence_tracking.md` — `zone.home` as the presence source and the confirmed-arrival pattern *Household: First Arrives Home* consumes
- `LESSONS.md` → *Vacuum & Roborock* — the underlying Roborock behavior (dock-cancels-job, job-relative progress, `current_room` unreliability, `get_maps` merge lag, `vacuum.start`'s dock-command overload) this design is built around
- `LESSONS.md` → *Presence & Device Trackers* — the all-day-calendar-event midnight rollover this design's Avery-tonight latch works around

## Troubleshooting

**Evening common-area pass doesn't start.** Do Not Disturb is on 20:00–08:00 on this unit, overlapping the evening window. Roborock DND is expected to allow commanded starts (only blocking scheduled cleans and auto-resume) while muting voice prompts. If a night consistently fails to start with no other condition explaining it, check whether DND is silently blocking the `app_segment_clean` command, and narrow the DND window if so rather than toggling DND off around the run.

**`vacuum_ran_daytime` never flips on despite the vacuum apparently finishing.** Check `input_select.vacuum_active_zone` at the time the job completed — if a job was started manually outside these automations (e.g., from the Roborock app), the active-zone helper won't reflect it, and *Vacuum Live Activity*'s daytime-completion check will silently attribute progress to whichever zone the helper happened to already be set to. (`vacuum_ran_evening` can't hit this the same way — it's set when a job is commanded, not when it finishes.)

**The nightly pass or the mop branch ran on the wrong night relative to Avery's calendar.** Check `input_boolean.vacuum_avery_home_tonight` against `binary_sensor.avery_home_today` at the time the pass fired — if they disagree, the latch window (opens 19:55, first tick 20:00, holds through 23:59) in *Vacuum Mop Pad Reminders* may not have ticked (an HA restart landing exactly at a tick boundary, or a config reload disabling that automation briefly) between the last correct snapshot and the run. The window is self-healing on the next tick; a single missed night should self-correct the following evening.

**Midday Prompt fires every day of a long trip instead of going quiet.** By design — the noon check is the only mechanism for an extended absence, and it has no memory of a previous "No." Tapping "No" skips that day's cleaning; the next noon prompt asks again regardless of how many days the house has been empty.

**Midday Prompt's whole-house clean doesn't start even though the vacuum looks idle.** Check `vacuum.living_room_vacuum`'s state is exactly `docked`, not merely not-`cleaning` — `vacuum.start` sends a dock command (`APP_CHARGE`) instead of cleaning if the vacuum is `returning`, and an autonomous mid-job recharge also reads `docked` while `binary_sensor.living_room_vacuum_cleaning` stays `on`. Both conditions must hold.

**The master-suite follow-up skips with "the water module isn't seated."** The 2-in-1 dustbin + water module was pulled to refill the tank and hasn't been reseated by the time the 15-minute grace window elapses. Reseat it before the window closes. The follow-up doesn't retry on its own, but if it still hasn't run by 11:00 a push offers a **Mop master suite now** button.

**Arrival doesn't dock the vacuum even though it looks like it's cleaning.** Check `binary_sensor.vacuum_stuck` — *Household: First Arrives Home* deliberately withholds `return_to_base` while it's `on` and pushes a notification instead, since commanding a stuck vacuum to move just adds another movement command on top of whatever it's caught on. Clear the physical obstruction first; the sensor drops back to `off` within a minute of real progress resuming.
