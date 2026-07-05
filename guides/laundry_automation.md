# Laundry Automation

*Last updated: July 2026*

---

## Overview

Two LG appliances — a washer and dryer — are managed via the `lg_thinq` integration and surface as entity sets in HA. This integration adds a state machine helper per appliance, four template sensors for progress computation, three automations for state management and TTS announcements, and a condition-triggered Laundry section on the `mobile-home` dashboard. When a cycle completes, the system announces on the kitchen HomePod (or master bedroom if Avery is sleeping) every 30 minutes until the laundry is retrieved or explicitly acknowledged, and re-announces immediately when the household re-engages after sleep or an absence.

---

## Architecture

```
LG ThinQ (lg_thinq integration)
  sensor.washer_current_status (running → ... → end → power_off)
  sensor.washer_remaining_time (ISO 8601 timestamp when cycle ends)
  sensor.washer_total_time (integer minutes, total cycle length)
  [mirror: dryer entities]
         │
         ├─► Template Helpers (HA storage)
         │   sensor.utility_room_washer_progress     (0–100 %)
         │   sensor.utility_room_washer_minutes_remaining (int min)
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
  options: idle │ alerting │ acknowledged
         │
         ├─► TTS Announcement Automation
         │   automation.utility_room_laundry_done_announcement
         │   ├── combined message when both appliances alerting
         │   ├── kitchen HomePod (default)
         │   └── master bedroom HomePod (avery_sleeping = on)
         │
         ├─► Dashboard Chips (mobile-home, chip strip row 2)
         │   Running: orange + progress % · tap → #laundry pop-up
         │   Alerting: bright green · tap → #laundry · hold → acknowledged
         │   Acknowledged: muted (disabled) color · hidden only when door opens
         │
         └─► #laundry Pop-up (modal overlay, both appliances)
             Status row · cycle info (started / ETA or actual end / elapsed)
             Acknowledge button (alerting only) · stats (cycles, energy, power)

State machine inputs:
  sensor.washer_current_status → end         ──► idle → alerting
  sensor.washer_current_status → running     ──► any → idle (new cycle)
  binary_sensor.utility_room_door_contact    ──► any → idle (retrieved)
  chip hold (green) / pop-up ack button      ──► alerting → acknowledged

TTS inputs:
  input_select → alerting                   ──► start repeat loop
  input_boolean.everyone_sleeping → off     ──► re-trigger if alerting
  zone.home (0 → above 0)                   ──► re-trigger if alerting
                                                (waits for garage door to close first)
  → stop: acknowledged │ door open │ everyone_sleeping │ away
```

**Design decisions:**

- **`input_select` state machine over booleans.** A single helper with three options (`idle`/`alerting`/`acknowledged`) gives the dashboard, TTS automation, and acknowledge tap a single source of truth. Two separate booleans (`done_pending` + `acknowledged`) would require template logic everywhere to avoid `pending=on` + `acknowledged=on` desync.

- **Status sensor trigger, not notification event.** `sensor.washer_current_status → end` is a persisted state change that survives HA restarts and doesn't depend on the LG cloud push delivery that drives `event.washer_notification`. The event entity (`washing_is_complete`) was confirmed working during setup but is not used as a trigger — state change is more reliable.

- **Dryer triggers on `end` only, not `cooling`.** Although clothes can technically be removed once cooling starts, triggering at `cooling` shows a "Done" card while time remaining is still counting down — which is confusing. The running card stays visible through cooling and wrinkle-care phases; the done card appears only when the cycle fully completes.

- **TTS re-triggers on re-engagement.** The announcement automation uses `mode: restart` and fires on three triggers: `input_select → alerting`, `everyone_sleeping → off`, and `zone.home` crossing above 0. Sleep and away stop TTS but leave the visual (`input_select`) at `alerting`. When the household re-engages, the automation restarts and fires immediately rather than waiting up to 30 minutes for the next loop iteration.

- **Garage entry grace window on arrival.** When the `someone_arrived` trigger fires, the announcement always waits for the full interior garage door entry sequence before TTS fires: if the door is currently closed, wait up to 10 minutes for it to open (the person parking and walking to the door), then wait up to 5 minutes for it to close (the person stepping inside), then a 30-second buffer. If the door is already open when the trigger fires, the open-wait is skipped. Both waits use `continue_on_timeout: true` so TTS still fires if the person enters a different way. Without this sequence, TTS fires the moment zone.home registers the GPS arrival — before the person is inside to hear the HomePod. This follows the standard pattern in `standards/automations.md` section 5.10, established in `automation.outdoor_air_quality_index_alert`.

