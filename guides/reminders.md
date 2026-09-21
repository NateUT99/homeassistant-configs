# Reminder System
*Last updated: September 2026*

---

## Overview

Household chores are tracked by the **`ha-chore-calendar`** HACS integration
(`calendar.household_chores` / `todo.household_chores`, one chore per `sensor.household_chores_*`),
which owns scheduling, pending/due/overdue status, and rescheduling on completion internally.
Two automations layer daily push notifications and lock-screen mark-done on top of it — nothing
here re-derives what the integration already computes. Trash pickup is separate and
deliberately minimal: one automation queries `calendar.family` live at each reminder time (no
stored due date, no list item) and one helper, `input_boolean.household_trash_taken_out`,
silences reminders once you've taken it out. A `chore-calendar-card` dashboard at
`/household-chores` gives create/edit/skip/complete dialogs beyond what the notifications cover.

---

## Architecture

```
ha-chore-calendar (HACS)
└── "Household Chores" config entry
    ├── calendar.household_chores        (all chores, read-only calendar view)
    ├── todo.household_chores            (native todo UI; writable — completing
    │                                      an item here IS chore_calendar.complete_item)
    └── sensor.household_chores_<chore>  (one per chore: status + schedule attributes)

Per-chore lifecycle (ha-chore-calendar internal, not automated here):
  completed → pending (pending_period before due) → due → overdue (after grace_period)
  Rescheduling on completion is internal — last_completed + interval computes the next due
  date the moment todo.update_item(status: completed) lands. No reschedule automation exists.

Household: Chore Daily Notify
  09:00 daily → todo.get_items(status=needs_action) → push per item already due/overdue
  (tag: chore_<uid>, action: CHORE_DONE_<uid>)

Household: Task Mark Done
  mobile_app_notification_action, action starts with CHORE_DONE_
    → todo.update_item(status=completed) → clear the notification by tag
      (ha-chore-calendar reschedules internally; nothing else to do)

───────────────────────────────────────────────────────────────────────

calendar.family (Remote Calendar, read-only iCloud subscribe)
└── "Trash Pickup" / "Trash & Recycling Pickup" alternating biweekly all-day events

Household: Trash Pickup — no stored due date, no list item; queries live each time it fires
  19:00/19:30/20:00 → if a pickup event is tomorrow AND the helper is off AND someone home
                     → script.household_tts_announce → kitchen
  everyone_sleeping: on → off → if a pickup event is today AND the helper is off
                     → script.household_tts_announce → master bedroom
  10:00 daily        → turn input_boolean.household_trash_taken_out off (idempotent reset)
```

**Design decisions:**

- *ha-chore-calendar over a native `local_todo` list.* A native list requires reimplementing
  reschedule-on-completion, pending/due/overdue status, and a dashboard surface from scratch;
  ha-chore-calendar (actively maintained, verified against its current source) provides all
  three plus a Lovelace card, and its own `todo.update_item` merges cleanly with the two
  notification automations here.
- *`pending_period` must be less than the chore's `interval`.* Verified directly against
  upstream source (`models/base.py::compute_status`): if `pending_period >= interval`, the
  chore is permanently stuck `completed` — `last_completed >= pending_at` becomes
  unconditionally true. See `LESSONS.md` for the full trace.
- *No reschedule automation.* Completing a chore via `todo.update_item(status: completed)`
  routes through ha-chore-calendar's own `async_complete_chore`, which recomputes the next due
  date from `last_completed + interval` internally. Household: Task Mark Done only sets
  `status: completed` and clears the notification — nothing else is needed.
- *Trash pickup stays off ha-chore-calendar and off any to-do list entirely.* The pickup
  schedule already lives in `calendar.family` (the real municipal schedule); duplicating it
  into a chore's own recurrence would drift if pickup day ever changes. Each of the five
  triggers queries the calendar directly at fire time — no due-date state to keep in sync, no
  rollover logic to get right at restart boundaries.
- *One helper carries all of trash pickup's state.* `input_boolean.household_trash_taken_out`
  — on silences the remaining reminders for the current pickup, and a daily 10:00 reset clears
  it for the next cycle. No push notification for trash, TTS only.
- *`todo.update_item` on ha-chore-calendar's entity requires `due_datetime`, not `due_date`.*
  Only `SET_DUE_DATETIME_ON_ITEM` is advertised (verified in `todo.py`); a bare date is
  rejected. Neither automation here sets a due date at all — mark-done only ever touches
  `status`.

---

## Prerequisites

- **ha-chore-calendar** installed via HACS (custom repository `tcarney/ha-chore-calendar`),
  with the **"Household Chores"** config entry created.
- Remote Calendar integration configured with the iCloud "Family" calendar subscription as
  `calendar.family`, for trash pickup.
