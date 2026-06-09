# Laundry Automation

*Last updated: June 2026*

---

## Overview

Two LG appliances — a washer and dryer — are managed via the `lg_thinq` integration and surface as entity sets in HA. This integration adds a state machine helper per appliance, four template sensors for progress computation, four automations for state management and TTS announcements, and a condition-triggered Laundry section on the `mobile-home` dashboard. When a cycle completes, the system announces on the kitchen HomePod (or master bedroom if Avery is sleeping) every 30 minutes until the laundry is retrieved or explicitly acknowledged, and re-announces immediately when the household re-engages after sleep or an absence.

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
         │   automation.utility_room_washer_done_announcement
         │   ├── kitchen HomePod (default)
         │   └── master bedroom HomePod (avery_sleeping = on)
         │
         └─► Dashboard Card (mobile-home, Laundry section)
             Running: orange + gradient progress fill
             Alerting: bright green  →  tap → acknowledged
             Acknowledged: muted green

State machine inputs:
  sensor.washer_current_status → end         ──► idle → alerting
  sensor.washer_current_status → running     ──► any → idle (new cycle)
  binary_sensor.utility_room_door_contact    ──► any → idle (retrieved)
  dashboard tap                              ──► alerting → acknowledged

TTS inputs:
  input_select → alerting                   ──► start repeat loop
  input_boolean.everyone_sleeping → off     ──► re-trigger if alerting
  zone.home (0 → above 0)                   ──► re-trigger if alerting
  → stop: acknowledged │ door open │ everyone_sleeping │ away
