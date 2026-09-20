# Laundry Automation

*Last updated: September 2026*

---

## Overview

Two LG appliances — a washer and dryer — are managed via the `lg_thinq` integration and surface as entity sets in HA. This integration adds a state machine helper per appliance, four template sensors for progress computation, three automations for state management and TTS announcements, and (deferred — see [Future Improvements](#future-improvements)) a dashboard section. When a cycle completes, the system announces on the kitchen HomePod (or master bedroom if Avery is sleeping) every 30 minutes until the laundry is retrieved, and re-announces immediately when the household re-engages after sleep or an absence. If the family room Sonos is playing at announcement time, a push notification also goes to Nate's phone — a busy Sonos there likely means a movie or game loud enough to miss the kitchen announcement over.

A cycle that errors out mid-run (door failed to lock, water supply issue, and similar) is handled as a distinct `fault` state, separate from a normal completion — see [Fault handling](#fault-handling) below.

Every entity ID below reflects the live `sensor.utility_room_*` naming this house's ThinQ registration produced.

---

## Architecture

```
LG ThinQ (lg_thinq integration)
  sensor.utility_room_washer_current_status   (running → ... → end → power_off)
  sensor.utility_room_washer_remaining_time   (ISO 8601 timestamp when cycle ends)
  sensor.utility_room_washer_total_time       (integer minutes, total cycle length)
  event.utility_room_washer_notification      (event entity; event_type: washing_is_complete / error_during_washing)
  event.utility_room_washer_error             (event entity; typed fault code — see Fault handling)
  [mirror: dryer entities]
         │
         ├─► Template Helpers (HA storage)
         │   sensor.utility_room_washer_progress
         │   sensor.utility_room_washer_minutes_remaining
         │   [mirror for dryer]
         │
         └─► Status Manager Automations
             automation.utility_room_washer_status_manager
             automation.utility_room_dryer_status_manager
                    │
         ┌──────────┘
         │
         ▼
  input_select.utility_room_washer_status
  options: idle │ alerting │ acknowledged │ fault
         │
         └─► TTS Announcement Automation
             automation.utility_room_laundry_announcement
             ├── combined message when both appliances alerting
             ├── fault message uses the reported error phrase when recent (see Fault handling)
             ├── kitchen HomePod (default)
             ├── + push to phone if family_room_theater is playing (busy Sonos, unconditional)
             ├── fault while away/asleep: single push instead of waiting, then stop
             └── master bedroom HomePod only (avery_sleeping = on) — no kitchen, no push check

State machine inputs (per status manager):
  current_status → end                                    ──► idle → alerting  (state trigger)
  notification event fires, event_type matches, < 5 min old ──► idle → alerting  (event trigger, backup)
  notification event fires, event_type = error, < 5 min old  ──► any → fault  (generic fault signal)
  typed error event fires, < 5 min old                     ──► any → fault  (specific fault code)
  current_status → running                                ──► any → idle (new cycle)
  utility_room_motion_sensor_occupancy sustained 15s        ──► any → idle (retrieved)
  utility_room_door held open 60s                          ──► any → idle (retrieved, PIR backup)

TTS inputs:
  input_select → alerting or fault          ──► start repeat loop (fault skips the sleep/away gate)
  input_boolean.everyone_sleeping → off     ──► re-trigger if alerting/fault
  zone.home (0 → 1)                         ──► re-trigger if alerting/fault
                                                (waits for garage/front-door entry first)
  → stop: neither alerting/fault │ everyone_sleeping on (no fault) │ nobody home (no fault)

Live Activity inputs (per appliance, independent of the TTS path above):
  current_status, input_select, every 5 min ──► reconcile → running/paused/done/error/clear
                                                 input_select = fault latches error, checked first
                                                 automation.utility_room_<appliance>_live_activity
                                                 see guides/live_activities.md
```

**Design decisions:**

- **`input_select` state machine over booleans.** A single helper with four options (`idle`/`alerting`/`acknowledged`/`fault`) gives the TTS automation and any future dashboard control a single source of truth. Two separate booleans would require template logic everywhere to avoid desync. `acknowledged` is reserved for the dashboard hold-to-acknowledge action documented under Future Improvements — nothing in the current build writes it. `fault` is a peer of `alerting`, not a replacement — see [Fault handling](#fault-handling).

- **Both the status sensor and the notification event trigger the alerting transition.** Live history shows `sensor.utility_room_*_current_status` sits in `end` for only ~30–45 seconds before moving to `power_off` — a narrow window for a state trigger alone to depend on. The `event.utility_room_*_notification` entity (event_type `washing_is_complete` / `drying_is_complete`) is a redundant second path; the `idle`-status precondition on both branches makes them idempotent, so whichever arrives first wins.

  > **Coordinated change:** event entities restore their last event value on every HA restart, re-firing this trigger with a value that may be hours or days old. The event-trigger branch is guarded by a template condition requiring the event's own timestamp (its `state` *is* the ISO timestamp of the last real event) to be within 5 minutes of `now()`. Without this guard, every HA restart after a completed cycle would fire a fresh laundry alert. See `LESSONS.md` → *Automations & YAML*.

- **Dryer triggers on `end` only, not `cooling`.** Although clothes can technically be removed once cooling starts, triggering at `cooling` shows a "done" state while time remaining is still counting down — confusing. The done state appears only when the cycle fully completes.

- **Retrieval clears on sustained occupancy, not a bare door edge.** Two constraints rule out a bare `binary_sensor.utility_room_door` edge: casual door opens (checking on something, walking through) last 3–24 seconds and look identical to a real visit, and the door gets left open for hours at a stretch — during which a cycle finishing produces no edge at all, so the alert would never clear. The primary retrieval signal is `occupancy.detected` on `binary_sensor.utility_room_motion_sensor_occupancy` with `for: 15s` — short enough to catch a quick retrieval, long enough to filter PIR noise. `door.opened` with `for: 60s` is an independent backup for when the PIR is unavailable, not combined with occupancy via AND: requiring a *fresh* door-open edge alongside occupancy would miss a retrieval where the door was already open when someone walked in.

  > **Known limitation, not fixed by tuning the threshold.** Both status managers watch the same door and occupancy sensors — there's only one utility room for two appliances. Opening the door to tend one appliance clears an unrelated alert on the other, since neither automation can tell which appliance a visit was for. This exists independent of the occupancy duration; only per-appliance sensors (see [Not built — deferred](#not-built--deferred)) actually fix it.

- **TTS re-triggers on re-engagement.** The announcement automation uses `mode: restart` and fires on three triggers: `input_select → alerting`, `everyone_sleeping → off`, and `zone.home` crossing 0→1. Sleep and away stop TTS but leave the visual (`input_select`) at `alerting`. When the household re-engages, the automation restarts and fires immediately rather than waiting up to 30 minutes for the next loop iteration.

- **Arrival entry-grace lives in the shared script's caller, not the script itself.** The garage/front-door wait before an arrival-triggered announcement is `standards/automations.md` §5.10, applied directly in this automation (not inside `script.household_tts_announce`) — any TTS-and-arrival automation gets the same block. The script's own job is only "speak this message at this target"; deciding *whether* and *when* to speak stays in the calling automation.

- **Family room awareness is a push notification, not a TTS target.** `script.household_tts_announce` cannot reach the family room Sonos (`media_player.family_room_theater`) — the playback command produces no audio (see `LESSONS.md` → TTS & Media). The requirement is met more simply anyway: one `script.household_tts_announce` call to `kitchen`, then an unconditional check of `media_player.family_room_theater`'s `state` (no script involvement) that pushes to `notify.mobile_app_nates_iphone` if `playing` — a busy Sonos there likely means a movie or game loud enough to miss the kitchen announcement over. The check is skipped in the Avery-sleeping branch, where only master bedroom fires.

- **Template helpers, not `configuration.yaml`.** Progress and remaining-time sensors are created as HA template helpers (config-flow API, equivalent to Settings → Helpers → Add Helper → Template), stored in HA storage and retrievable via MCP. Formula: `progress = (total_time − minutes_remaining) / total_time × 100`, clamped 0–100; `minutes_remaining = max(0, (remaining_time_timestamp − now()) / 60)`. Both guard against `unknown`/`unavailable` source states.

- **Cycle timestamps via `input_datetime` helpers.** ThinQ does not persist wall-clock start/end times — the status managers capture them at the moment the `running`/alerting transitions happen, into four `input_datetime` helpers (one per appliance per event). Built now even though their only consumer (a deferred dashboard pop-up) doesn't exist yet, since they can only ever be captured live at the transition — building later means losing history in between.

---

## Fault Handling

A cycle that aborts mid-run — a door that won't lock, a water supply problem, a jammed motor — is a `fault`, not a completion. Each appliance's error event entity (`event.utility_room_washer_error` / `event.utility_room_dryer_error`) carries a typed `event_type` naming the specific failure; the generic notification event's `error_during_washing` / `drying_failed` type is a second, less specific signal for the same failure. Both land on the same `fault` option, and whichever arrives first wins — mirroring the `alerting` transition's dual-trigger pattern above.

**A fault overrides `alerting`, and clears the same three ways `alerting` does:** a new cycle starting, sustained utility-room occupancy, or the door held open a minute. No separate fault-clearing logic exists — the status manager's existing retrieval branches set `idle` regardless of which non-idle state they're leaving.

**Ordering caveat:** the generic notification event lands roughly 0.5 seconds *before* the typed error event carrying the actual fault code. The announcement automation adds a 5-second settle delay before composing a fault message, specifically to let the typed event catch up — composing immediately risks reading no code at all. See `LESSONS.md`.

**Fault code → phrase map** (used by `automation.utility_room_laundry_announcement` to speak/push a specific cause; single copy, in that automation's `variables:` block):

| Appliance | `event_type` | Phrase |
|---|---|---|
| Washer | `unable_to_lock_error` | the door wouldn't lock |
| Washer | `door_open_error` | the door is open |
| Washer | `water_supply_error` | it isn't getting water |
| Washer | `water_drain_error` | it can't drain |
| Washer | `overfill_error` | it overfilled |
| Washer | `out_of_balance_error` | the load is out of balance |
| Washer | `locked_motor_error` | the motor is jammed |
| Washer | `power_fail_error` | there was a power failure |
| Washer | `water_level_sensor_error` | the water level sensor failed |
| Washer | `temperature_sensor_error` | the temperature sensor failed |
| Dryer | `high_power_supply_error` | there's a power supply problem |
| Dryer | `temperature_sensor_error` | the temperature sensor failed |
| Dryer | `power_code_connection_error` | the power cord isn't connected properly |

Fallbacks, in order: if the error entity's timestamp is more than 5 minutes old (reached `fault` via the generic notification event only, or a restart replayed a stale value), the message drops to "The washer stopped with an error."; if a code is present but unmapped — a firmware-added error type — it's humanized (`replace('_', ' ')`) rather than left to fail.

**Away or asleep: a single push, not the nag loop.** A fault bypasses the sleep/away gate that a plain completion respects — reaching for the phone matters more than waiting for someone to be home and awake. The announcement automation checks for this case before the arrival-wait block and before the repeat loop: if a fault is present and either nobody is home or everyone is asleep, it pushes once to `notify.mobile_app_nates_iphone` and stops, rather than entering the 30-minute repeat. This is a normal push, not a critical alert — a stalled laundry cycle isn't a safety hazard, and `binary_sensor.utility_room_washer_water_leak` already covers the case that would be (see [Related HA Config](#related-ha-config)).

**Live Activity latches the fault.** `sensor.utility_room_<appliance>_current_status` sits in `error` for only 1–2 seconds before reverting — too brief for the existing sensor-keyed error branch in `automation.utility_room_<appliance>_live_activity` to reliably catch. A fault-latch branch, checked first in each automation's `choose`, keys on `input_select.utility_room_<appliance>_status == fault` instead and holds the card in `error` until the same three clearing paths above take it back to `idle`. The card's message stays generic ("Check the washer — error reported") rather than carrying the specific fault code, to avoid a third copy of the phrase map above; if the code is wanted on the card later, promote the map to a `custom_templates` Jinja macro first (see `standards/documentation.md` and the best-practices skill's guidance on repeated template logic).

---

## Prerequisites

- LG ThinQ integration (`lg_thinq`) installed and authenticated
- `script.household_tts_announce` configured and active (see `guides/chime_tts.md`)
- `binary_sensor.utility_room_door` and `binary_sensor.utility_room_motion_sensor_occupancy` — Zigbee (ZHA)
- `input_boolean.everyone_sleeping` and `input_boolean.avery_sleeping` — sleep state helpers
- `binary_sensor.garage_interior_door` and `lock.entrance_front_door` — entry-detection for the §5.10 arrival grace window
- `zone.home` — default HA home zone
- `int_laundry` and `text_to_speech` labels (see `standards/automations.md` §3.2 for the two-step label creation procedure)

---

## Built

### 1. ThinQ entity set (confirmed live)

| Entity | Purpose |
|---|---|
| `sensor.utility_room_washer_current_status` | Cycle state machine |
| `sensor.utility_room_washer_remaining_time` | ISO 8601 timestamp when cycle ends; `unknown` when idle |
| `sensor.utility_room_washer_total_time` | Total cycle duration in minutes; `unknown` when idle |
| `event.utility_room_washer_notification` | Event entity; `event_type` attribute: `washing_is_complete` / `error_during_washing` |
| `event.utility_room_washer_error` | Event entity; typed fault code — see [Fault handling](#fault-handling) for the full list and phrase map |
| `sensor.utility_room_dryer_current_status` | Cycle state machine (running → cooling → wrinkle_care → end → power_off) |
| `sensor.utility_room_dryer_remaining_time` / `_total_time` | Same semantics as washer |
| `event.utility_room_dryer_notification` | `event_type`: `drying_is_complete` / `drying_failed` |
| `event.utility_room_dryer_error` | Event entity; typed fault code — see [Fault handling](#fault-handling) |

### 2. `int_laundry` and `text_to_speech` labels

`int_laundry` (purple, `mdi:washing-machine`) is applied to every helper, automation, and template sensor built in this guide. `text_to_speech` (green) is applied to the announcement automation alongside `notification`, per `standards/automations.md` §3.2.

### 3. `script.household_tts_announce`

Built as a prerequisite for this guide — it did not exist in the new house. See `guides/chime_tts.md` for the full script contract; this guide only uses `target: kitchen` and `target: master_bedroom`. The family room Sonos is not a script target — see the design decision above.

### 4. Helpers

| Entity | Type | Notes |
|---|---|---|
| `input_select.utility_room_washer_status` | Dropdown | Options: `idle`, `alerting`, `acknowledged`, `fault` |
| `input_select.utility_room_dryer_status` | Dropdown | Same options |
| `input_datetime.utility_room_washer_cycle_started` / `_ended` | Date + time | Captured live by the status manager |
| `input_datetime.utility_room_dryer_cycle_started` / `_ended` | Date + time | Same |
| `sensor.utility_room_washer_progress` / `_minutes_remaining` | Template sensor | See formula above |
| `sensor.utility_room_dryer_progress` / `_minutes_remaining` | Template sensor | Same |

All ten are assigned to the Utility Room area with the `int_laundry` label.

### 5. Status manager automations

`automation.utility_room_washer_status_manager` and `automation.utility_room_dryer_status_manager` — Maintenance category, Utility Room area, `int_laundry` label, `mode: single`. See [Design decisions](#architecture) and [Fault handling](#fault-handling) above for the trigger rationale. Full trigger/condition/action detail lives in the automation itself — retrieve via MCP (`ha_config_get_automation`) or read `ha/automations/automation.utility_room_washer_status_manager.yaml`.

### 6. TTS announcement automation

`automation.utility_room_laundry_announcement` — Maintenance category, Utility Room area, labels `int_laundry` + `notification` + `text_to_speech`, `mode: restart`. Announces both cycle completions and faults; see [Fault handling](#fault-handling) for the fault-specific branches. See `ha/automations/automation.utility_room_laundry_announcement.yaml` for the full config.

### 7. Live Activity automations

`automation.utility_room_washer_live_activity` and `automation.utility_room_dryer_live_activity` — Maintenance category, Utility Room area, labels `int_laundry` + `notification` + `live_activity`, `mode: queued`. Each drives an iOS Lock Screen card by reconciling its appliance's `current_status` sensor and retrieval `input_select` on every status change and a 5-minute tick — reusing the retrieval `input_select` means the card clears on the same occupancy/door signal that stops the TTS nag, with no new state machine. A fault-latch branch (see [Fault handling](#fault-handling)) is checked first, ahead of the status-sensor error branch. Full field contract, status palette, and the phase-label conversion table are in `guides/live_activities.md`, which owns the shared dispatch script; this guide only owns the two automations' triggers and the ThinQ entities they read.

---

## Not built — deferred

The dashboard was explicitly out of scope for this build pass. Nothing below exists yet:

- **Chip strip chips** — per-appliance running/alerting/acknowledged chips in the `mobile-home` chip strip, navigating to a `#laundry` pop-up.
- **`#laundry` pop-up** — status row, cycle info card, acknowledge action, washer stats tiles (cycles since cleaned, energy this/last month).
- **`input_select` → `acknowledged` transition** — nothing currently writes this value. It's reserved for the dashboard hold-to-acknowledge action; the option exists on the helper today so it doesn't require a schema change later.
- **Washer cycles-since-cleaned** — blocked, not just deferred. It needs a "washer was just cleaned" timestamp to snapshot `sensor.utility_room_washer_cycles` against; the natural source is `ha-chore-calendar`'s `input_datetime.washer_cleaned`, which is not installed in this instance (see `guides/reminders.md`). Needs either that integration or a standalone `input_datetime` + manual-trigger button first.
- **Per-appliance door sensors** — hardware, not software. The status managers currently share one utility room door/occupancy sensor pair for two appliances (see the retrieval design decision above). Adding a contact sensor directly to each washer/dryer lid would let each status manager clear only on its own appliance being opened, closing the cross-appliance false-clear gap entirely. No structural automation change needed — it's a one-entity swap in each status manager's `retrieved` trigger.

When dashboard work starts, `sensor.utility_room_washer_cycles` and `sensor.utility_room_washer_energy_this_month` / `_last_month` are already live and ready to wire in.

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Washer status | `input_select.utility_room_washer_status` | Helper (input_select) |
| Dryer status | `input_select.utility_room_dryer_status` | Helper (input_select) |
| Washer progress | `sensor.utility_room_washer_progress` | Helper (template sensor) |
| Washer minutes remaining | `sensor.utility_room_washer_minutes_remaining` | Helper (template sensor) |
| Dryer progress | `sensor.utility_room_dryer_progress` | Helper (template sensor) |
| Dryer minutes remaining | `sensor.utility_room_dryer_minutes_remaining` | Helper (template sensor) |
| Washer cycle started / ended | `input_datetime.utility_room_washer_cycle_started` / `_ended` | Helper (input_datetime) |
| Dryer cycle started / ended | `input_datetime.utility_room_dryer_cycle_started` / `_ended` | Helper (input_datetime) |
| Washer status manager | `automation.utility_room_washer_status_manager` | Automation |
| Dryer status manager | `automation.utility_room_dryer_status_manager` | Automation |
| Laundry announcement | `automation.utility_room_laundry_announcement` | Automation |
| Washer Live Activity | `automation.utility_room_washer_live_activity` | Automation |
| Dryer Live Activity | `automation.utility_room_dryer_live_activity` | Automation |
| TTS dispatch | `script.household_tts_announce` | Script |
| Live Activity dispatch | `script.household_live_activity` | Script |
| Laundry integration label | `int_laundry` | Label |
| Utility room door | `binary_sensor.utility_room_door` | Entity |
| Utility room occupancy | `binary_sensor.utility_room_motion_sensor_occupancy` | Entity |
| Family room Sonos (busy check only, not a TTS target) | `media_player.family_room_theater` | Entity |
| Washer error event | `event.utility_room_washer_error` | Entity |
| Dryer error event | `event.utility_room_dryer_error` | Entity |
| Washer water leak (the actual safety hazard, not this guide) | `binary_sensor.utility_room_washer_water_leak` | Entity |

---

## Related Documents

- `guides/chime_tts.md` — `script.household_tts_announce` field contract, per-room volumes, and why family room isn't a script target
- `guides/live_activities.md` — `script.household_live_activity` field contract, status palette, and the phase-label conversion tables for both appliances
- `guides/mobile_dashboard.md` — future home of the laundry chips and `#laundry` pop-up (not yet built)
- `guides/reminders.md` — why `ha-chore-calendar` isn't installed in this instance, blocking cycles-since-cleaned
- `standards/automations.md` — §5.10 (arrival entry-grace, used by the announcement automation), §5.11 (semantic triggers, used by both status managers), category/label/alias requirements
- `standards/dashboards.md` — chip strip pattern and Bubble Card pop-up conventions, for whenever the dashboard section is built

---

## Troubleshooting

**TTS fired while a machine was still running.** Check whether the status sensor briefly entered `end` before transitioning further — this is normal ThinQ behavior; the status manager should set `alerting` within the same second the sensor reports `end`.

**Progress bar not updating.** The template sensors update on ThinQ's own polling interval. If frozen mid-cycle, check the template sensor's state in **Developer Tools → States** before assuming the automation is broken.

**TTS not re-firing after returning home.** Confirm `zone.home` actually dropped to `0` before your return — if someone else stayed home, the count never hit zero and the re-trigger condition doesn't apply. Also confirm `automation.utility_room_laundry_announcement` is enabled.

**Status never clears after retrieving laundry.** Check `binary_sensor.utility_room_motion_sensor_occupancy` state in **Developer Tools → States** — if it shows `unavailable`, the primary retrieval trigger can't fire and you're relying on the door-open backup (60s continuous). Both sensors have shown occasional `unavailable` gaps in this house; see `LESSONS.md` for the pattern.

**Restart triggered a stale laundry alert.** This should not happen — the event-trigger branch has a 5-minute recency guard specifically for this. If it does, check `automation.utility_room_washer_status_manager`'s trace for which branch fired and whether the recency condition template evaluated correctly.

**A fault announced with the generic "stopped with an error" instead of the specific cause.** Expected when the fault arrived only through the generic notification event (`error_during_washing` / `drying_failed`) without a matching typed error event landing inside the same 5-minute window — check the error event entity's `event_type` attribute and its timestamp in **Developer Tools → States**. If the typed event *did* land within the window and the generic message still spoke, check whether the fault code is missing from the phrase map in `automation.utility_room_laundry_announcement`'s `variables:` block — see [Fault handling](#fault-handling) for the current list.

**A fault never announced at all.** Check `event.utility_room_washer_error` (or `_dryer_error`) for an `event_type` value not listed in [Fault handling](#fault-handling) — a firmware update can add a new code. `automation.utility_room_washer_status_manager`'s `fault_error` trigger filters on an explicit `options.event_type` list (the trigger schema requires one), so a new code needs that list extended before it reaches the state machine at all.