- HA Companion app on Nate's iPhone (`notify.mobile_app_nates_iphone`) for chore push
  notifications.
- `script.household_tts_announce` for trash pickup's voice announcements.

---

## Steps

### 1. Install and create the list

Add `tcarney/ha-chore-calendar` as a HACS custom repository (category: integration), download
it, restart HA, then add the integration with list name **Household Chores**. This creates
`calendar.household_chores` and `todo.household_chores`.

### 2. Add the chores

Via `chore_calendar.create_item` (`entity_id: calendar.household_chores`), one `interval:`
chore per row, `grace_period: {hours: 1}` on all:

| Chore | `interval.interval` (days) | `pending_period` |
|---|---|---|
| Wash Accord | 30 | 21 days |
| Clean Coffee Grinder | 45 | 21 days |
| Clean Dishwasher | 30 | 21 days |
| Clean Garbage Disposal | 30 | 21 days |
| Clean Washing Machine | 30 | 21 days |
| Replace Razor Blade | 14 | 7 days |
| Replace Toothbrushes | 60 | 21 days |
| Replace Water Filter | 90 | 21 days |

`create_item` has no field to seed `last_completed`; to anchor a chore's first due date, follow
the create with `chore_calendar.complete_item` (`completed_at:` set to the desired last-done
timestamp) — the chore then reads `due = completed_at + interval`.

### 3. Build the two automations

`automation.household_chore_daily_notify` and `automation.household_task_mark_done` — full
YAML in the `ha/` mirror (see Related HA Config). Both operate on `todo.household_chores`
directly; neither needs any per-chore configuration.

### 4. Build the trash pickup automation and helper

Create `input_boolean.household_trash_taken_out`, then `automation.household_trash_pickup` —
full YAML in the `ha/` mirror. No chore, no to-do item, no due-date helper.

### 5. Add the dashboard

A minimal dashboard (`/household-chores`) with a `chore-calendar-card` and the trash helper:

```yaml
type: custom:chore-calendar-card
entities:
  - calendar.household_chores
```

The card's resource (`/chore_calendar/chore-calendar-card.js`) is auto-registered by the
integration on install — no manual Lovelace resource step.

### 6. Adding a chore later

`chore_calendar.create_item` against `calendar.household_chores`, or use the card's own "add
chore" dialog. Household: Chore Daily Notify and Household: Task Mark Done need no changes —
both operate generically over whatever `todo.household_chores` currently holds.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household Chores | `calendar.household_chores` | calendar (ha-chore-calendar) |
| Household Chores | `todo.household_chores` | todo (ha-chore-calendar, writable) |
| Household Chores: `<chore>` | `sensor.household_chores_<chore>` | sensor, one per chore |
| Household: Chore Daily Notify | `automation.household_chore_daily_notify` | automation |
| Household: Task Mark Done | `automation.household_task_mark_done` | automation |
| Household: Trash Pickup | `automation.household_trash_pickup` | automation |
| Household Trash Taken Out | `input_boolean.household_trash_taken_out` | input_boolean |

All entities above carry the `reminders` label. `household_chore_daily_notify` and
`household_task_mark_done` also carry `notification`; `household_trash_pickup` carries
`text_to_speech` instead — its only outbound action is `script.household_tts_announce`.

---

## Related Documents

- `LESSONS.md` — the `pending_period < interval` bug (confirmed current, code-verified), and
  the retraction of an earlier "midnight tick" claim that didn't hold up against current
  source. See "Reminders & To-do Lists" and "HACS Integrations".
- `standards/naming.md` §9 — chore name and trash-helper naming.

---

## Troubleshooting

**A chore is stuck `completed` and never comes due**

Check `pending_period` against `interval` on that chore — if `pending_period >= interval` it
is permanently stuck by design of the integration's status computation. Fix by lowering
`pending_period` via `chore_calendar.update_item`; there is no runtime workaround.

**A chore doesn't show as `needs_action` even though it seems overdue**

It may still be dormant (`completed`) because `now` hasn't reached its `pending_at` yet —
ha-chore-calendar chores don't surface in the actionable list until the pending window opens,
even if the *previous* cycle completed long ago. This is expected; check the chore's `due`
attribute on its `sensor.household_chores_<chore>` entity to see exactly when it opens.

**Trash reminders fire even though you already took it out**

Confirm `input_boolean.household_trash_taken_out` is actually `on` — the helper is the only
gate; nothing else silences the reminders. If it reads `on` but a reminder still fired, check
`automation.household_trash_pickup`'s trace for which branch ran.

**Manually running Household: Trash Pickup doesn't announce anything**

Expected — a manual run matches no `condition: trigger` branch and falls into the `default:`
cleanup branch, which only resets the helper. Test the notifying branches by waiting for the
real trigger times, or by toggling `input_boolean.everyone_sleeping` off to exercise the
wake-up branch on demand.
