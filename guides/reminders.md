# Reminder System
*Last updated: July 2026*

---

## Overview

The reminder system uses the [ha-chore-calendar](https://github.com/tcarney/ha-chore-calendar) HACS integration to manage two categories of recurring tasks: household maintenance chores (interval-based, anchored to last completion) and trash/recycling pickup (calendar-schedule-based, biweekly alternating). Both categories surface on the mobile dashboard through a single always-visible chip and a shared `#reminders` pop-up.

A separate notification framework handles Roborock consumable alerts — see the [Sensor-Threshold Notifications](#sensor-threshold-notifications) section below.

> **Migration note:** Prior to July 2026, the reminder system used manual `input_datetime` / `input_number` helpers for interval-based reminders and `input_boolean` / `input_text` helpers for trash pickup state. Both patterns were replaced by ha-chore-calendar. The previous automations (`automation.household_reminder_notifications`, `automation.household_reminder_mark_complete`, `automation.household_pickup_reminder`, `automation.household_pickup_morning_critical`, `automation.household_pickup_mark_complete`) were rewritten in place to use the new integration. Git history preserves the old implementation.

---

## Architecture

```
ha-chore-calendar integration (HACS)
├── "Household Chores" config entry
│   ├── calendar.household_chores   (on = any chore due/overdue)
│   ├── todo.household_chores       (state = count of non-completed chores)
│   └── sensor.household_chores_*  (one per chore, state = completed/pending/due/overdue)
└── "Trash Pickup" config entry
    ├── calendar.trash_pickup       (on = active pickup window)
    ├── todo.trash_pickup           (state = count of non-completed trash chores)
    └── sensor.trash_pickup_*      (one per chore)

Status lifecycle per chore:
  completed → pending (pending_period before due_at) → due (at due_at) → overdue (after grace_period)

Notification lifecycle:
  Household Chores:
    09:00 daily → get_items(status=overdue) → push per overdue chore (tag: reminder_<uid>)
    chore_calendar_status_changed(to=completed) → clear notification by uid tag

  Trash Pickup:
    19:00 daily → get_items(status=pending, calendar.trash_pickup) → push + TTS if pickup pending
    19:30, 20:00 → TTS repeat if active trash sensor still pending/due
    chore_calendar_status_changed(to=due, calendar.trash_pickup) → critical iOS alarm
    09:00 daily → auto-complete active trash chore (cleanup if not manually done)
    chore_calendar_status_changed(to=completed, calendar.trash_pickup) → clear push notification

Dashboard:
  chip strip → todo.household_chores (always visible; grey=0, yellow=pending, red=due/overdue)
  #reminders popup → custom:chore-calendar-card for both lists (native mark-complete)
```

**Key design decisions:**

- *Integration owns the state machine.* ha-chore-calendar tracks `last_completed`, computes `due_at`, manages `completed → pending → due → overdue` transitions, and fires `chore_calendar_status_changed` events. No HA helper mirrors this state — the integration is the single source of truth.
- *Interval chores are anchored to last completion.* Due date = `last_completed + interval`. A chore that has never been completed starts in `pending` state with no due date; it enters the normal lifecycle on first completion.
- *Scheduled trash chores are anchored to the calendar grid.* The biweekly RRULE determines the exact due times regardless of when the chore was last completed. Two separate chores with offset `dtstart` values (`2026-07-09` and `2026-07-16`) produce alternating Wednesday series: one for trash-only weeks, one for trash-and-recycling weeks.
- *Alternating trash chores, not a single chore with a variable name.* Using two chore entities allows independent sensor state (`sensor.trash_pickup_put_out_trash` vs `sensor.trash_pickup_put_out_trash_recycling`) and means the 19:00 automation can derive the pickup label from `chore_name | replace('Put Out ', '')` — no stored label helper needed.
- *07:00 critical uses chore_calendar_status_changed(to=due), not a time trigger.* The event fires when the trash chore transitions to `due` (at 07:00 Wednesday via pending_period expiry). This means the critical notification fires only on actual pickup days with zero false positives — no daily condition check against a boolean.
- *09:00 auto-complete for trash cleanup.* If trash is still pending/due/overdue at 09:00, the automation calls `chore_calendar.complete_item` on the active sensor. This semantically marks pickup as done, advances the scheduled series to the next occurrence, and clears the iOS notification — a clean close even if the user forgot to tap Mark Complete.
- *chore-calendar-card handles mark-complete natively.* The popup uses the integration's own Lovelace card, which has built-in mark-complete UI. No `script.reminder_mark_complete` wrapper is needed; the card calls `chore_calendar.complete_item` directly.
- *Single always-visible chip with three color states.* Grey (no actionable chores), yellow (chores pending but nothing due/overdue yet), red (something due or overdue). The `calendar.household_chores` entity (`on` when any chore is due/overdue) drives the color; `todo.household_chores` drives the count badge.
- *Notification action mark-complete uses UID.* The push notification `action` field encodes `REMINDER_MARK_COMPLETE_<uid>`. The handler strips the prefix and passes the UID directly to `chore_calendar.complete_item` — no lookup table needed.

---

## Prerequisites

- ha-chore-calendar installed via HACS and both config entries created: **"Household Chores"** and **"Trash Pickup"**
- HA Companion app on Nate's iPhone (`notify.mobile_app_nates_iphone`)
- Critical Alerts entitlement enabled: **iPhone → Settings → Notifications → Home Assistant → Critical Alerts** (required for the 07:00 trash alarm to break through Do Not Disturb)

---

## Chore Lists

### Household Chores (`calendar.household_chores`)

All interval chores. All use `pending_period`: 3 days (4320 min), `grace_period`: 1 hour (60 min).

| Chore Name | Entity ID | Interval | Notes |
|---|---|---|---|
| Accord Washed | `sensor.household_chores_accord_washed` | 30 days | |
| Coffee Grinder Cleaned | `sensor.household_chores_coffee_grinder_cleaned` | 45 days | |
| Dishwasher Cleaned | `sensor.household_chores_dishwasher_cleaned` | 30 days | |
| Disposal Cleaned | `sensor.household_chores_disposal_cleaned` | 30 days | |
| Razor Blade Changed | `sensor.household_chores_razor_blade_changed` | 14 days | |
| Toothbrushes Changed | `sensor.household_chores_toothbrushes_changed` | 60 days | |
| Washer Cleaned | `sensor.household_chores_washer_cleaned` | 30 days | |
| Water Filter Changed | `sensor.household_chores_water_filter_changed` | 90 days | |

### Trash Pickup (`calendar.trash_pickup`)

Two scheduled chores with biweekly RRULE, offset by one week to produce an alternating pattern.

| Chore Name | Entity ID | Schedule | Pending window | Grace |
|---|---|---|---|---|
| Put Out Trash | `sensor.trash_pickup_put_out_trash` | Biweekly Wed (`dtstart: 2026-07-09`) | 12 hours (720 min) | 2 hours (120 min) |
| Put Out Trash & Recycling | `sensor.trash_pickup_put_out_trash_recycling` | Biweekly Wed (`dtstart: 2026-07-16`) | 12 hours (720 min) | 2 hours (120 min) |

Both use `FREQ=WEEKLY;INTERVAL=2;BYDAY=WE` with `time: 07:00`. The 12-hour pending window means the chore enters `pending` state at 19:00 Tuesday (12 hours before 07:00 Wednesday), which aligns with the 19:00 evening notification trigger.

---

## Notification Timing

### Household Reminders

| Time | Trigger | Action |
|---|---|---|
| 09:00 daily | Time trigger | Push notification per overdue chore (`tag: reminder_<uid>`, `REMINDER_MARK_COMPLETE_<uid>` action) |
| Any time | `chore_calendar_status_changed` → `to_status: completed` | Clear push notification by uid tag |

### Trash Pickup

| Time | Trigger | Action |
|---|---|---|
| 19:00 Tue | Time trigger | `get_items(status=pending)` on `calendar.trash_pickup`; push + TTS to kitchen if found |
| 19:30 Tue | Time trigger | TTS repeat to kitchen if active trash sensor still `pending` or `due` |
| 20:00 Tue | Time trigger | TTS repeat to kitchen if still pending/due and someone home |
| 07:00 Wed | `chore_calendar_status_changed` → `to_status: due` | Critical iOS alarm (`tag: pickup`, `PICKUP_MARK_COMPLETE` action) |
| 09:00 Wed | Time trigger | Auto-complete active trash chore if still `pending`/`due`/`overdue` |
| Any time | `chore_calendar_status_changed` → `to_status: completed` (calendar.trash_pickup) | Clear pickup push notification |

TTS announcements skip if no one is home (`zone.home` count ≤ 0). The 19:30 and 20:00 repeats check the active trash sensor state directly (`sensor.trash_pickup_put_out_trash` or `sensor.trash_pickup_put_out_trash_recycling`) rather than re-querying `get_items`.

---

## Dashboard Integration

**Chip strip** — always-visible button in the second row (between Dryer and the end of the row):

- Entity: `todo.household_chores`
- Icon: `mdi:calendar-clock` (static)
- Tap / hold: navigate to `#reminders`
- Color: grey when `todo.household_chores` state = 0; yellow when > 0 and `calendar.household_chores` is `off`; red when > 0 and `calendar.household_chores` is `on`
- Count badge: shows `todo.household_chores` state when > 0

**`#reminders` pop-up** — two `custom:chore-calendar-card` instances:

```yaml
type: custom:chore-calendar-card
entity: calendar.household_chores
---
type: custom:chore-calendar-card
entity: calendar.trash_pickup
```

The chore-calendar-card provides native status grouping (overdue / due / pending) and a built-in mark-complete action — no custom Bubble Card buttons needed.

---

## Adding a New Chore

**Interval chore:**
1. Open ha-chore-calendar config entry for "Household Chores" → Add chore
2. Set `chore_type: interval`, configure `interval` (days), `pending_period: 4320` (3 days), `grace_period: 60` (1 hour)
3. The integration automatically creates `sensor.household_chores_<chore_name>` and registers it with the calendar/todo entities
4. The 09:00 automation uses `get_items(status=overdue)` dynamically — no automation edit needed

**Scheduled chore (trash-pattern):**
1. Open ha-chore-calendar config entry for "Trash Pickup" → Add chore
2. Set `chore_type: scheduled`, configure RRULE, `dtstart`, `pending_period: 720` (12 hours), `grace_period: 120` (2 hours)
3. If adding a new pickup type, update `automation.household_pickup_reminder` to detect and derive the label from `chore_name`

---

## Related HA Config

### ha-chore-calendar Entities

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household Chores | `calendar.household_chores` | calendar (on = any chore due/overdue) |
| Household Chores | `todo.household_chores` | todo (state = actionable chore count) |
| Trash Pickup | `calendar.trash_pickup` | calendar |
| Trash Pickup | `todo.trash_pickup` | todo |
| Household Chores: Accord Washed | `sensor.household_chores_accord_washed` | chore sensor |
| Household Chores: Coffee Grinder Cleaned | `sensor.household_chores_coffee_grinder_cleaned` | chore sensor |
| Household Chores: Dishwasher Cleaned | `sensor.household_chores_dishwasher_cleaned` | chore sensor |
| Household Chores: Disposal Cleaned | `sensor.household_chores_disposal_cleaned` | chore sensor |
| Household Chores: Razor Blade Changed | `sensor.household_chores_razor_blade_changed` | chore sensor |
| Household Chores: Toothbrushes Changed | `sensor.household_chores_toothbrushes_changed` | chore sensor |
| Household Chores: Washer Cleaned | `sensor.household_chores_washer_cleaned` | chore sensor |
| Household Chores: Water Filter Changed | `sensor.household_chores_water_filter_changed` | chore sensor |
| Trash Pickup: Put Out Trash | `sensor.trash_pickup_put_out_trash` | chore sensor |
| Trash Pickup: Put Out Trash & Recycling | `sensor.trash_pickup_put_out_trash_recycling` | chore sensor |

### Automations

| Friendly Name | Entity ID | Role |
|---|---|---|
| Household: Reminder Notifications | `automation.household_reminder_notifications` | 09:00 overdue push; status_changed:completed → clear |
| Household: Reminder Mark Complete | `automation.household_reminder_mark_complete` | Notification action REMINDER_MARK_COMPLETE_* → complete_item |
| Household: Trash Pickup Reminder | `automation.household_pickup_reminder` | 19:00 push+TTS; 19:30/20:00 TTS repeats |
| Household: Trash Pickup Morning Critical | `automation.household_pickup_morning_critical` | status_changed:due → critical alarm; 09:00 → auto-complete |
| Household: Trash Pickup Mark Complete | `automation.household_pickup_mark_complete` | PICKUP_MARK_COMPLETE action → complete_item; status_changed:completed → clear |

---

## Troubleshooting

**`get_items` returns a 500 error or sensors go unavailable**

This indicates a corrupted coordinator state — most commonly caused by a `completed_at` value with no timezone offset being stored. The fix requires deleting and recreating the ha-chore-calendar config entry. After recreating, seed `last_completed` dates via the `chore_calendar.complete_item` service with timezone-aware timestamps (e.g., `"2026-06-16T00:00:00-04:00"` for EDT). Naive datetimes (`"2026-06-16T00:00:00"`) will trigger the same crash.

**`get_items` result accessed with `.items` returns the dict method, not the data**

The service response is a dict with an `items` key. In Jinja2, `result.items` resolves to the built-in dict `.items()` method. Always use bracket notation: `result['items']`.

**Overdue notification fires but Mark Complete tap doesn't clear it**

The notification tag is `reminder_<uid>` where `uid` is the chore's UUID attribute. The action ID is `REMINDER_MARK_COMPLETE_<uid>`. Verify the uid in `sensor.household_chores_*` attributes matches what was embedded in the push payload. Check `automation.household_reminder_mark_complete` traces for the `chore_uid` variable.

**19:00 push fires but no TTS**

Check that `zone.home` count > 0 at time of firing. TTS is gated on presence. Also confirm `script.household_tts_announce` is not suppressed (check `sensor.mac_mini_is_in_meeting` or similar camera sensor if applicable).

**07:00 critical doesn't fire on a pickup Wednesday**

The critical trigger is `chore_calendar_status_changed(to_status=due)`, which fires when the pending window expires at 07:00. If the status event doesn't fire, the coordinator may not have polled — check that ha-chore-calendar is reachable and the config entry is healthy. The coordinator polls every ~60 seconds.

**Stale iOS notifications from before the July 2026 migration**

The old system used tags like `reminder_accord_washed` (key-name-based). The new system uses `reminder_<uuid>`. Old-format notifications on the lock screen cannot be cleared by the new automations — dismiss them manually from the phone.

---

## Interval-Based Reminders (Deprecated)

> **Deprecated July 2026.** This pattern was replaced by ha-chore-calendar interval chores. The documentation is preserved for reference in case the pattern needs to be recreated.

A framework where each reminder tracks a last-done date and a configurable interval. The system automatically computes when the task is next due, marks it overdue, sends an actionable push notification, and closes the loop when the user taps Mark Complete on the lock screen — which resets the last-done date to today.

Two shared automations handle every reminder centrally. Per-item configuration is four helpers (last-done date, interval, due-date template sensor, overdue binary sensor). Adding a new reminder requires only creating those helpers and registering the new sensor in the shared automations.

### Architecture

```
input_datetime.<key>       input_number.<key>_offset
        └──────┬───────────────────┘
               ├──────────────────────────────────────────┐
               ▼ (template sensor, reactive)               ▼ (template helper, computes independently)
   sensor.<key>_due                          binary_sensor.<key>_overdue   (today() >= due)
   (formatted display string)                              │
  off edge ────┘    09:00 daily time trigger
                     │
                     ▼
   automation.household_reminder_notifications
          ├─ edge_off → clear notification            (clear_notification by tag)
          └─ daily    → send for each still-on sensor
                     │
                     ▼
         notify.mobile_app_nates_iphone
                     │
            [User taps Mark Complete]
                     ▼
   event: mobile_app_notification_action
                     ▼
   automation.household_reminder_mark_complete
                     ▼
   input_datetime.<key> ← today()
   (sensor.<key>_due updates reactively → overdue sensor flips off → notification clears)
```

**Key design decisions:**

- *Two shared automations, not one per reminder.* All reminders share `automation.household_reminder_notifications` and `automation.household_reminder_mark_complete`. New reminders register in two lists; no new automations needed.
- *One shared script for dashboard mark-complete.* `script.reminder_mark_complete` handles the hold-to-complete action for all reminder cards on the dashboard. Jinja2 templates in Lovelace card action `data` fields are not evaluated by the frontend — a server-side script is required for any action that needs the current date.
- *All notifications send at 09:00.* The daily time trigger is the only send path. No edge-on trigger means no midnight pings when the date rolls over. The `edge_off` trigger remains so the lock-screen notification clears immediately when a reminder is marked complete.
- *Tag-based notification lifecycle.* Each reminder's notification carries a stable `reminder_<key>` tag. The daily re-send replaces (not stacks) the on-screen notification; the clear path uses the same tag. iOS lock screen never accumulates duplicates.
- *Action ID encodes the input_datetime key.* The `REMINDER_MARK_COMPLETE_<key>` action ID doubles as the `input_datetime` entity name suffix. The handler parses it at runtime, requiring no lookup table and routing any reminder with one automation.
- *Due date sensor returns a formatted display string.* `sensor.<key>_due` computes `last-done + offset` and outputs the result as a human-readable string (e.g., `June 15, 2026`) rather than an ISO date. This is the value shown directly on dashboard cards — no card-level template evaluation needed. The sensor has no `device_class` set; HA cards show the raw state string as-is.
- *Binary sensor computes the due date independently.* `binary_sensor.<key>_overdue` does not read `sensor.<key>_due` — it recomputes the due date directly from `input_datetime.<key>` and `input_number.<key>_offset`. This decouples the overdue logic from the display format: if the sensor's output format ever changes, the binary sensor comparison is unaffected.

### Prerequisites

- HA Companion app installed on Nate's iPhone (`notify.mobile_app_nates_iphone`)
- Notification actions enabled in the iOS Companion app (Settings → Companion App → Notifications → no restrictions needed beyond standard setup)
- Helpers category `01K6ZGDERD3FBN9BPYKQSBYTGG` exists (all reminder helpers are grouped here for the HA UI)

### Adding a New Reminder

This procedure adds a reminder for a new task. The worked example below (Accord Washed) shows what all artifacts look like after setup.

**1. Create the last-done date helper**

In HA: *Settings → Devices & Services → Helpers → Create Helper → Date and/or time*

| Field | Value |
|---|---|
| Name | `<Object> <Action>` (e.g., `Accord Washed`) |
| Has date | Yes |
| Has time | No |
| Icon | Pick something meaningful |

Entity ID will be `input_datetime.<key>` (e.g., `input_datetime.accord_washed`).

**2. Create the interval helper**

*Helpers → Create Helper → Number*

| Field | Value |
|---|---|
| Name | `<Object> <Action> Offset` |
| Min | 0 |
| Max | 365 |
| Step | 1 |
| Unit | days |
| Mode | Box |
| Icon | `mdi:numeric` |

Entity ID: `input_number.<key>_offset`.

**3. Create the due-date template sensor**

*Settings → Devices & Services → Helpers → Create Helper → Template → Sensor*

| Field | Value |
|---|---|
| Name | `<Object> <Action> Due` |
| Template | `{{ (strptime(states('input_datetime.<key>'), '%Y-%m-%d') + timedelta(days=states('input_number.<key>_offset') \| int)).strftime('%B %-d, %Y') }}` |
| Device class | (leave blank) |

Entity ID: `sensor.<key>_due`. Returns a formatted string like `June 15, 2026`. No `device_class` — the state is a display string, not a machine-readable date. The sensor updates reactively whenever either input changes — no automation needed.

**4. Create the overdue binary sensor**

*Helpers → Create Helper → Template → Binary sensor*

| Field | Value |
|---|---|
| Name | `<Object> <Action> Overdue` |
| Template | `{{ now().date() >= (strptime(states('input_datetime.<key>'), '%Y-%m-%d') + timedelta(days=states('input_number.<key>_offset') \| int)).date() }}` |
| Device class | Problem |

Entity ID: `binary_sensor.<key>_overdue`. HA sets it `on` when the template evaluates to `True`.

**5. Create the days-until-due template sensor**

*Settings → Devices & Services → Helpers → Create Helper → Template → Sensor*

| Field | Value |
|---|---|
| Name | `<Object> <Action> Days Until Due` |
| Template | `{{ (as_date(states('sensor.<key>_due')) - today()).days }}` |
| Unit of measurement | `d` |
| Device class | (leave blank) |

Entity ID: `sensor.<key>_days_until_due`. Returns an integer count of calendar days until the task is due (e.g., `17`). Negative when overdue. The mobile dashboard uses this for all Upcoming visibility conditions — `condition: numeric_state` on a backend sensor works reliably where `condition: template` with date arithmetic fails: the Lovelace JS frontend cannot evaluate `as_timestamp(now())`, so all date bucketing must happen server-side.

> **Note on the date approach:** `as_date(states('sensor.<key>_due'))` returns the due date as a Python `date` object. Subtracting `today()` yields a `timedelta`, and `.days` gives an exact integer calendar-day count. This is immune to time-of-day drift that affected the prior floating-point timestamp approach, making the bucketing threshold semantically exact.

**6. Register the new sensor in the shared notification automations**

In `automation.household_reminder_notifications`, add `binary_sensor.<key>_overdue` to **both** the `edge_on` trigger's `entity_id` list and the `edge_off` trigger's `entity_id` list. Also add `<key>` (without `_overdue`) to the `for_each` list in the daily branch.

> **Coordinated change:** The `for_each` list in `automation.household_reminder_notifications` and the trigger `entity_id` lists are the canonical registration point for all reminders. Adding a new reminder requires updating all three lists in sync — they are duplicates of the same set.

**7. Add the task card to the mobile dashboard**

New tasks must be added to the `mobile-home` dashboard in the `#reminders` pop-up. The pop-up is organized into three sections — **Overdue**, **Upcoming**, and **Current** — and each reminder appears once per section (three card instances total per reminder), each gated by a `visibility` condition.

In Bubble Card, `hold_action` at the top level binds to the icon area — use `button_action.hold_action` to bind to the card body where the user expects to hold:

```yaml
# Template for all three section instances — change `styles` and `visibility` per section
type: custom:bubble-card
card_type: button
button_type: state
card_layout: normal
entity: sensor.<key>_due
name: <Friendly Name>
icon: <mdi:icon>
tap_action:
  action: none
hold_action:
  action: none
button_action:
  tap_action:
    action: none
  hold_action:
    action: perform-action
    perform_action: script.turn_on
    target:
      entity_id: script.reminder_mark_complete
    data:
      variables:
        reminder_entity: input_datetime.<key>
```

> **`card_layout: normal`** reduces Bubble Card's default card height to the compact "normal" size. Without it, each reminder card renders at the taller default height, making the pop-up excessively long with 8+ items per section.

**Overdue instance** — place after the Overdue separator:
```yaml
styles: "ha-icon { color: var(--error-color) !important; }"
visibility:
  - condition: state
    entity: binary_sensor.<key>_overdue
    state: "on"
```

**Next 3 Days instance** — place after the Next 3 Days separator:
```yaml
styles: "ha-icon { color: var(--warning-color) !important; }"
visibility:
  - condition: numeric_state
    entity: sensor.<key>_days_until_due
    above: 0
    below: 4
```

The Next 3 Days separator's visibility gates on `sensor.upcoming_reminders_count` > 0. After adding a new reminder, update the `sensor.upcoming_reminders_count` template sensor to include the new `'<key>'` in its key list — the template iterates this list to count reminders in the 1–3 day window.

> **Coordinated change:** Adding a new reminder requires five artifacts — four per-reminder helpers (steps 1–4) and one days-until-due template sensor (step 5) — plus two `#reminders` pop-up card instances (Overdue and Next 3 Days) and an update to `sensor.upcoming_reminders_count`. All must be kept in sync with the automation registrations in step 6. `script.reminder_mark_complete` and the empty state "All caught up" card are shared — no changes needed to either when adding a new reminder.

### Example: Household Maintenance Tasks

The eight household maintenance reminders that were migrated to ha-chore-calendar followed this pattern. All shared the two automations above; only their per-item helpers differed.

| Reminder | Last-Done Helper | Offset Helper | Due Sensor | Overdue Sensor | Days Until Due |
|---|---|---|---|---|---|
| Accord Washed | `input_datetime.accord_washed` | `input_number.accord_washed_offset` | `sensor.accord_washed_due` | `binary_sensor.accord_washed_overdue` | `sensor.accord_washed_days_until_due` |
| Coffee Grinder Cleaned | `input_datetime.coffee_grinder_cleaned` | `input_number.coffee_grinder_cleaned_offset` | `sensor.coffee_grinder_cleaned_due` | `binary_sensor.coffee_grinder_cleaned_overdue` | `sensor.coffee_grinder_cleaned_days_until_due` |
| Dishwasher Cleaned | `input_datetime.dishwasher_cleaned` | `input_number.dishwasher_cleaned_offset` | `sensor.dishwasher_cleaned_due` | `binary_sensor.dishwasher_cleaned_overdue` | `sensor.dishwasher_cleaned_days_until_due` |
| Disposal Cleaned | `input_datetime.disposal_cleaned` | `input_number.disposal_cleaned_offset` | `sensor.disposal_cleaned_due` | `binary_sensor.disposal_cleaned_overdue` | `sensor.disposal_cleaned_days_until_due` |
| Razor Blade Changed | `input_datetime.razor_blade_changed` | `input_number.razor_blade_changed_offset` | `sensor.razor_blade_changed_due` | `binary_sensor.razor_blade_changed_overdue` | `sensor.razor_blade_changed_days_until_due` |
| Toothbrushes Changed | `input_datetime.toothbrushes_changed` | `input_number.toothbrushes_changed_offset` | `sensor.toothbrushes_changed_due` | `binary_sensor.toothbrushes_changed_overdue` | `sensor.toothbrushes_changed_days_until_due` |
| Washer Cleaned | `input_datetime.washer_cleaned` | `input_number.washer_cleaned_offset` | `sensor.washer_cleaned_due` | `binary_sensor.washer_cleaned_overdue` | `sensor.washer_cleaned_days_until_due` |
| Water Filter Changed | `input_datetime.water_filter_changed` | `input_number.water_filter_changed_offset` | `sensor.water_filter_changed_due` | `binary_sensor.water_filter_changed_overdue` | `sensor.water_filter_changed_days_until_due` |

### Shared Scripts & Automations

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Reminder Notifications | `automation.household_reminder_notifications` | automation |
| Household: Reminder Mark Complete | `automation.household_reminder_mark_complete` | automation |
| Reminder: Mark Complete | `script.reminder_mark_complete` | script |
| Upcoming Reminders Count | `sensor.upcoming_reminders_count` | template sensor |

### Troubleshooting

**Mark Complete tap does not update the last-done date**

1. Open HA and check `automation.household_reminder_mark_complete` traces. Look at the `action_id` variable — confirm it starts with `REMINDER_MARK_COMPLETE_`.
2. Verify the `target_entity` variable resolves to a real `input_datetime` entity (`states(target_entity)` should not return `unknown`).
3. If the action ID is wrong, confirm the `household_reminder_notifications` automation is sending the correct `action:` field in the notification payload. Both must use the same `REMINDER_MARK_COMPLETE_<key>` string.

**Notification does not clear after marking complete**

The clear fires when the `binary_sensor.<key>_overdue` flips from `on` to `off`. Check:
1. Did the last-done date actually update? (Check `input_datetime.<key>` state.)
2. Did `sensor.<key>_due` update to the new due date? It updates reactively; if it shows `unavailable`, inspect the template in Developer Tools → Template.
3. Is the overdue sensor's due-date comparison still evaluating correctly? (Check `binary_sensor.<key>_overdue` state and trace via Developer Tools → Template.)
4. If the sensor flipped off but the notification did not clear, check the `edge_off` branch in `automation.household_reminder_notifications`. The `tag` must match exactly (`reminder_<key>`) between the send and clear calls.

**A reminder is not re-notified at 9am**

The reminder key is likely missing from the `for_each` list in the daily branch of `automation.household_reminder_notifications`. Verify the key appears as `<key>` (without `binary_sensor.` prefix and without `_overdue` suffix).

---

## Calendar-Driven Reminders (Deprecated)

> **Deprecated July 2026.** This pattern was replaced by ha-chore-calendar scheduled chores. The documentation is preserved for reference in case the pattern needs to be recreated.

A pattern for fixed-schedule events where the schedule is owned by an external calendar rather than by HA helpers. HA queries the calendar for upcoming events and sends notifications based on what it finds. Because the calendar is the source of truth, there is no last-done date or interval to manage — only a pending boolean that carries state across the notification lifecycle.

This pattern suits events that recur on a predictable external schedule (weekly, biweekly, seasonal) and where the notification timing is tied to the event date rather than an interval since last action. It uses a two-stage notification: an evening send the day before, and a critical escalation on the morning of the event if not yet acknowledged.

### Example: Trash & Recycling Pickup

The pickup schedule lived in an iCloud-published calendar subscribed in HA as `calendar.family` via the Remote Calendar integration. Single all-day events drove the logic: **"Trash Pickup"** (weekly, every Wednesday) and **"Trash & Recycling Pickup"** (biweekly, every other Wednesday). The event title directly encoded whether recycling was included that week — no separate series to correlate.

#### Architecture

```
iCloud "Family" calendar  (subscribed read-only via Remote Calendar integration)
            │
            ▼
     calendar.family  ─── all-day "Trash Pickup" (weekly Wed) or "Trash & Recycling Pickup" (biweekly Wed)
            │
            │  19:00 daily trigger               20:00 daily trigger
            ▼                                             │
   automation.household_pickup_reminder ←────────────────┘
      ├─ [19:00] calendar.get_events for tomorrow's window
      │          filter summaries → has_pickup flag, derive label
      │          if found: input_boolean.trash_pickup_pending ← on
      │                    input_text.trash_pickup_pending_label ← "Trash" | "Trash & Recycling"
      │                    notify.mobile_app_nates_iphone (tag: pickup, Mark Complete action)
      │                    notify.reminder_kitchen (TTS, if someone home)
      │          else:     input_boolean.trash_pickup_pending ← off (housekeeping)
      └─ [20:00] if pending + home: notify.reminder_kitchen (TTS repeat)
                                       │
                          [User taps Mark Complete]
                                       ▼
                       event: mobile_app_notification_action
                       (action: PICKUP_MARK_COMPLETE)
                                       ▼
                   automation.household_pickup_mark_complete
                      ├─ input_boolean.trash_pickup_pending ← off
                      └─ notify.mobile_app_nates_iphone (clear_notification, tag: pickup)

                  07:00 daily trigger
                          │
                          ▼
            automation.household_pickup_morning_critical
                ├─ condition: input_boolean.trash_pickup_pending is on
                ├─ notify.mobile_app_nates_iphone (CRITICAL sound, tag: pickup)
                │                                  message uses stored label
                └─ input_boolean.trash_pickup_pending ← off  (fires at most once per pickup cycle)
```

**Key design decisions:**

- *`calendar.get_events` instead of template attributes.* The Family calendar contains many unrelated events. HA's calendar entity state attributes only expose the single next event, which could be any event — not necessarily a pickup event. Calling `calendar.get_events` with a tomorrow window and filtering by summary is the only reliable way to detect pickup events regardless of what else is on the calendar.
- *Two helpers carry state across the 19:00 → 07:00 gap.* `input_boolean.trash_pickup_pending` arms when the evening notification fires and disarms when the user acks or when the critical fires. `input_text.trash_pickup_pending_label` stores the notification text from the calendar query so the 07:00 critical doesn't have to re-query. State survives HA restarts because HA restores helper state from storage.
- *Same notification tag for both sends.* The 07:00 critical replaces (not stacks) the 19:00 notification on the lock screen. Mark Complete clears whichever is currently showing.
- *Pending stays armed after the critical fires.* The 07:00 critical sends the alarm but leaves the boolean on, so the dashboard chip stays visible (and red) until the user marks complete or the 09:00 cleanup fires. The cleanup turns off the boolean — the `edge_off` branch of `automation.household_pickup_mark_complete` then clears the iOS notification automatically.
- *19:00 always writes pending state.* If no pickup is tomorrow, pending is forced off — a housekeeping gate that prevents stale pending state from a missed 07:00 run from carrying forward.
- *TTS fires at 19:00 and repeats at 20:00 if still pending.* Both announcements check `zone.home` count before firing. No TTS escalation at 07:00 — the critical path is push-only to avoid waking the household. The 20:00 repeat shares the stored label set at 19:00, so no calendar re-query is needed.
- *Critical alert requires iOS entitlement.* iOS will not play the critical alarm sound unless **Settings → Notifications → Home Assistant → Critical Alerts** is enabled on the device. Without this, the 07:00 notification is delivered silently if Do Not Disturb is active.

> **Coordinated change:** the exact event summaries `Trash Pickup` and `Trash & Recycling Pickup`. If the iCloud calendar event titles change, the `automation.household_pickup_reminder` templates must be updated to match.

#### State Helpers

| Friendly Name | Entity ID | Type | Role |
|---|---|---|---|
| Trash Pickup Pending | `input_boolean.trash_pickup_pending` | `input_boolean` | On between 19:00 send and Mark Complete / 07:00 escalation |
| Trash Pickup Pending Label | `input_text.trash_pickup_pending_label` | `input_text` | Carries "Trash" or "Trash & Recycling" from 19:00 to 07:00 |
| Trash Next Pickup Date | `input_text.trash_next_pickup_date` | `input_text` | Carries the formatted pickup date (e.g. "Wed, Jun 11") for dashboard display; set at 19:00 alongside the label |

#### Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Trash Pickup Reminder | `automation.household_pickup_reminder` | automation |
| Household: Trash Pickup Morning Critical | `automation.household_pickup_morning_critical` | automation |
| Household: Trash Pickup Mark Complete | `automation.household_pickup_mark_complete` | automation |
| Trash Pickup Pending | `input_boolean.trash_pickup_pending` | `input_boolean` |
| Trash Pickup Pending Label | `input_text.trash_pickup_pending_label` | `input_text` |
| Trash Next Pickup Date | `input_text.trash_next_pickup_date` | `input_text` |

#### Troubleshooting

**No notification fired Tuesday evening**

1. In HA Developer Tools → Services, call `calendar.get_events` against `calendar.family` for a window covering tomorrow. Confirm the response contains events with summary exactly `Trash Pickup` or `Trash & Recycling Pickup` (case-sensitive). If summaries differ, update the templates in `automation.household_pickup_reminder`.
2. Check the Remote Calendar integration's last-update timestamp — if `calendar.family` hasn't synced recently, the events may not be populated yet. Trigger a manual reload via **Settings → Devices & Services → [Remote Calendar integration] → Reload**.
3. Check the `automation.household_pickup_reminder` trace to see whether the `choose` branch evaluated `trash or recycling` as false.

**07:00 critical alarm didn't sound**

The critical alarm requires iOS to grant the entitlement: **iPhone → Settings → Notifications → Home Assistant → Critical Alerts**. If that toggle is off, the notification delivers silently during Do Not Disturb. Enable it, then re-test by manually setting `input_boolean.trash_pickup_pending` to on and running the automation via *Run*.

**Notification doesn't clear after tapping Mark Complete**

Check that the `action:` field in the notification payload exactly matches the trigger `event_data.action` in `automation.household_pickup_mark_complete`. Both must be `PICKUP_MARK_COMPLETE`. Also verify the `tag:` field is `pickup` in both the send and the clear calls — mismatched tags produce a notification that can't be cleared by the handler.

---

## Sensor-Threshold Notifications

A separate pattern for maintenance tasks where an external integration tracks usage and signals when attention is needed. The Roborock integration tracks four consumables and flips binary sensors to Problem state when each needs service. Notifications fire when the vacuum docks after a cleaning run; tapping Reset presses the corresponding integration reset button.

This framework lives independently of ha-chore-calendar — the Roborock integration owns the usage counters, and HA observes sensor state rather than tracking intervals manually.

| Binary Sensor | Notification Label | Reset Button |
|---|---|---|
| `binary_sensor.roborock_clean_sensor` | Clean Sensor | `button.roborock_q8_max_reset_sensor_consumable` |
| `binary_sensor.roborock_replace_filter` | Replace Filter | `button.roborock_q8_max_reset_air_filter_consumable` |
| `binary_sensor.roborock_replace_main_brush` | Replace Main Brush | `button.roborock_q8_max_reset_main_brush_consumable` |
| `binary_sensor.roborock_replace_side_brush` | Replace Side Brush | `button.roborock_q8_max_reset_side_brush_consumable` |

### Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Roborock: Notify maintenance needed | `automation.roborock_notify_maintenance_needed` | automation |
| Roborock: Dispatch Maintenance Reset | `automation.roborock_dispatch_maintenance_reset` | automation |
| Roborock Maintenance Required | `sensor.roborock_maintenance_required` | sensor (template) |
