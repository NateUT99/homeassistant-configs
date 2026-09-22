# Reminder System
*Last updated: September 2026*

---

## Overview

Household chores — including trash pickup — are tracked by the **`ha-chore-calendar`** HACS
integration (`calendar.household_chores` / `todo.household_chores`, one chore per
`sensor.household_chores_*`), which owns scheduling, pending/due/overdue status, and
rescheduling on completion internally. Two automations layer daily push notifications and
lock-screen mark-done on top of the 8 interval chores. Trash pickup is a ninth chore — a
persistent `oneshot` synced live from `calendar.family` rather than a fixed recurrence, so the
real municipal schedule stays authoritative — with its own TTS-only escalation automation
that reads the chore's own due/status directly; no helper, no separate to-do surface. A
`chore-calendar-card` dashboard at `/household-chores` gives create/edit/skip/complete dialogs
for all 9 chores, trash included.

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

Household: Trash Pickup — one persistent oneshot chore (Take Out Trash, persist: true)
  Sync (18:00 daily / HA start / manual), only when the chore is unscheduled or completed:
    find the first calendar.family event matching "Trash" past the chore's current due
    (or today, if unscheduled) → chore_calendar.update_item(oneshot.due_datetime, description)
    An open (not-yet-completed) chore is left untouched -- restart-safe by construction.
  Escalate, reading the chore's own due/status via todo.get_items:
    19:00/19:30/20:00 → if due tomorrow, not completed, someone home
                       → script.household_tts_announce → kitchen
    everyone_sleeping: on → off → if due today, not completed
                       → script.household_tts_announce → master bedroom
  Marking the chore complete (the card, same as any other chore) silences every remaining
  reminder for that cycle -- no helper. chore_calendar.update_item's due-datetime edit on a
  completed oneshot clears its terminal flag, so the next sync reopens it automatically.
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
- *Trash is a persistent `oneshot` chore, synced from `calendar.family` rather than given its
  own `ha-chore-calendar` recurrence.* The real municipal pickup schedule stays authoritative;
  duplicating it into the chore's own RRULE would drift if pickup day ever changed. The sync
  only writes a new `due_datetime` when the chore is unscheduled or completed — an open chore's
  due is already correct, so there is no floor/bump logic to get right at restart boundaries,
  unlike an earlier design that queried the calendar live at every reminder.
- *No helper for trash — the chore's own status is the state.* Marking it complete on the card
  is what silences the rest of that cycle's reminders; `chore_calendar.update_item`'s
  `due_datetime` edit clears the completed oneshot's `terminal` flag automatically on the next
  sync, reopening it for the next cycle with no explicit "reopen" step.
- *`due_datetime` is the evening-before deadline (19:00), not the truck's arrival time.* The
  chore is genuinely "due" when the bin needs to be at the curb, not when the truck picks it
  up the next morning — so the sync sets `due_datetime` to 19:00 the day *before* the matched
  calendar event, not 07:00 the day *of*. This makes the card's own countdown/pending display
  read correctly ("due in 12 hours" now means 12 hours until the real deadline). It also shifts
  the escalation automation's date comparisons by one day from what a same-day due_datetime
  would need: evening reminders check `due == today` (not tomorrow), the wake-up reminder
  checks `due == yesterday` (not today), and the sync's floor for finding the *next* cycle
  after a completion is `due + 2 days` (past both the deadline day and the actual pickup day),
  not `due + 1`. `pending_period: 12h` against a 19:00 due means the chore enters `pending` at
  07:00 the same day — a same-day heads-up on the card, computed by the integration, not
  hardcoded. `grace_period: 12h` keeps it reading `due` (not `overdue`) through the actual
  pickup window the next morning.
- *`todo.update_item` on ha-chore-calendar's entity requires `due_datetime`, not `due_date`.*
  Only `SET_DUE_DATETIME_ON_ITEM` is advertised (verified in `todo.py`); a bare date is
  rejected. Neither chore automation sets a due date via `todo.update_item` — mark-done only
  ever touches `status`; trash's due date is set via `chore_calendar.update_item` instead,
  which requires `entity_id` as a plain string in `data:`, not through `target:` (which always
  expands to a list and this service's schema rejects that) — see `LESSONS.md`.

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

### 4. Add the trash chore and its automation

Create one persistent oneshot chore:

```yaml
action: chore_calendar.create_item
data:
  entity_id: calendar.household_chores
  chore_name: "Take Out Trash"
  oneshot:
    persist: true
  pending_period: {hours: 12}
  grace_period: {hours: 12}
```

It starts unscheduled — the sync half of `automation.household_trash_pickup` (full YAML in the
`ha/` mirror) gives it its first `due_datetime` on its next run, set to 19:00 the evening
*before* the matched pickup event (the actionable deadline), not the pickup morning itself —
see Design Decisions above.

### 5. Add the dashboard

A minimal dashboard (`/household-chores`) with a `chore-calendar-card`, showing all 9 chores
including trash:

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
| Household Chores: `<chore>` | `sensor.household_chores_<chore>` | sensor, one per chore (9, trash included) |
| Household: Chore Daily Notify | `automation.household_chore_daily_notify` | automation |
| Household: Task Mark Done | `automation.household_task_mark_done` | automation |
| Household: Trash Pickup | `automation.household_trash_pickup` | automation |

All entities above carry the `reminders` label. `household_chore_daily_notify` and
`household_task_mark_done` also carry `notification`; `household_trash_pickup` carries
`text_to_speech` instead — its only outbound action is `script.household_tts_announce`.

---

## Related Documents

- `LESSONS.md` — the `pending_period < interval` bug (confirmed current, code-verified), the
  retraction of an earlier "midnight tick" claim that didn't hold up against current source,
  and the `chore_calendar.update_item` `entity_id`-must-be-a-string gotcha. See "Reminders &
  To-do Lists" and "HACS Integrations".
- `standards/naming.md` §9 — chore name naming.

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

Confirm the "Take Out Trash" chore actually shows `completed` on the card or via
`sensor.household_chores_take_out_trash` — that status is the only gate; there is no separate
helper. If it reads `completed` but a reminder still fired, check
`automation.household_trash_pickup`'s trace for which branch ran.

**The trash chore shows `completed` for days after you marked it done, even though the next
pickup is coming up**

Expected — same dormancy as the interval chores (see above). Reopening clears `terminal` but
does not touch `last_completed`, so the chore reads `completed` (dormant) until `now` reaches
the new `pending_at` (12h before the new `due_datetime`). Check `sensor.household_chores_take_out_trash`'s
`next_due` attribute to see exactly when it opens.

**The trash chore's "due" display seems off by a day, or shows a countdown to the wrong time**

Check what `due_datetime` actually is (`sensor.household_chores_take_out_trash`'s `next_due`
attribute) against what you expect it to mean. `due_datetime` is the evening-before deadline
(19:00), never the pickup morning — if it ever shows a 07:00 timestamp on the pickup date
itself, the sync wrote it with the old (pre-correction) formula; delete and recreate the chore,
or push a manual `chore_calendar.update_item` with a correct `oneshot.due_datetime`.

**Manually running Household: Trash Pickup doesn't announce anything**

Expected — a manual run matches no `condition: trigger` branch, so nothing fires (there is no
`default:` branch). Fire `household_task_debug` with `{"branch": "sync"}`, `{"branch":
"escalate_first"}`, `{"branch": "escalate_repeat"}`, or `{"branch": "wakeup"}` from Developer
Tools → Events to exercise a specific branch on demand.
