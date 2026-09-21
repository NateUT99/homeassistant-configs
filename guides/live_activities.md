# iOS Live Activities

*Last updated: September 2026*

## Overview

`script.household_live_activity` is the single dispatch point for every iOS Live Activity in
this instance — the Lock Screen / Dynamic Island card the companion app renders from a push
carrying `live_update: true` and a stable `tag`. It plays the same role for Live Activities that
`script.household_tts_announce` plays for TTS (`guides/chime_tts.md`): automations describe *what
is happening* (a status, a phase message, a progress number); the script owns *what the card
looks like* (palette, icon default, chrome, the clear/live-update split). Two consumers exist
today — the laundry washer/dryer and the household vacuum — and any future long-running process
becomes a third consumer by calling the script, never by hand-writing a `live_update` payload.

Live Activities are iOS-only; the companion app's Android equivalent (Live Updates) is out of
scope for this instance, which has no Android devices in `CLAUDE.md`'s device list.

## Architecture

```
consumer automations (reconcilers — recompute the whole card from live state, every trigger)
  automation.utility_room_washer_live_activity
  automation.utility_room_dryer_live_activity
  automation.household_vacuum_live_activity
          │
          ▼
script.household_live_activity
  ├── status palette (color + behavior per status)
  ├── payload assembly (progress bar, chronometer, chrome)
  └── status: clear → clear_notification
      status: running/paused/done/attention/error → live_update
          │
          ▼
notify.mobile_app_nates_iphone
          │
          ▼
iOS Lock Screen / Dynamic Island
```

**Design decisions:**

- **Consumers are reconcilers, not event handlers.** Every automation run re-reads live state and
  computes the whole card from scratch — none of the three consumers branch on `trigger.to_state`.
  This means a stale queued tick computes the same payload as a fresh one (safe under
  `mode: queued`), and an HA restart mid-cycle self-heals on the next 5-minute tick instead of
  leaving a stuck card, with no separate recovery path needed.
- **The chronometer does the per-second work on-device; pushes carry only phase changes and coarse
  progress.** iOS throttles and silently drops over-frequent Live Activity updates, and the push
  budget for *creating* an activity fails with no log entry when exhausted — both undiagnosable
  after the fact. Every consumer triggers on the discrete status/state sensor changing, plus a
  `time_pattern: /5` minutes tick while a task may be active — roughly 12 pushes/hour plus a
  handful of transitions, not one per underlying integration poll. The countdown/elapsed timer
  still moves every second, rendered locally by iOS from the `when` field the chronometer carries.
- **One script, one status palette.** `status: running/paused/done/attention/error/clear` maps to
  a fixed color (blue/grey/green/amber/red) so every card in this instance reads consistently
  without each consumer choosing colors. A consumer can still override the color for identity (the
  washer and dryer use different blues/oranges so two stacked cards are distinguishable at a
  glance) — see the palette table below.
- **`status: done` always shows a full bar and drops the chronometer**, regardless of what
  `progress` the caller passed. This lets a consumer signal completion without having to reason
  about whether the underlying sensor's progress reading is trustworthy at that instant — see the
  vacuum Design Decisions below for why that matters concretely.