```

**Design decisions:**

- **`input_select` state machine over booleans.** A single helper with three options (`idle`/`alerting`/`acknowledged`) gives the dashboard, TTS automation, and acknowledge tap a single source of truth. Two separate booleans (`done_pending` + `acknowledged`) would require template logic everywhere to avoid `pending=on` + `acknowledged=on` desync.

- **Status sensor trigger, not notification event.** `sensor.washer_current_status → end` is a persisted state change that survives HA restarts and doesn't depend on the LG cloud push delivery that drives `event.washer_notification`. The event entity (`washing_is_complete`) was confirmed working during setup but is not used as a trigger — state change is more reliable.

- **Dryer triggers on `cooling` or `end`, not just `end`.** Cooling begins when active drying heat stops; clothes can be removed at that point. Triggering at `cooling` matches when the LG app typically notifies and avoids delay from wrinkle-care phases that can run for hours.

- **TTS re-triggers on re-engagement.** The announcement automation uses `mode: restart` and fires on three triggers: `input_select → alerting`, `everyone_sleeping → off`, and `zone.home` crossing above 0. Sleep and away stop TTS but leave the visual (`input_select`) at `alerting`. When the household re-engages, the automation restarts and fires immediately rather than waiting up to 30 minutes for the next loop iteration.

- **Door-only visual clear.** The dashboard card disappears only when the utility room door opens — not on sleep or away. This preserves a visual reminder visible the moment you return or wake up. Sleep/away are pause conditions for TTS only.

- **Template helpers, not `configuration.yaml`.** Progress and remaining-time sensors are created as HA template helpers (Settings → Helpers → Add Helper → Template) stored in HA storage, not `configuration.yaml`. They are retrievable via MCP. The formula: `progress = (total_time − minutes_remaining) / total_time × 100`, clamped 0–100; `minutes_remaining = max(0, (remaining_time_timestamp − now()) / 60)`. Both guard against `unknown`/`unavailable` source states.

---

## Prerequisites

- LG ThinQ integration (`lg_thinq`) installed and authenticated
- Chime TTS integration active with `notify.reminder_kitchen` and `notify.reminder_master_bedroom` configured (see `guides/chime_tts.md`)
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

**Dryer status manager** (`automation.utility_room_dryer_status_manager`): mirror of the above, with two triggers for the done transition (`cooling` and `end`) sharing the same `id: cycle_done` so both match the same `condition: trigger` branch.

### 6. Create TTS announcement automations

Two automations — one per appliance — handle the repeating TTS loop. Both are in the **Maintenance** category, **Utility Room** area, with labels `int_laundry`, `notification`, and `text_to_speech`.

**Washer done announcement** (`automation.utility_room_washer_done_announcement`):

*Triggers:*
- `input_select.utility_room_washer_status` → `alerting` (primary)
- `input_boolean.everyone_sleeping` → `off` (re-trigger after sleep)
- `zone.home` numeric state crosses above 0 (re-trigger after absence)

*Start conditions (all must pass):*
- `washer_status == alerting`
- `everyone_sleeping == off`
- `zone.home > 0`

*Action — repeat (count: 20):*
1. Stop if `washer_status != alerting`
2. Stop if `everyone_sleeping == on`
3. Stop if `zone.home < 1`
4. Choose: `avery_sleeping == on` → `notify.reminder_master_bedroom`; otherwise → `notify.reminder_kitchen`. Message: `"The washer is done."`
5. Delay 30 minutes

Mode: `restart` — ensures re-triggers (wake up / arrive home) cancel the mid-loop delay and fire TTS immediately.

**Dryer done announcement** (`automation.utility_room_dryer_done_announcement`): mirror, referencing dryer entities. Message: `"The dryer is done."`

### 7. Add Laundry section to mobile-home dashboard

A condition-triggered section is added between the chip strip and the pop-up definitions. The section is invisible when both appliances are idle; it appears automatically when either is running or done.

**Section visibility:** `or` of:
- `washer_status != idle` (covers alerting + acknowledged)
- `dryer_status != idle`
- `washer_current_status` not in [`power_off`, `initial`] (covers active cycle)
- `dryer_current_status` not in [`power_off`, `initial`]

**Four conditional cards (two per appliance):**

*Running card* — visible when `status == idle` AND `current_status` not in [`power_off`, `initial`]:
- Bubble Card button, `button_type: name`, entity: progress sensor (drives re-render)
- Icon: orange · Label template: current status text + minutes remaining
- `card_mod` style: `linear-gradient` fill from left, width driven by progress sensor (0–100%)
- `tap_action: none`

*Done card* — visible when `status != idle`:
- Bubble Card button, `button_type: name`, entity: input_select (drives re-render)
- Icon: green · Label: "Done — tap to acknowledge" (alerting) or "Done" (acknowledged)
- `card_mod` style: `background-color: rgba(40, 200, 100, 0.45)` (alerting) or `rgba(40, 200, 100, 0.15)` (acknowledged)
- `tap_action`: `input_select.select_option → acknowledged`

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
| Washer status manager | `automation.utility_room_washer_status_manager` | Automation |
| Dryer status manager | `automation.utility_room_dryer_status_manager` | Automation |
| Washer done announcement | `automation.utility_room_washer_done_announcement` | Automation |
| Dryer done announcement | `automation.utility_room_dryer_done_announcement` | Automation |
| Laundry integration label | `int_laundry` | Label |
| Utility room door | `binary_sensor.utility_room_door_contact` | Entity |

---

## Related Documents

- `guides/chime_tts.md` — `notify.reminder_kitchen` and `notify.reminder_master_bedroom` configuration and call conventions
- `guides/mobile_dashboard.md` — `mobile-home` build guide; Laundry section is documented in its Related HA Config table
- `standards/automations.md` — Category, label, and alias requirements applied to all four automations
- `standards/dashboards.md` — Condition-triggered section pattern; Bubble Card button conventions

---

## Troubleshooting

**TTS fired while machine was still running.** The cycle completed while the section was showing the running card. Check whether the washer briefly entered `end` before transitioning — this is normal, the status manager should have set `input_select → alerting` within milliseconds of the `end` state appearing.

**Progress bar not updating.** The template sensors update on a 30-second polling interval by default. If the bar appears frozen mid-cycle, navigate away and back to force a re-render, or check the template sensor's state in **Developer Tools → States**.

**TTS not re-firing after returning home.** Confirm `zone.home` count actually dropped to 0 before your return — if you only stepped out briefly and the count stayed at 1 (someone else home), the re-trigger condition doesn't apply. Also verify `automation.utility_room_washer_done_announcement` is enabled in **Settings → Automations**.

**Dryer done card appeared during cooling but machine was still hot.** This is by design — `cooling` is the trigger. Clothes can be removed once active heating stops. If you prefer to wait for `end` only, change the dryer status manager's `cycle_done` trigger to remove the `cooling` → `id: cycle_done` entry.
