# Reminder System
*Last updated: July 2026*

---

## Overview

The reminder system uses two independent subsystems. **Household chores** (interval-based maintenance tasks) are managed by the [ha-chore-calendar](https://github.com/tcarney/ha-chore-calendar) HACS integration via a single "Household Chores" config entry. **Trash pickup** uses `calendar.get_events` against `calendar.family` (an iCloud-published calendar subscribed via the Remote Calendar integration) — a boolean/text helper pair carries pending state across the 19:00-Tuesday → 09:00-Wednesday notification window. Both surfaces on the mobile dashboard through a shared chip and `#reminders` pop-up.

A separate notification framework handles Roborock consumable alerts — see the [Sensor-Threshold Notifications](#sensor-threshold-notifications) section below.

> Trash pickup runs on `calendar.get_events`, not ha-chore-calendar, on purpose — ha-chore-calendar's scheduled-chore state machine is unreliable for the narrow Tue→Wed notification window (see `LESSONS.md`). Interval chores are on ha-chore-calendar; trash pickup is not.

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

ha-chore-calendar evaluates `completed → pending` transitions at midnight, not in real-time. If the coordinator poll was missed or the integration restarted during a critical midnight window, the sensor can remain `completed` indefinitely. Reload the ha-chore-calendar config entry via **Settings → Devices & Services → ha-chore-calendar → Reload**. If the sensor still doesn't flip, delete and recreate the chore. This is why trash pickup does not use ha-chore-calendar — see `LESSONS.md`.

**A lock-screen reminder notification won't clear from an automation**

The current automations tag chore notifications `reminder_<uuid>` and clear by that tag. A notification carrying any other tag format cannot be cleared automatically — dismiss it manually from the phone.

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

1. Check `calendar.family` state first. If `unavailable`, the `calendar.get_events` call errors with "Service call requested response data but did not match any entities" and the automation exits without notifying. Reload via **Settings → Devices & Services → Remote Calendar → Reload**, wait for `calendar.family` to return a non-`unavailable` state, then manually trigger `automation.household_pickup_reminder` — it handles manual triggers by running the same evening-check branch.
2. If the calendar is available but no notification fired, call `calendar.get_events` against `calendar.family` for a window covering tomorrow in Developer Tools → Services. Confirm the response contains events with summary exactly `Trash Pickup` or `Trash & Recycling Pickup` (case-sensitive). If summaries differ, update the filter in `automation.household_pickup_reminder`.
3. Check the `automation.household_pickup_reminder` trace to see whether the `choose` branch found any matching events and what the `has_pickup` variable resolved to.

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