- **Chip over conditional section.** The original design used a condition-triggered dashboard section that auto-appeared above the chip strip. This was replaced with two conditional chips in the chip strip itself. Visual weight is lower — chips are compact and sit alongside vacuum/reminders rather than expanding the home view. A tap on either chip navigates to the shared `#laundry` pop-up rather than surfacing cards inline.

- **Door-only chip clear; acknowledged icon variant.** The chip disappears only when the utility room door opens — not on sleep, away, or acknowledge. Acknowledging silences TTS but leaves the chip visible (still green) and swaps the icon to the alert variant (`mdi:washing-machine-alert` / `mdi:tumble-dryer-alert`), signalling that the cycle is done but the load still needs to be dealt with. Sleep and away are TTS pause conditions only.

- **Cycle timestamps via `input_datetime` helpers.** The `#laundry` pop-up surfaces "started at," "estimated/actual end," and "finished X ago" data. ThinQ does not persist these wall-clock times — they are captured by the status manager automations at the moment the `running` and `end` state transitions happen. Four `input_datetime` helpers (one per appliance per event) store these values. Because they survive restarts and are not derived from live sensor state, the pop-up shows accurate history even when the machine is idle.

- **Template helpers, not `configuration.yaml`.** Progress and remaining-time sensors are created as HA template helpers (Settings → Helpers → Add Helper → Template) stored in HA storage, not `configuration.yaml`. They are retrievable via MCP. The formula: `progress = (total_time − minutes_remaining) / total_time × 100`, clamped 0–100; `minutes_remaining = max(0, (remaining_time_timestamp − now()) / 60)`. Both guard against `unknown`/`unavailable` source states.

---

## Prerequisites

- LG ThinQ integration (`lg_thinq`) installed and authenticated
- `script.household_tts_announce` configured and active (see `guides/chime_tts.md`)
- `binary_sensor.utility_room_door_contact` — utility room door sensor (Zigbee, via Z2M)
- `input_boolean.everyone_sleeping` and `input_boolean.avery_sleeping` — sleep state helpers (see `guides/reminders.md`)
- `zone.home` — default HA home zone
- Bubble Card and `lovelace-card-mod` installed in HACS frontend resources (for dashboard section)

---

## Build Steps

### 1. Confirm ThinQ entity set

After registering appliances in the `lg_thinq` integration, verify the following entities exist:

| Entity | Purpose |
|---|---|
| `sensor.washer_current_status` | Cycle state machine (running → spinning → rinsing → end → power_off) |
| `sensor.washer_remaining_time` | ISO 8601 timestamp when cycle ends; `unknown` when idle |
| `sensor.washer_total_time` | Total cycle duration in minutes; `unknown` when idle |
| `sensor.dryer_current_status` | Cycle state machine (running → cooling → wrinkle_care → end → power_off) |
| `sensor.dryer_remaining_time` | Same semantics as washer |
| `sensor.dryer_total_time` | Same semantics as washer |

### 2. Create the `int_laundry` label

In HA: **Settings → Labels → Add Label**.

| Field | Value |
|---|---|
| Name | Laundry |
| Label ID | `int_laundry` |
| Color | Purple |
| Icon | `mdi:washing-machine` |

Apply this label to all automations created below. The label marks entities documented in this guide.

### 3. Create input_select helpers

In HA: **Settings → Helpers → Add Helper → Dropdown**.

Create two helpers with identical configuration:

| Field | Washer | Dryer |
|---|---|---|
| Name | Utility Room Washer Status | Utility Room Dryer Status |
| Entity ID | `input_select.utility_room_washer_status` | `input_select.utility_room_dryer_status` |
| Options | `idle`, `alerting`, `acknowledged` | `idle`, `alerting`, `acknowledged` |
| Initial value | `idle` | `idle` |
| Icon | `mdi:washing-machine` | `mdi:tumble-dryer` |
| Area | Utility Room | Utility Room |

### 4. Create template sensor helpers

In HA: **Settings → Helpers → Add Helper → Template → Sensor**. Create four sensors.