- **`target` exists for one value today.** Only `nates_iphone` is a registered iOS device in this
  instance (`CLAUDE.md`'s Mac Mini and work laptop notification targets are not iOS). The field and
  the script's target-validation guard exist so a second iOS device is a one-line addition to the
  `choose` block, not a redesign — the same extensibility `script.household_tts_announce` keeps for
  its per-room targets.
- **`ends_at` is read from the source sensor as-is, guarded against `unknown`/`unavailable`.**
  ThinQ's remaining-time sensor already reports an ISO 8601 timestamp (`device_class: timestamp`),
  so no conversion happens in the laundry consumers — only a guard that substitutes an empty
  string when the source is not yet populated, which the script's `chronometer_ref` logic treats
  as "no chronometer" rather than passing a bad value into `as_timestamp()`. `started_at` exists
  in the script for the same purpose on a future consumer with a reliable start timestamp; the
  vacuum consumer tried one and dropped it — see its Design Decisions below.

## Prerequisites

- iOS Companion App 2026.9.1+ on the target device (confirmed installed on Nate's iPhone)
- Home Assistant Core 2026.7.0+ (confirmed: 2026.9.2 installed)
- `notify.mobile_app_nates_iphone` reachable (standard mobile_app integration, already in use for
  other pushes — see `LESSONS.md` on why this native service is required over `notify.send_message`
  for any payload carrying `data`)

## Steps

### 1. `script.household_live_activity`

Built once as the shared dispatch point. Full field contract:

| Field | Required | Default | Description |
|---|---|---|---|
| `tag` | Yes | — | Stable activity ID, kebab-case, ≤64 chars. Same tag = update, not a new card. |
| `status` | Yes | — | `running` / `paused` / `done` / `attention` / `error` / `clear`. |
| `title` | No | — | Static header. **iOS ignores changes after the activity starts** — pass the same value every call. |
| `message` | No | — | Body line — the current phase ("Spinning", "Returning to dock"). |
| `icon` | No | `mdi:home-assistant` | MDI slug. |
| `progress` | No | — | 0–100. Omitted = no progress bar. Forced to 100 when `status: done`. |
| `ends_at` | No | — | ISO 8601 datetime the task finishes → countdown chronometer (only while `status: running`). |
| `started_at` | No | — | ISO 8601 datetime the task began → count-up chronometer. Used only if `ends_at` is absent. |
| `critical_text` | No | — | Short Dynamic Island text. **Ignored whenever a chronometer is active** — the timer replaces it. |
| `color` | No | palette | Hex override of the status palette, for per-consumer identity. |
| `url` | No | `/lovelace/0` | Tap destination — the primary dashboard's auto-generated Overview, until custom dashboard pop-ups exist (see Deferred below). |
| `target` | No | `nates_iphone` | Which iOS device to push to — one option registered today. |
| `periodic_tick` | No | `false` | True when the call is a routine refresh from the consumer's recurring timer tick, not a genuine status change — the script sends it as a lower-priority (APNs 5, not 10), no-alert update that refreshes the Lock Screen/Dynamic Island content in place without the peek/expand animation. A genuine transition should leave this `false` (or omit it) for the normal alert-priority update. Per [companion.home-assistant.io](https://companion.home-assistant.io/docs/notifications/live-activities/), has no effect when starting a brand-new activity, only on updates to one already showing. |

Status palette:

| Status | Color | Behavior |
|---|---|---|
| `running` | `#2196F3` blue | Progress bar + chronometer as supplied |
| `paused` | `#9E9E9E` grey | Bar shown at whatever `progress` was passed, no chronometer |
| `done` | `#4CAF50` green | Bar forced to 100, chronometer dropped |
| `attention` | `#FFA726` amber | Reserved for a future "needs a human" consumer (e.g. mop pad not fitted) — no current consumer uses it |
| `error` | `#EF5350` red | Appliance/robot fault |
| `clear` | — | Sends `clear_notification` for the tag; every other field ignored |

Card chrome is house-standard across every consumer: `background_color: "#101820"` (near-black
with a blue cast), `text_color` left unset so iOS auto-contrasts, `progress_bar_color` inherits
the resolved status/override color, `progress_bar_direction: increasing` whenever `progress` is
set.

### 2. `live_activity` label

Created (green, `mdi:cellphone-arrow-down`) per `standards/automations.md` §3.2's two-step
ID/rename procedure, applied to every automation that calls the script, alongside `notification`
(the script calls `notify.*` transitively) and each consumer's `int_*` integration label.

### 3. Laundry consumers

`automation.utility_room_washer_live_activity` and `automation.utility_room_dryer_live_activity`
— Maintenance category, Utility Room area, labels `int_laundry` + `notification` +
`live_activity`, `mode: queued`. Tags `utility-room-washer` / `utility-room-dryer`; icons
`mdi:washing-machine` / `mdi:tumble-dryer`; identity colors `#2196F3` / `#FF7043` so two stacked
cards are distinguishable.

Each reconciles from live state in this priority order, re-evaluated on every ThinQ status
change, every retrieval `input_select` change, and every 5-minute tick:

| Live state | Card |
|---|---|
| `input_select.utility_room_<appliance>_status` = `alerting`, held 8+ hours | `clear` — stale-alerting fallback, checked ahead of the `done` row below |
| `input_select.utility_room_<appliance>_status` = `alerting` | `done` — "Cycle complete — ready to unload", `critical_text: "Done"` |
| `sensor.utility_room_<appliance>_current_status` = `error` | `error` |
| `current_status` = `pause` | `paused` |
| `current_status` not in `[end, pause, power_off, error, initial]` | `running` — message from the phase-label map below, `progress` from the `_progress` sensor, `ends_at` from the `_remaining_time` sensor |
| `input_select` = `idle` | `clear` |

The card therefore survives cycle-end and stays green until the existing retrieval logic
(`guides/laundry_automation.md`'s occupancy/door detection) flips the `input_select` back to
`idle` — no new state machine was added. A dedicated branch, checked ahead of the `done` branch,
clears the card itself once `alerting` has held for 8 hours straight (`condition: state` with
`for: "08:00:00"`, the same level-based pattern as the vacuum's dock-and-hold `clear` branch
below) — a deliberate fallback for when occupancy/door retrieval never fires (PIR unavailable,
or someone unloads without tripping either sensor), so the card doesn't just sit forever waiting
on iOS's own 8-hour hard expiry to remove it. This is Live-Activity-only: it does not touch
`input_select`, so the TTS nag (`guides/laundry_automation.md`) keeps nagging on its own
sleep/away/re-engagement guardrails regardless of how long the card has been cleared. Faults are
excluded — an unresolved fault keeps its card (and the TTS nag) up until someone actually attends
to it, not silently after 8 hours.

**Every live-update branch passes `periodic_tick: "{{ trigger.id == 'coarse_tick' }}"`** (the
`time_pattern: /5` trigger carries that `id`), not just the running/paused branches the vacuum
consumer silences. Unlike the vacuum's `done`/`error`/`clear` branches, none of these consumers'
branches are trigger-id-guarded — the coarse tick can land on any of them, including a `done`
card sitting untouched for hours waiting to be unloaded, which would otherwise re-expand the
Dynamic Island every 5 minutes for as long as the laundry goes unretrieved. Applying the field
uniformly avoids having to reason about which branches the tick can and can't reach.

**Phase label map.** The raw ThinQ enum is not presentable (`detergent_amount`,
`frozen_prevent_pause`, `rinse_hold`, `wrinkle_care`). Each automation's `variables:` carries a
dict mapping every value of its appliance's `current_status` `options` attribute to a Title Case
label, with `raw_value | replace('_',' ') | title` as the fallback for any value the dict misses:

| Washer raw value | Label | Dryer raw value | Label |
|---|---|---|---|
| `end` | Cycle Complete | `cooling` | Cooling Down |
| `pause` | Paused | `wrinkle_care` | Wrinkle Care |
| `prewash` | Pre-Wash | `running` | Drying |
| `add_drain` | Draining | `end` | Cycle Complete |
| `frozen_prevent_initial` | Anti-Freeze Prep | `power_off` | Off |
| `rinsing` | Rinsing | `error` | Error |
| `running` | Washing | `initial` | Ready |
| `detergent_amount` | Detecting Detergent | `pause` | Paused |
| `frozen_prevent_pause` | Anti-Freeze Pause | | |
| `spinning` | Spinning | | |
| `refreshing` | Refreshing | | |
| `frozen_prevent_running` | Anti-Freeze Cycle | | |
| `drying` | Drying | | |
| `reserved` | Delay Start | | |
| `rinse_hold` | Rinse Hold | | |
| `power_off` | Off | | |
| `detecting` | Detecting Load | | |
| `error` | Error | | |
| `initial` | Ready | | |

The message carries the phase only — never "18 min left." The countdown renders natively from
`ends_at`; duplicating it in the body would be redundant and would force a push every time the
minute changed, which is exactly the update-budget rule this framework exists to avoid.

### 4. Vacuum consumer

`automation.household_vacuum_live_activity` — Routines category, no area (household-scoped),
labels `int_vacuum_cleaning_routine` + `notification` + `live_activity` + `scope_multi_area`,
`mode: queued`. Tag `household-vacuum`, icon `mdi:robot-vacuum`. Deliberately **not** folded into
any of `guides/vacuum_cleaning_routine.md`'s job-start automations — it watches the robot's own
domain entity (`vacuum.living_room_vacuum`) and the shared error sensor, so every job is covered
by one artifact with nothing to keep in sync as that routine's automation count or shape changes.

| Live state | Card |
|---|---|
| `vacuum.living_room_vacuum` = `error`, or `sensor.living_room_vacuum_vacuum_error` ≠ `none` | `error` |
| `cleaning`, `everyone_sleeping` off | `running` — `"{{ zone }} · {{ current_room }}"`, `progress` from `cleaning_progress`, area cleaned as `critical_text` (Dynamic Island) |
| `paused` | `paused` |
| `returning`, `everyone_sleeping` off | `running` — "Returning to dock" |
| transition *into* `docked` from `cleaning`/`returning`/`paused`/`error` | `done` — `"Cleaning finished · {{ area }} m² in {{ minutes }} min"` (edge-triggered — see below) |
| `docked`, held for 10+ minutes | `clear` |
| `cleaning` or `returning` while `everyone_sleeping` is on | no card (branch does not match; falls through) |

- **Sleep suppression is a condition on the running branches only** (`cleaning`, `returning`);
  `paused`, `error`, `done`, and `clear` are ungated. This means the nightly quiet evening pass —
  which starts an hour after `everyone_sleeping` goes on — never creates a Lock Screen card, and
  any card still showing from before bedtime clears itself once the vacuum docks, rather than
  needing an explicit sleeping-edge teardown.
- **The running message describes what the robot is doing, not which schedule started it.**
  `"{{ 'Mop & Vacuum' or 'Vacuum' }} · {{ current_room }}"` reads live off
  `select.living_room_vacuum_cleaning_mode`, paired with `sensor.living_room_vacuum_current_room`
  for the room the robot is in right now. An earlier version mapped `input_select.vacuum_active_zone`
  (`evening`/`daytime`/`away`/`master_mop`) to a human label instead — that broke down twice: it
  couldn't represent an ad hoc manual run (no zone value fits "someone just started this from the
  app"), and it didn't reflect an automated pass silently falling back from mop to vacuum-only when
  the pad wasn't fitted, so the card could say "Evening pass" while dry-vacuuming. Reading
  `cleaning_mode` directly is correct in every case, automated or manual, with no label map to keep
  in sync. `LESSONS.md` → *Vacuum & Roborock* documents that `current_room` flips every 30s–2min at
  open-plan room boundaries, which is fine here — a display-only read updated at most every 5
  minutes — but is exactly why `current_room` was ruled out for *inferring room completion*
  elsewhere in this routine.
- **`critical_text` (area cleaned) is deliberately absent from the running card.** Paired with
  `progress` and no chronometer, it displaced the progress bar on the actual Lock Screen card
  instead of staying confined to the Dynamic Island as the field's own description assumes — see
  `LESSONS.md` → *iOS Live Activities*. The area figure still surfaces on the `done` card's message
  once the job finishes.
- **No chronometer.** The integration exposes no start-of-job timestamp usable for a count-up
  timer — see `LESSONS.md` → *Vacuum & Roborock* for why `last_clean_begin` doesn't work. Progress
  % and the mop/vacuum + room message substitute for a timer instead, rather than capturing our
  own start time into a new helper.
- **The recurring 5-minute tick sends `periodic_tick: true`; genuine transitions don't.** All
  five trigger IDs are named (`state_change`, `job_finished`, `error_change`, `coarse_tick`,
  `progress_complete`), and the running/paused/returning branches pass
  `periodic_tick: "{{ trigger.id == 'coarse_tick' }}"`. The script maps that to a lower-priority
  (APNs 5, not 10), no-alert push, so the Lock Screen and Dynamic Island content still refreshes
  every 5 minutes, but only a genuine state change (job starts, pauses, returns, errors, or
  finishes) triggers the peek/expand animation. Confirmed live on 2026-09-15 — the un-silenced
  tick was re-expanding the Dynamic Island every 5 minutes for the whole duration of a run, which
  read as excessive. `done`/`error`/`clear` don't need the guard here because they're
  edge-triggered off dedicated triggers with a `condition: trigger` guard (see below) — the
  coarse tick structurally can't land on them. The field was originally named `silent`
  (matching the APNs mechanism it sets); renamed to `periodic_tick` when the laundry consumers
  adopted the same pattern, so every consumer states its *intent* ("this is a routine tick") and
  the script alone owns the resulting APNs priority.
- **A dedicated `progress_complete` trigger guarantees a non-silent update near job end, even
  before the robot starts returning.** `cleaning_progress` crossing 99% (`numeric_state`, not
  `state: to: "100"` — progress is non-monotonic, see `LESSONS.md` → *Vacuum & Roborock*) fires
  its own trigger, landing in whichever branch matches the vacuum's state at that instant. Since
  its ID isn't `coarse_tick`, the same silencing rule above already makes it non-silent with no
  extra logic — it only exists so "job's basically done" isn't stuck waiting for the next
  scheduled tick if it lands before the robot's real transition into `returning`.
- **The done card always shows a full bar, with the truth in the message.** A commanded dock
  (someone arriving home mid-run, per `guides/vacuum_cleaning_routine.md`) resets Roborock's live
  progress to 0, so reading `cleaning_progress` at dock time would report a false 0%.
  `cleaning_area` and `cleaning_time` hold the finished job's real totals regardless, and
  `status: done` forcing the bar to 100 (a framework-level behavior, not something this consumer
  had to implement) means the card never contradicts its own message.
- **The `done` card is edge-triggered off a dedicated `job_finished` trigger, not off "currently
  docked."** A named `state` trigger (`from: [cleaning, returning, paused, error]`, `to: docked`)
  plus a `condition: trigger, id: [job_finished]` guard on the `done` branch means the card is
  only (re)created on a genuine job-end transition. An earlier version gated `done` on "state is
  `docked` and hasn't been for 10 minutes yet," which re-fired every time anything — observed:
  the dock's smart auto-empty cycle — knocked the vacuum out of `docked` and back into it; each
  such blip looked like a fresh job finishing and recreated the card after it had already been
  dismissed. See `LESSONS.md` → *Vacuum & Roborock*.
- **The 10-minute clear window still uses a native `condition: state` with `for:`**, not a
  `delay:` inside the run — a `delay:` would hold the `queued` mode's run slot open and could
  fight a new job starting during that window. Unlike the old `done` guard, resending
  `clear_notification` on a spurious re-dock is harmless (it's a no-op against an already-cleared
  tag), so the `for:` heuristic is fine here even though it wasn't safe for `done`.

### 5. Verifying a consumer

Before wiring a new automation to the script, smoke-test the script alone against a throwaway tag
from **Developer Tools → Actions**, stepping through `running` → an in-place update → `done` →
`clear`, and check the Lock Screen and long-press Dynamic Island view after each step. This
isolates script bugs from consumer-logic bugs and is far faster to iterate on than waiting for a
real appliance cycle.

## Adding a new consumer

1. Pick a stable `tag` (kebab-case) that will never collide with another consumer's.
2. Write a reconciler automation, not an event handler: read all relevant live state in
   `variables:`, then a `choose` block that computes one of `running`/`paused`/`done`/`attention`/
   `error`/`clear` from that state — never from `trigger.to_state`. Trigger on every entity whose
   state feeds the `choose` conditions, plus a `time_pattern: /5` minutes (or coarser, if the
   underlying process runs longer) tick while the process may be active.
3. Call `script.household_live_activity` from every branch, including a `clear` branch for the
   terminal/idle state — don't rely on the 8-hour iOS expiry as the only way a card goes away.
   **Gate any one-time "just finished" card on a dedicated edge trigger** (`from: [active states],
   to: terminal state` plus `condition: trigger, id: [...]`), not on "currently in the terminal
   state, recently" — the latter re-fires (and recreates an already-dismissed card) on any blip
   that briefly leaves and re-enters the terminal state. A duration-based `for:` condition is
   fine for a `clear` branch, where resending is a harmless no-op, but not for one that creates
   or updates a card. See the vacuum consumer's Design Decisions above for the concrete failure.
   Name the coarse-tick trigger's `id` (convention: `coarse_tick`) and pass
   `periodic_tick: "{{ trigger.id == 'coarse_tick' }}"` on every live-update branch that trigger
   can reach — if any branch is edge-trigger-guarded against the coarse tick (like the vacuum's
   `done`), the field is unnecessary there but harmless to include anyway.
4. **If the process has no reliable completion/retrieval signal** (or one that can fail to fire —
   an unavailable sensor, a step a person can skip), add a fallback max-age clear branch: a
   level-based `condition: state` with `for:` on the entity the `done`/`running` branches key off,
   checked immediately ahead of the branch it's meant to expire. This is a per-consumer policy
   decision, not something the shared script owns — see the vacuum's 10-minute dock-hold and the
   laundry consumers' 8-hour alerting-hold above for the two worked examples, and don't route this
   through the underlying process's own state machine if doing so would have side effects the card
   alone shouldn't cause (the laundry consumers deliberately clear the card without touching
   `input_select`, so the TTS nag in `guides/laundry_automation.md` is unaffected).
5. Apply the `live_activity` label plus `notification` plus the consumer's own `int_*` label.
6. Add the automation to `ha/automations/`, and add a Related HA Config row plus a short
   Architecture note to the guide that owns the underlying process — this guide only owns the
   dispatch script and its palette, not what triggers each consumer.
7. Smoke-test per Step 5 above before wiring to real triggers.

The dishwasher (`ha/packages/dishwasher_running.yaml`) is the next natural candidate — not built
in this pass.

## Deferred

- **Dashboard tap targets.** Every card's `url` is the default `/lovelace/0` (the primary
  dashboard) rather than a specific pop-up. `guides/mobile_dashboard.md` specs a `#laundry`
  pop-up and already has a `#vacuum` pop-up built; once dashboard work resumes, both consumers'
  `url` fields become one-line additions (`/lovelace/mobile-home#laundry`,
  `/lovelace/mobile-home#vacuum`).
- **`attention` status has no consumer yet.** Reserved for a future case where a Live Activity
  should prompt a human action rather than report progress — the weekly mop pass's pad/water
  checks (`guides/vacuum_cleaning_routine.md`) are the most likely first user, but that automation
  already has its own push-based reminder system (`automation.household_vacuum_mop_pad_reminders`)
  and wasn't changed in this pass.

## Related HA Config

| Friendly Name | Entity / ID | Type |
|---|---|---|
| Live Activity Dispatch | `script.household_live_activity` | Script — shared entry point for every consumer |
| Utility Room: Washer Live Activity | `automation.utility_room_washer_live_activity` | Automation |
| Utility Room: Dryer Live Activity | `automation.utility_room_dryer_live_activity` | Automation |
| Household: Vacuum Live Activity | `automation.household_vacuum_live_activity` | Automation |
| Live Activity label | `live_activity` | Label |

## Related Documents

- `guides/chime_tts.md` — the dispatch-script pattern this mirrors, including the "call the
  script, not the underlying service" rule
- `guides/laundry_automation.md` — the ThinQ entity set and retrieval `input_select` state
  machine the washer/dryer consumers read
- `guides/vacuum_cleaning_routine.md` — the job-start automations and the zone/error sensors the
  vacuum consumer reads
- `guides/mobile_dashboard.md` — future home of the `#laundry` pop-up and the existing `#vacuum`
  pop-up, once tap targets move off the default dashboard
- `standards/automations.md` §3.2 — the `live_activity` label definition and the two-step label
  creation procedure
- `LESSONS.md` → *Vacuum & Roborock* — why `current_room` isn't used for the vacuum card's message

## Troubleshooting

**A card never appears, with a clean automation trace.** iOS's push budget for *creating* a new
Live Activity is separate from its update budget and fails silently with no log entry when
exhausted — see the companion app documentation. This is the first suspect over anything in the
automation or script; there is no HA-side signal that distinguishes it from a delivered-but-slow
push.

**A card is stuck showing a stale phase.** Confirm the consumer automation is enabled and check
its most recent trace (`ha_get_automation_traces`) for which `choose` branch fired — a stale card
usually means the entity it watches went `unavailable` and the automation's conditions all failed,
falling to the `default: []` no-op branch rather than any status branch. The next 5-minute tick
self-heals once the entity recovers.

**The laundry countdown looks wrong.** Confirm
`sensor.utility_room_<appliance>_remaining_time` holds a valid ISO 8601 timestamp in
**Developer Tools → States**, not `unknown`/`unavailable` — the consumer's guard substitutes an
empty string in that case, which disables the chronometer entirely rather than passing a bad
value to the script. Before trusting any other sensor as a chronometer source for a new
consumer, confirm it updates at the *start* of the thing it's timing, not the end — see the
vacuum's Design Decisions above for a sensor that looked right and wasn't.
