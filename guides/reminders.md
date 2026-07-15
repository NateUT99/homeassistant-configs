# Reminder System
*Last updated: July 2026*

---

## Overview

The reminder system uses two independent subsystems. **Household chores** (interval-based maintenance tasks) are managed by the [ha-chore-calendar](https://github.com/tcarney/ha-chore-calendar) HACS integration via a single "Household Chores" config entry. **Trash pickup** uses `calendar.get_events` against `calendar.family` (an iCloud-published calendar subscribed via the Remote Calendar integration) — a boolean/text helper pair carries pending state across the 19:00-Tuesday → 09:00-Wednesday notification window. Both surfaces on the mobile dashboard through a shared chip and `#reminders` pop-up.

A separate notification framework handles Roborock consumable alerts — see the [Sensor-Threshold Notifications](#sensor-threshold-notifications) section below.

> **Migration history:** Prior to July 2026, the reminder system used manual `input_datetime` / `input_number` helpers for interval-based reminders and `input_boolean` / `input_text` helpers for trash pickup state. Both were replaced by ha-chore-calendar in July 2026. Trash pickup was reverted back to the calendar-based approach later the same month when ha-chore-calendar's scheduled chore state machine proved unreliable for narrow notification windows (state stuck in `completed` on two consecutive pickup cycles despite a 2-day pending window). Interval chores remain on ha-chore-calendar. Git history preserves the full migration timeline.

---

## Architecture

```
ha-chore-calendar integration (HACS)
└── "Household Chores" config entry
    ├── calendar.household_chores   (on = any chore due/overdue)
    ├── todo.household_chores       (state = count of non-completed chores)
    └── sensor.household_chores_*  (one per chore, state = completed/pending/due/overdue)

Status lifecycle per chore:
  completed → pending (pending_period before due_at) → due (at due_at) → overdue (after grace_period)

Household Chores notification lifecycle:
  09:00 daily → get_items(status=overdue) → push per overdue chore (tag: reminder_<uid>)
  chore_calendar_status_changed(to=completed) → clear notification by uid tag

───────────────────────────────────────────────────────────────────────

calendar.family (Remote Calendar, read-only iCloud subscribe)
└── "Trash Pickup" and "Trash & Recycling Pickup" all-day events

Trash Pickup notification lifecycle:
  19:00 Tue → calendar.get_events (tomorrow window) → filter by summary
      found: input_boolean.trash_pickup_pending ← on
             input_text.trash_pickup_pending_label ← "Trash" | "Trash & Recycling"
             input_text.trash_next_pickup_date ← formatted date
             push + kitchen TTS (if home)
      not found: input_boolean.trash_pickup_pending ← off (housekeeping)
  19:30/20:00 Tue → if pending + home: kitchen TTS repeat
  07:00 Wed → if pending: critical iOS alarm (uses stored label)
  09:00 Wed → if pending: turn off boolean + clear push notification
  PICKUP_MARK_COMPLETE action → turn off boolean + clear push notification

Dashboard:
  chip strip → combined: todo.household_chores + input_boolean.trash_pickup_pending
               grey=nothing due/pending, orange=due or trash pending, red=overdue
  #reminders popup → trash Bubble Card (visible when pending) + chore-calendar-card
```

**Key design decisions:**

- *Integration owns the interval chore state machine.* ha-chore-calendar tracks `last_completed`, computes `due_at`, manages `completed → pending → due → overdue` transitions, and fires `chore_calendar_status_changed` events. No HA helper mirrors this state.
- *Interval chores are anchored to last completion.* Due date = `last_completed + interval`. A chore that has never been completed starts in `pending` state with no due date; it enters the normal lifecycle on first completion.
- *Trash pickup uses `calendar.get_events` instead of ha-chore-calendar.* ha-chore-calendar's scheduled chore `completed → pending` transition evaluates at midnight. On two consecutive pickup cycles the transition was silently missed, leaving sensors stuck in `completed` at the 19:00 notification window. The calendar-based approach queries the authoritative schedule source at notification time and has no state machine dependency. See LESSONS.md for the full ha-chore-calendar midnight evaluation bug.
- *Two helpers carry trash state across the 19:00 → 07:00 gap.* `input_boolean.trash_pickup_pending` arms at 19:00 and disarms on Mark Complete or 09:00 cleanup. `input_text.trash_pickup_pending_label` stores the message text so the 07:00 critical doesn't need to re-query the calendar. State survives HA restarts.
- *chore-calendar-card handles interval mark-complete natively.* The popup uses the integration's own Lovelace card, which has built-in mark-complete UI. No `script.reminder_mark_complete` wrapper is needed for interval chores.
- *Single chip with three color states.* Grey (nothing due, overdue, or trash pending), orange (something due OR trash pending), red (anything overdue). Color iterates `sensor.household_chores_*` states for chores; adds `input_boolean.trash_pickup_pending` for trash. Count badge shows chores due+overdue plus 1 if trash pending; hidden when zero.
- *Notification action mark-complete for chores uses UID.* The push notification `action` field encodes `REMINDER_MARK_COMPLETE_<uid>`. The handler strips the prefix and passes the UID directly to `chore_calendar.complete_item`.

---

## Prerequisites

- ha-chore-calendar installed via HACS with the **"Household Chores"** config entry created
- Remote Calendar integration configured with the iCloud "Family" calendar subscription as `calendar.family`
- HA Companion app on Nate's iPhone (`notify.mobile_app_nates_iphone`)
- Critical Alerts entitlement enabled: **iPhone → Settings → Notifications → Home Assistant → Critical Alerts** (required for the 07:00 trash alarm to break through Do Not Disturb)

---

## Chore Lists

### Household Chores (`calendar.household_chores`)

All interval chores. All use `grace_period`: 1 hour (60 min). `pending_period` must not exceed the chore's interval — see LESSONS.md.

> **Note:** ha-chore-calendar preserves entity IDs when a chore is renamed — only the friendly name changes. Entity IDs remain anchored to the original chore name at creation time.

| Chore Name | Entity ID | Interval | Pending period |
|---|---|---|---|
| Wash Accord | `sensor.household_chores_accord_washed` | 30 days | 21 days (30240 min) |
| Clean Coffee Grinder | `sensor.household_chores_coffee_grinder_cleaned` | 45 days | 21 days (30240 min) |
| Clean Dishwasher | `sensor.household_chores_dishwasher_cleaned` | 30 days | 21 days (30240 min) |
| Clean Garbage Disposal | `sensor.household_chores_disposal_cleaned` | 30 days | 21 days (30240 min) |
| Replace Razor Blade | `sensor.household_chores_razor_blade_changed` | 14 days | 7 days (10080 min) |
| Replace Toothbrushes | `sensor.household_chores_toothbrushes_changed` | 60 days | 21 days (30240 min) |
| Clean Washing Machine | `sensor.household_chores_washer_cleaned` | 30 days | 21 days (30240 min) |
| Replace Water Filter | `sensor.household_chores_water_filter_changed` | 90 days | 21 days (30240 min) |

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
| 19:00 Tue | Time trigger | `calendar.get_events` on `calendar.family` for tomorrow; filter summaries; push + kitchen TTS if pickup found; set helpers. Turn off boolean if not found. |
| 19:30 Tue | Time trigger | TTS repeat to kitchen if `input_boolean.trash_pickup_pending == on` and someone home |
| 20:00 Tue | Time trigger | TTS repeat to kitchen if `input_boolean.trash_pickup_pending == on` and someone home |
| 07:00 Wed | Time trigger | Critical iOS alarm if `input_boolean.trash_pickup_pending == on`; uses stored `input_text.trash_pickup_pending_label` for message |
| 09:00 Wed | Time trigger | If `input_boolean.trash_pickup_pending == on`: turn off + clear notification `tag: pickup` |
| Any time | `mobile_app_notification_action` → `PICKUP_MARK_COMPLETE` | Turn off boolean + clear notification `tag: pickup` |

TTS announcements skip if no one is home (`sensor.household_people_home` ≤ 0) and route through `script.household_tts_announce`. The 07:00 critical is push-only — no TTS escalation to avoid waking the household.

---

## Dashboard Integration

**Chip strip** — always-visible button in the second row (between Dryer and the end of the row):

- Icon: `mdi:calendar-clock` (static)
- Tap / hold: navigate to `#reminders`
- Color: grey when no chores are `due` or `overdue` AND `input_boolean.trash_pickup_pending == off`; orange when any chore is `due` OR trash is pending; red when any chore is `overdue`. Determined by iterating `sensor.household_chores_*` states for the chore component and reading `input_boolean.trash_pickup_pending` for the trash component.
- Count badge: shows count of due+overdue chores plus 1 for trash if pending; hidden when zero.

**`#reminders` pop-up** — two cards, in order:

1. **Trash Pickup card** (Bubble Card, visible only when `input_boolean.trash_pickup_pending == on`):
   - Entity: `input_text.trash_pickup_pending_label` (displays "Trash" or "Trash & Recycling" as the state)
   - Sub-button shows `input_text.trash_next_pickup_date` (the formatted pickup date)
   - Hold action: `script.trash_pickup_mark_complete` (turns off boolean + clears iOS notification)
   - Icon color: `var(--warning-color)` (orange)

2. **Chore calendar card** (`custom:chore-calendar-card`, always visible):

```yaml
type: custom:chore-calendar-card
entities:
  - calendar.household_chores
```

The chore-calendar-card provides native status grouping (overdue / due / pending) and a built-in mark-complete action.

---

## Adding a New Chore

**Interval chore:**
1. Open ha-chore-calendar config entry for "Household Chores" → Add chore
2. Set `chore_type: interval`, configure `interval` (days), `pending_period` (must be less than `interval`; 21 days works for most), `grace_period: 60` (1 hour)
3. The integration automatically creates `sensor.household_chores_<chore_name>` and registers it with the calendar/todo entities
4. The 09:00 automation uses `get_items(status=overdue)` dynamically — no automation edit needed

---

## Related HA Config

### ha-chore-calendar Entities

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household Chores | `calendar.household_chores` | calendar (on = any chore due/overdue) |
| Household Chores | `todo.household_chores` | todo (state = actionable chore count) |
| Household Chores: Wash Accord | `sensor.household_chores_accord_washed` | chore sensor |
| Household Chores: Clean Coffee Grinder | `sensor.household_chores_coffee_grinder_cleaned` | chore sensor |
| Household Chores: Clean Dishwasher | `sensor.household_chores_dishwasher_cleaned` | chore sensor |
| Household Chores: Clean Garbage Disposal | `sensor.household_chores_disposal_cleaned` | chore sensor |
| Household Chores: Replace Razor Blade | `sensor.household_chores_razor_blade_changed` | chore sensor |
| Household Chores: Replace Toothbrushes | `sensor.household_chores_toothbrushes_changed` | chore sensor |
| Household Chores: Clean Washing Machine | `sensor.household_chores_washer_cleaned` | chore sensor |
| Household Chores: Replace Water Filter | `sensor.household_chores_water_filter_changed` | chore sensor |

### Trash Pickup Helpers

| Friendly Name | Entity ID | Type | Role |
|---|---|---|---|
| Trash Pickup Pending | `input_boolean.trash_pickup_pending` | `input_boolean` | On between 19:00 send and Mark Complete / 09:00 cleanup |
| Trash Pickup Pending Label | `input_text.trash_pickup_pending_label` | `input_text` | Carries "Trash" or "Trash & Recycling" from 19:00 to 07:00 |
| Trash Next Pickup Date | `input_text.trash_next_pickup_date` | `input_text` | Carries the formatted pickup date (e.g. "Wed, Jul 16") for dashboard display |

### Automations

| Friendly Name | Entity ID | Role |
|---|---|---|
| Household: Reminder Notifications | `automation.household_reminder_notifications` | 09:00 overdue push; status_changed:completed → clear |
| Household: Reminder Mark Complete | `automation.household_reminder_mark_complete` | Notification action REMINDER_MARK_COMPLETE_* → complete_item |
| Household: Trash Pickup Reminder | `automation.household_pickup_reminder` | 19:00 calendar query + push + TTS; 19:30/20:00 TTS repeats |
| Household: Trash Pickup Morning Critical | `automation.household_pickup_morning_critical` | 07:00 critical alarm if pending; 09:00 cleanup |
| Household: Trash Pickup Mark Complete | `automation.household_pickup_mark_complete` | PICKUP_MARK_COMPLETE action → turn off boolean + clear notification |

### Scripts

| Friendly Name | Entity ID | Role |
|---|---|---|
| Trash Pickup: Mark Complete | `script.trash_pickup_mark_complete` | Dashboard hold-to-complete; same actions as mark-complete automation |

---

## Troubleshooting

**`get_items` returns a 500 error or sensors go unavailable**

This indicates a corrupted coordinator state — most commonly caused by a `completed_at` value with no timezone offset being stored. The fix requires deleting and recreating the ha-chore-calendar config entry. After recreating, seed `last_completed` dates via the `chore_calendar.complete_item` service with timezone-aware timestamps (e.g., `"2026-06-16T00:00:00-04:00"` for EDT). Naive datetimes (`"2026-06-16T00:00:00"`) will trigger the same crash.

**`get_items` result accessed with `.items` returns the dict method, not the data**

The service response is a dict with an `items` key. In Jinja2, `result.items` resolves to the built-in dict `.items()` method. Always use bracket notation: `result['items']`.

**Overdue notification fires but Mark Complete tap doesn't clear it**

The notification tag is `reminder_<uid>` where `uid` is the chore's UUID attribute. The action ID is `REMINDER_MARK_COMPLETE_<uid>`. Verify the uid in `sensor.household_chores_*` attributes matches what was embedded in the push payload. Check `automation.household_reminder_mark_complete` traces for the `chore_uid` variable.

**Chore sensor stuck in `completed` state despite next_due in the past**

ha-chore-calendar evaluates `completed → pending` transitions at midnight, not in real-time. If the coordinator poll was missed or the integration restarted during a critical midnight window, the sensor can remain `completed` indefinitely. Reload the ha-chore-calendar config entry via **Settings → Devices & Services → ha-chore-calendar → Reload**. If the sensor still doesn't flip, delete and recreate the chore. Note: this bug is why trash pickup was reverted to the calendar.get_events approach — see LESSONS.md.

**Stale iOS notifications from before the July 2026 migration**

The old system used tags like `reminder_accord_washed` (key-name-based). The current system uses `reminder_<uuid>`. Old-format notifications on the lock screen cannot be cleared by the current automations — dismiss them manually from the phone.

---

## Trash Pickup

The pickup schedule lives in an iCloud-published calendar subscribed in HA as `calendar.family` via the Remote Calendar integration. Recurring all-day events drive the logic: **"Trash Pickup"** (biweekly, alternating Wednesdays) and **"Trash & Recycling Pickup"** (biweekly, the other Wednesdays). The event title directly encodes whether recycling is included — no separate series to correlate.

### Architecture

```
iCloud "Family" calendar  (subscribed read-only via Remote Calendar integration)
            │
            ▼
     calendar.family  ─── all-day "Trash Pickup" or "Trash & Recycling Pickup" (alternating Wed)
            │
            │  19:00 Tue trigger
            ▼
   automation.household_pickup_reminder
      ├─ [19:00] calendar.get_events → tomorrow's window
      │          filter summaries for pickup events → derive label + date
      │          found:    input_boolean.trash_pickup_pending ← on
      │                    input_text.trash_pickup_pending_label ← label
      │                    input_text.trash_next_pickup_date ← formatted date
      │                    notify.mobile_app_nates_iphone (tag: pickup, PICKUP_MARK_COMPLETE action)
      │                    script.household_tts_announce → kitchen (if home)
      │          not found: input_boolean.trash_pickup_pending ← off
      ├─ [19:30] if pending + home: script.household_tts_announce → kitchen
      └─ [20:00] if pending + home: script.household_tts_announce → kitchen

  07:00 Wed time trigger
            │
            ▼
   automation.household_pickup_morning_critical
      ├─ [07:00] condition: pending on
      │          notify.mobile_app_nates_iphone (CRITICAL sound, tag: pickup, stored label)
      └─ [09:00] if pending: input_boolean.trash_pickup_pending ← off
                             notify.mobile_app_nates_iphone (clear_notification, tag: pickup)

  mobile_app_notification_action (PICKUP_MARK_COMPLETE)
            │
            ▼
   automation.household_pickup_mark_complete
      ├─ input_boolean.trash_pickup_pending ← off
      └─ notify.mobile_app_nates_iphone (clear_notification, tag: pickup)

  Dashboard hold action
            │
            ▼
   script.trash_pickup_mark_complete
      ├─ input_boolean.trash_pickup_pending ← off
      └─ notify.mobile_app_nates_iphone (clear_notification, tag: pickup)
```

**Key design decisions:**

- *`calendar.get_events` instead of ha-chore-calendar.* ha-chore-calendar's scheduled chore state machine evaluates `completed → pending` at midnight; on two consecutive pickup cycles this transition was silently missed. `calendar.get_events` queries the authoritative schedule at notification time with no state machine dependency.
- *`calendar.get_events` instead of calendar attribute.* The Family calendar contains many unrelated events. HA's calendar entity state attributes only expose the single next event, which could be any event — not necessarily a pickup event. Querying with a tomorrow window and filtering by summary is the only reliable way to detect pickup events.
- *Two helpers carry state across the 19:00 → 07:00 gap.* `input_boolean.trash_pickup_pending` arms when the evening notification fires and disarms on Mark Complete or 09:00 cleanup. `input_text.trash_pickup_pending_label` stores the notification text from the calendar query so the 07:00 critical doesn't have to re-query. State survives HA restarts.
- *Same notification tag for all sends.* The 07:00 critical replaces (not stacks) the 19:00 notification on the lock screen. Mark Complete clears whichever is currently showing.
- *Boolean stays armed after the 07:00 critical.* The critical sends the alarm but leaves the boolean on so the dashboard chip remains visible until the user marks complete or 09:00 cleanup fires.
- *19:00 always writes pending state.* If no pickup is tomorrow, pending is forced off — a housekeeping gate that prevents stale state from carrying forward.
- *TTS fires at 19:00, 19:30, and 20:00 if still pending.* All TTS announcements check `sensor.household_people_home` before firing and route through `script.household_tts_announce`. No TTS at 07:00 — the critical path is push-only to avoid waking the household.
- *Critical alert requires iOS entitlement.* iOS will not play the critical alarm sound unless **Settings → Notifications → Home Assistant → Critical Alerts** is enabled on the device.

> **Coordinated change:** the exact event summaries `Trash Pickup` and `Trash & Recycling Pickup` are matched literally in `automation.household_pickup_reminder`. If the iCloud calendar event titles change, the summary filter in that automation must be updated to match.

### Notification Timing

See [Notification Timing — Trash Pickup](#trash-pickup-1) above.

### Dashboard Integration

The reminders chip on the mobile dashboard counts `input_boolean.trash_pickup_pending` as 1 toward the badge and toward the orange color condition. When trash is the only pending item, the chip shows orange with a badge of 1.

The `#reminders` pop-up shows a Bubble Card button for the pickup when `input_boolean.trash_pickup_pending` is `on`. The card state shows the label ("Trash" or "Trash & Recycling"); a sub-button shows the formatted pickup date from `input_text.trash_next_pickup_date`. Hold the card to mark complete via `script.trash_pickup_mark_complete`.

### Troubleshooting

**No notification fired Tuesday evening**

1. In HA Developer Tools → Services, call `calendar.get_events` against `calendar.family` for a window covering tomorrow. Confirm the response contains events with summary exactly `Trash Pickup` or `Trash & Recycling Pickup` (case-sensitive). If summaries differ, update the filter in `automation.household_pickup_reminder`.
2. Check the Remote Calendar integration's last-update timestamp — if `calendar.family` hasn't synced recently, events may not be populated. Trigger a manual reload via **Settings → Devices & Services → Remote Calendar → Reload**.
3. Check the `automation.household_pickup_reminder` trace to see whether the `choose` branch found any matching events.

**07:00 critical alarm didn't sound**

The critical alarm requires iOS to grant the entitlement: **iPhone → Settings → Notifications → Home Assistant → Critical Alerts**. If that toggle is off, the notification delivers silently during Do Not Disturb. To re-test without waiting for next Tuesday: manually set `input_boolean.trash_pickup_pending` to on, then run `automation.household_pickup_morning_critical` via *Run Manually*.

**Notification doesn't clear after tapping Mark Complete**

Check that the `action:` field in the notification payload exactly matches the trigger `event_data.action` in `automation.household_pickup_mark_complete`. Both must be `PICKUP_MARK_COMPLETE`. Verify the `tag:` field is `pickup` in both the send and the clear calls.

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