**Washer Minutes Remaining** (`sensor.utility_room_washer_minutes_remaining`):

```jinja2
{% set ts = states('sensor.washer_remaining_time') %}
{% if ts in ['unknown', 'unavailable', 'none'] %}
  0
{% else %}
  {% set remaining = ((as_timestamp(ts) - as_timestamp(now())) / 60) | int %}
  {{ [remaining, 0] | max }}
{% endif %}
```

Unit: `min` · State class: Measurement · Icon: `mdi:timer-outline`

**Washer Progress** (`sensor.utility_room_washer_progress`):

```jinja2
{% set total = states('sensor.washer_total_time') | int(0) %}
{% set ts = states('sensor.washer_remaining_time') %}
{% if total == 0 or ts in ['unknown', 'unavailable', 'none'] %}
  0
{% else %}
  {% set remaining = ((as_timestamp(ts) - as_timestamp(now())) / 60) | float %}
  {% set remaining = [remaining, 0] | max %}
  {% set elapsed = total - remaining %}
  {% set pct = (elapsed / total * 100) | round(0) | int %}
  {{ [[pct, 0] | max, 100] | min }}
{% endif %}
```

Unit: `%` · State class: Measurement · Icon: `mdi:progress-clock`

**Dryer Minutes Remaining** (`sensor.utility_room_dryer_minutes_remaining`): same formula referencing `sensor.dryer_remaining_time`.

**Dryer Progress** (`sensor.utility_room_dryer_progress`): same formula referencing `sensor.dryer_remaining_time` and `sensor.dryer_total_time`.

### 5. Create status manager automations

Two automations — one per appliance — drive the `input_select` state machine. Both are in the **Maintenance** category, assigned to the **Utility Room** area, with the `int_laundry` label.

**Washer status manager** (`automation.utility_room_washer_status_manager`):

| Trigger | Condition | Action |
|---|---|---|
| `washer_current_status` → `end` | `washer_status == idle` | `washer_status` → `alerting` |
| `washer_current_status` → `running` | — | `washer_status` → `idle` |
| `utility_room_door_contact` → `on` | — | `washer_status` → `idle` |

Mode: `single`. The condition on the `end` trigger prevents re-alerting if the helper was manually set to `acknowledged` or `alerting` by a prior cycle that wasn't cleared before a new one started.

**Dryer status manager** (`automation.utility_room_dryer_status_manager`): mirror of the above, triggering only on `end` for the alerting transition (not `cooling` — see design decision above).

### 6. Create TTS announcement automation

One automation — `automation.utility_room_laundry_done_announcement` — handles the repeating TTS loop for both appliances. **Maintenance** category, **Utility Room** area, labels `int_laundry`, `notification`, and `text_to_speech`.

*Triggers:*
- `input_select.utility_room_washer_status` → `alerting` (primary, id: `status_alerting`)
- `input_select.utility_room_dryer_status` → `alerting` (primary, id: `status_alerting`)
- `input_boolean.everyone_sleeping` → `off` (re-trigger after sleep, id: `everyone_woke`)
- `zone.home` numeric state crosses above 0 (re-trigger after absence, id: `someone_arrived`)

*Start conditions (all must pass):*
- `washer_status == alerting` OR `dryer_status == alerting`
- `everyone_sleeping == off`
- `zone.home > 0`

*Pre-loop action (arrival only):*
- If `trigger.id == someone_arrived`: wait for the interior garage door entry sequence — if door is currently closed, wait up to 10 minutes for it to open, then wait up to 5 minutes for it to close, then pause 30 seconds. If the door is already open when arrival fires, the open-wait is skipped. Both waits use `continue_on_timeout: true`. See `standards/automations.md` section 5.10.

*Action — repeat (count: 20):*
1. Stop if neither `washer_status` nor `dryer_status` is `alerting`
2. Stop if `everyone_sleeping == on`
3. Stop if `zone.home < 1`
4. Evaluate message and title: `"The washer and dryer cycles have both completed."` / `"Laundry Done"` when both alerting; `"The washer cycle has completed."` / `"Washer Done"` for washer only; `"The dryer cycle has completed."` / `"Dryer Done"` for dryer only.
5. Call `script.household_tts_announce` with the computed message and title, `target: master_bedroom` (when `avery_sleeping == on`) or `target: kitchen` (otherwise). The script handles camera-aware suppression and mobile push fallback — see `guides/chime_tts.md`.
6. If `utility_room_door_contact == on` → set both `washer_status` and `dryer_status` to `idle` and stop. Idempotent — setting an already-idle status to idle is a no-op.
7. Delay 30 minutes

Mode: `restart` — ensures re-triggers (wake up / arrive home / second appliance finishing) cancel the mid-loop delay and fire TTS immediately with an updated message.

### 7. Add laundry chips and pop-up to mobile-home dashboard

The laundry integration surfaces two conditional chips in the existing chip strip and a `#laundry` Bubble Card pop-up. There is no inline Laundry section on the home view — the chips provide ambient status at a glance and navigate directly to the pop-up on tap.

#### 7a. Chip strip chips (two per appliance, added to chip strip row 2)

Each appliance gets one sub-button in the chip strip's feature row (alongside thermostat, vacuum, reminders). The chip is hidden when the appliance is idle and no cycle is active. Visibility is driven by the chip strip card's global CSS-in-JS `styles` expression.

| State | Icon | Color | Content |
|---|---|---|---|
| Running (status `idle`, appliance not `power_off` / `initial`) | `mdi:washing-machine` / `mdi:tumble-dryer` | Warning (orange) | Progress % |
| Done unacknowledged (`status == alerting`) | `mdi:washing-machine` / `mdi:tumble-dryer` | Success (green) | (icon only) |
| Done acknowledged (`status == acknowledged`) | `mdi:washing-machine-alert` / `mdi:tumble-dryer-alert` | Success (green) | (icon only) |
| Idle (no cycle active) | — | Hidden | — |

**Tap:** navigate to `#laundry` pop-up.  
**Hold:** calls `script.utility_room_acknowledge_laundry` with the appropriate appliance. No-op while running (script conditions on `status == alerting`).

#### 7b. `#laundry` pop-up

Bubble Card `pop-up`, `hash: "#laundry"`, `popup_mode: adaptive-dialog`. Per-appliance layout repeated twice (Washer then Dryer):

1. **Bubble Card separator** — appliance name heading
2. **Bubble Card button — status row** (`button_type: slider`, entity: `sensor.utility_room_<appliance>_progress`):
   - Slider fill tracks cycle completion (0–100 %); `state_display` Jinja shows phase name ("Off" / "Standby" / "Running" / "Done")
   - Icon color via `styles` block: orange (running), green (alerting), grey (acknowledged or off)
   - **Acknowledge sub-button** (`mdi:check-bold`, `perform-action: script.turn_on` with `appliance` field): hidden via `styles` unless `status == alerting`
   - **Progress % sub-button** (entity: `sensor.utility_room_<appliance>_progress`, `show_state: true`): hidden unless running
3. **Markdown card — cycle info** (state-adaptive):
   - *Running*: **Started:** HH:MM AM (N min ago) / *__End:__ HH:MM AM (N min remaining)* (whole line italic — estimated)
   - *Done*: **Started:** HH:MM AM / **End:** HH:MM AM (finished X ago)
   - *Idle + history*: **Last cycle:** HH:MM AM → HH:MM AM (X ago) — requires cycle duration > 0 to filter uninitialized helpers
   - *Idle, no history*: card emits blank
4. **Washer stats** (no separator; flows directly below the status card):
   - Full-width Bubble Card button: `state_display` = cycles since cleaned (`sensor.washer_cycles` − snapshot) + last cleaning date; `name` = "Since cleaned"
   - 2-column energy grid: This Month (`sensor.washer_energy_this_month`) | Last Month (`sensor.washer_energy_last_month`)
   - Conditional last error tile (`event.washer_error`, hidden when `unknown`)
5. **Dryer** has no stats tiles; conditional last error tile only (`event.dryer_error`)

---

## Related HA Config

| Artifact | Entity / ID | Type |
|---|---|---|
| Washer | `sensor.washer_current_status` | Entity (lg_thinq) |
| Washer remaining time | `sensor.washer_remaining_time` | Entity (lg_thinq) |
| Washer total time | `sensor.washer_total_time` | Entity (lg_thinq) |
| Dryer | `sensor.dryer_current_status` | Entity (lg_thinq) |
| Dryer remaining time | `sensor.dryer_remaining_time` | Entity (lg_thinq) |
| Dryer total time | `sensor.dryer_total_time` | Entity (lg_thinq) |
| Washer status | `input_select.utility_room_washer_status` | Helper (input_select) |
| Dryer status | `input_select.utility_room_dryer_status` | Helper (input_select) |
| Washer progress | `sensor.utility_room_washer_progress` | Helper (template sensor) |
| Washer minutes remaining | `sensor.utility_room_washer_minutes_remaining` | Helper (template sensor) |
| Dryer progress | `sensor.utility_room_dryer_progress` | Helper (template sensor) |
| Dryer minutes remaining | `sensor.utility_room_dryer_minutes_remaining` | Helper (template sensor) |
| Washer cycle started | `input_datetime.utility_room_washer_cycle_started` | Helper (input_datetime) |
| Washer cycle ended | `input_datetime.utility_room_washer_cycle_ended` | Helper (input_datetime) |
| Dryer cycle started | `input_datetime.utility_room_dryer_cycle_started` | Helper (input_datetime) |
| Dryer cycle ended | `input_datetime.utility_room_dryer_cycle_ended` | Helper (input_datetime) |
| Washer energy this month | `sensor.washer_energy_this_month` | Entity (lg_thinq) |
| Washer energy last month | `sensor.washer_energy_last_month` | Entity (lg_thinq) |
| Washer cycles at last cleaning | `input_number.utility_room_washer_cycles_at_last_cleaning` | Helper (input_number) |
| Washer status manager | `automation.utility_room_washer_status_manager` | Automation |
| Dryer status manager | `automation.utility_room_dryer_status_manager` | Automation |
| Laundry done announcement | `automation.utility_room_laundry_done_announcement` | Automation |
| Washer cycles snapshot | `automation.utility_room_washer_cycles_snapshot_on_clean` | Automation |
| Acknowledge laundry | `script.utility_room_acknowledge_laundry` | Script |
| TTS dispatch | `script.household_tts_announce` | Script |
| Laundry integration label | `int_laundry` | Label |
| Utility room door | `binary_sensor.utility_room_door_contact` | Entity |

---

## Related Documents

- `guides/chime_tts.md` — `notify.reminder_kitchen` and `notify.reminder_master_bedroom` configuration and call conventions
- `guides/mobile_dashboard.md` — `mobile-home` build guide; laundry chips and `#laundry` pop-up are documented there
- `guides/reminders.md` — Reminder system architecture; `input_datetime.washer_cleaned` is watched by `automation.utility_room_washer_cycles_snapshot_on_clean` to update the cycles-since-cleaned snapshot
- `standards/automations.md` — Category, label, and alias requirements applied to all automations
- `standards/dashboards.md` — Chip strip pattern; Bubble Card pop-up conventions

---

## Future Improvements

**Per-appliance door sensors.** The current design uses `binary_sensor.utility_room_door_contact` as a proxy for "someone retrieved the laundry." If door sensors are added directly to the washer and dryer lids, replace the utility room door entity in two places per appliance:

1. The status manager's `door_opened` trigger — currently clears both appliances when anyone enters the utility room; per-appliance sensors would clear each independently
2. The announcement loop's post-announcement door check — same scoping improvement

No structural changes needed; it's a two-entity swap in each status manager and a one-entity swap in the announcement automation.

---

## Troubleshooting

**TTS fired while machine was still running.** The cycle completed while the chip was still showing the running (orange) state. Check whether the washer briefly entered `end` before transitioning — this is normal, the status manager should have set `input_select → alerting` within milliseconds of the `end` state appearing.

**Progress bar not updating.** The template sensors update on a 30-second polling interval by default. If the bar appears frozen mid-cycle, navigate away and back to force a re-render, or check the template sensor's state in **Developer Tools → States**.

**TTS not re-firing after returning home.** Confirm `zone.home` count actually dropped to 0 before your return — if you only stepped out briefly and the count stayed at 1 (someone else home), the re-trigger condition doesn't apply. Also verify `automation.utility_room_laundry_done_announcement` is enabled in **Settings → Automations**.

**Dryer chip appeared during cooling but machine was still hot.** The dryer status manager only triggers on `end`, not `cooling`. If the chip appeared before the cycle actually finished, check the dryer status manager automation trace — `sensor.dryer_current_status` may have briefly hit `end` before transitioning to `cooling` or `wrinkle_care`. This is normal ThinQ state machine behavior; the chip should clear correctly when the door opens.
