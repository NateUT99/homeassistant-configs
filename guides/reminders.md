# Reminder System
*Last updated: May 2026*

---

## Overview

A recurring-reminder framework built from native HA helpers and automations. Each reminder tracks a last-done date and a configurable interval; the system automatically computes when the task is next due, marks it overdue, sends an actionable push notification to Nate's iPhone, and closes the loop when the user marks it complete directly from the lock screen.

The framework uses two shared automations that handle every reminder centrally. Per-item configuration is three helpers (last-done date, interval, and an overdue binary sensor) plus a reactive template sensor for the due date. Adding a new reminder requires only creating those artifacts and registering the new sensor in the shared automations.

---

## Architecture

```
input_datetime.<key>       input_number.<key>_offset
        └──────┬───────────────────┘
               ▼ (template sensor, reactive)
   sensor.<key>_due
               ▼
  binary_sensor.<key>_overdue   (template helper: today() >= due)
               │
  off edge ────┘    09:00 daily time trigger
                     │
                     ▼
   automation.manage_reminder_notifications
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
   automation.handle_reminder_mark_complete_action
                     ▼
   input_datetime.<key> ← today()
   (sensor.<key>_due updates reactively → overdue sensor flips off → notification clears)
```

**Key design decisions:**

- *Two shared automations, not one per reminder.* All 8 reminders share `automation.manage_reminder_notifications` and `automation.handle_reminder_mark_complete_action`. New reminders register in two lists; no new automations needed.
- *All notifications send at 09:00.* The daily time trigger is the only send path. No edge-on trigger means no midnight pings when the date rolls over. The `edge_off` trigger remains so the lock-screen notification clears immediately when a reminder is marked complete.
- *Tag-based notification lifecycle.* Each reminder's notification carries a stable `reminder_<key>` tag. The daily re-send replaces (not stacks) the on-screen notification; the clear path uses the same tag. iOS lock screen never accumulates duplicates.
- *Action ID encodes the input_datetime key.* The `REMINDER_MARK_COMPLETE_<key>` action ID doubles as the `input_datetime` entity name suffix. The handler parses it at runtime, requiring no lookup table and routing any reminder with one automation.
- *Due date is a reactive template sensor.* `sensor.<key>_due` computes `last-done + offset` as a template. It updates the moment either `input_datetime.<key>` or `input_number.<key>_offset` changes — no automation needed to keep it in sync.

---

## Prerequisites

- HA Companion app installed on Nate's iPhone (`notify.mobile_app_nates_iphone`)
- Notification actions enabled in the iOS Companion app (Settings → Companion App → Notifications → no restrictions needed beyond standard setup)
- Helpers category `01K6ZGDERD3FBN9BPYKQSBYTGG` exists (all reminder helpers are grouped here for the HA UI)

---

## Adding a New Reminder

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
| Template | `{{ (strptime(states('input_datetime.<key>'), '%Y-%m-%d') + timedelta(days=states('input_number.<key>_offset') \| int)).strftime('%Y-%m-%d') }}` |
| Device class | Date |

Entity ID: `sensor.<key>_due`. The sensor updates reactively whenever either input changes — no automation needed.

**4. Create the overdue binary sensor**

*Helpers → Create Helper → Template → Binary sensor*

| Field | Value |
|---|---|
| Name | `<Object> <Action> Overdue` |
| Template | `{{ now().date() >= strptime(states('sensor.<key>_due'), '%Y-%m-%d').date() }}` |
| Device class | Problem |

Entity ID: `binary_sensor.<key>_overdue`. HA sets it `on` when the template evaluates to `True`.

**5. Register the new sensor in the shared notification automations**

In `automation.household_reminder_notifications`, add `binary_sensor.<key>_overdue` to **both** the `edge_on` trigger's `entity_id` list and the `edge_off` trigger's `entity_id` list. Also add `<key>` (without `_overdue`) to the `for_each` list in the daily branch.

> **Coordinated change:** The `for_each` list in `automation.household_reminder_notifications` and the trigger `entity_id` lists are the canonical registration point for all reminders. Adding a new reminder requires updating all three lists in sync — they are duplicates of the same set.

---

## Shared Automations

### `automation.household_reminder_notifications`

*Friendly name: Household: Reminder Notifications*

Single automation covering the notification lifecycle: sends an actionable notification for each overdue reminder at 09:00 daily, and clears the iOS lock-screen notification when a reminder resolves. All sends go through the daily trigger — there is no edge-on send — so notifications never arrive at midnight when the date rolls over.

```yaml
alias: "Household: Reminder Notifications"
description: >-
  Notification lifecycle for overdue reminders. Sends an actionable iOS notification
  for each overdue reminder at 09:00 daily, and clears the lock-screen notification
  when a reminder flips back to not-overdue.
mode: parallel
max: 8
trigger:
  - id: edge_off
    alias: "Any reminder flips back to not overdue"
    platform: state
    entity_id:
      - binary_sensor.accord_washed_overdue
      - binary_sensor.coffee_grinder_cleaned_overdue
      - binary_sensor.dishwasher_cleaned_overdue
      - binary_sensor.disposal_cleaned_overdue
      - binary_sensor.razor_blade_changed_overdue
      - binary_sensor.toothbrushes_changed_overdue
      - binary_sensor.washer_cleaned_overdue
      - binary_sensor.water_filter_changed_overdue
    to: "off"
  - id: daily
    alias: "9am daily re-check"
    platform: time
    at: "09:00:00"
action:
  - choose:
      - alias: "Edge OFF — clear the notification when reminder completes"
        conditions:
          - condition: trigger
            id: edge_off
        sequence:
          - variables:
              reminder_key: "{{ trigger.to_state.object_id | replace('_overdue', '') }}"
          - alias: "Clear the iOS notification by tag"
            action: notify.mobile_app_nates_iphone
            data:
              message: "clear_notification"
              data:
                tag: "reminder_{{ reminder_key }}"
      - alias: "Daily — notify each reminder still overdue at 9am"
        conditions:
          - condition: trigger
            id: daily
        sequence:
          - alias: "Iterate all reminders"
            repeat:
              for_each:
                - accord_washed
                - coffee_grinder_cleaned
                - dishwasher_cleaned
                - disposal_cleaned
                - razor_blade_changed
                - toothbrushes_changed
                - washer_cleaned
                - water_filter_changed
              sequence:
                - alias: "Notify if currently overdue"
                  if:
                    - condition: template
                      value_template: "{{ is_state('binary_sensor.' ~ repeat.item ~ '_overdue', 'on') }}"
                  then:
                    - alias: "Send actionable iOS notification"
                      action: notify.mobile_app_nates_iphone
                      data:
                        title: "Reminder Overdue"
                        message: >-
                          {{ state_attr('binary_sensor.' ~ repeat.item ~ '_overdue', 'friendly_name')
                             | replace(' Overdue', '') }}
                        data:
                          tag: "reminder_{{ repeat.item }}"
                          actions:
                            - action: "REMINDER_MARK_COMPLETE_{{ repeat.item }}"
                              title: "Mark Complete"
```

### `automation.household_reminder_mark_complete`

*Friendly name: Household: Reminder Mark Complete*

When the user taps *Mark Complete* on a reminder notification, this automation sets the corresponding last-done date to today. The `sensor.<key>_due` template sensor then updates reactively, which flips the overdue binary sensor off, which triggers the edge_off branch above to clear the notification.

```yaml
alias: "Household: Reminder Mark Complete"
description: >-
  When the user taps Mark Complete on a reminder notification, set the corresponding
  last-done date to today. This closes the loop: the due-date template sensor updates
  reactively, the overdue sensor flips off, and the notification clears automatically.
mode: parallel
max: 8
trigger:
  - alias: "iOS notification action fired"
    platform: event
    event_type: mobile_app_notification_action
variables:
  action_id: "{{ trigger.event.data.action | default('') }}"
  reminder_key: "{{ action_id | replace('REMINDER_MARK_COMPLETE_', '') }}"
  target_entity: "input_datetime.{{ reminder_key }}"
condition:
  - alias: "Action is a reminder Mark Complete"
    condition: template
    value_template: "{{ action_id.startswith('REMINDER_MARK_COMPLETE_') }}"
  - alias: "Target input_datetime exists"
    condition: template
    value_template: "{{ states(target_entity) not in ['unknown', 'unavailable'] }}"
action:
  - alias: "Set last-done date to today"
    action: input_datetime.set_datetime
    target:
      entity_id: "{{ target_entity }}"
    data:
      date: "{{ now().strftime('%Y-%m-%d') }}"
```

---

## Worked Example — Accord Washed

**Current configuration (as of May 2026):** last washed 2026-02-17, interval 30 days, due 2026-03-19.

### Per-item helpers

| Helper | Entity ID | Type | Value |
|---|---|---|---|
| Accord Washed | `input_datetime.accord_washed` | `input_datetime` | Last-done date (user-sets to mark complete) |
| Accord Washed Offset | `input_number.accord_washed_offset` | `input_number` | 30 days |
| Accord Washed Due | `sensor.accord_washed_due` | `sensor` (template, date) | `(last-done + 30 days)` computed reactively |
| Accord Washed Overdue | `binary_sensor.accord_washed_overdue` | `binary_sensor` (template) | `on` when today > due |

---

## Roborock Maintenance Notifications

A variant of the reminders pattern scoped to Roborock vacuum consumables. Rather than a calendar-based due date, the Roborock integration itself tracks consumable usage internally and flips four binary sensors to Problem state when maintenance is needed. Notifications fire when the vacuum returns to its dock after cleaning — not on a daily schedule — and include a **Reset** action that presses the corresponding consumable reset button on the integration, closing the loop automatically.

### Architecture

```
vacuum.roborock_q8_max → "returning"
         │
         ▼
automation.roborock_notify_maintenance_needed
  └─ for each binary_sensor.roborock_* in Problem state:
       notify.mobile_app_nates_iphone (tag: roborock_maintenance_<key>)
         │
         │     [User taps Reset]
         ▼
event: mobile_app_notification_action
         ▼
automation.roborock_dispatch_maintenance_reset
         ▼
button.roborock_q8_max_reset_*_consumable
  (Roborock resets counter → sensor flips off → notification clears)

Any sensor flips off (manual or app reset) ──────────────────────────────────┘
  → edge_off branch → clear_notification by tag
```

**Key design decisions:**

- *Dock-return trigger, not daily schedule.* Maintenance needs only become relevant after a cleaning run. Notifying at dock return is timely and avoids daily pings for a problem that changes state only during vacuum cycles.
- *Reset action mirrors the reminders Mark Complete.* Tapping Reset calls `button.press` on the corresponding consumable reset button. The integration resets its internal usage counter, which flips the binary sensor off, which clears the iOS notification — same self-closing lifecycle as the date-based reminders.
- *Per-sensor clearing, not aggregate.* The four sensors clear independently. If two items need attention and you reset one, that notification clears immediately. The other stays until its sensor resolves. This requires watching all four sensors individually in the `sensor_resolved` trigger rather than watching `sensor.roborock_maintenance_required`, which only goes false when all four are off.
- *No per-item helpers.* The Roborock integration tracks consumable usage internally. No `input_datetime`, `input_number`, or due-date template sensor is needed.

### Sensor and reset button mapping

| Binary Sensor | Notification Label | Reset Button |
|---|---|---|
| `binary_sensor.roborock_clean_sensor` | Clean Sensor | `button.roborock_q8_max_reset_sensor_consumable` |
| `binary_sensor.roborock_replace_filter` | Replace Filter | `button.roborock_q8_max_reset_air_filter_consumable` |
| `binary_sensor.roborock_replace_main_brush` | Replace Main Brush | `button.roborock_q8_max_reset_main_brush_consumable` |
| `binary_sensor.roborock_replace_side_brush` | Replace Side Brush | `button.roborock_q8_max_reset_side_brush_consumable` |

### `automation.roborock_notify_maintenance_needed`

*Friendly name: Roborock: Notify maintenance needed*

```yaml
alias: "Roborock: Notify maintenance needed"
description: >-
  When the vacuum returns to its dock, sends an iOS notification for each Roborock
  maintenance sensor currently in Problem state. Each notification includes a Reset
  action that presses the corresponding Roborock consumable reset button. Clears
  automatically when the sensor resolves.
mode: parallel
max: 5
trigger:
  - id: returning_to_dock
    alias: "Vacuum returning to dock"
    platform: state
    entity_id:
      - vacuum.roborock_q8_max
    to: "returning"
  - id: sensor_resolved
    alias: "Maintenance sensor resolved"
    platform: state
    entity_id:
      - binary_sensor.roborock_clean_sensor
      - binary_sensor.roborock_replace_filter
      - binary_sensor.roborock_replace_main_brush
      - binary_sensor.roborock_replace_side_brush
    to: "off"
action:
  - alias: "Route by trigger"
    choose:
      - alias: "Returning to dock — notify for any sensors in Problem state"
        conditions:
          - condition: trigger
            id: returning_to_dock
        sequence:
          - alias: "Check each maintenance sensor"
            repeat:
              for_each:
                - key: roborock_clean_sensor
                  label: "Clean Sensor"
                - key: roborock_replace_filter
                  label: "Replace Filter"
                - key: roborock_replace_main_brush
                  label: "Replace Main Brush"
                - key: roborock_replace_side_brush
                  label: "Replace Side Brush"
              sequence:
                - alias: "Notify if sensor is in Problem state"
                  if:
                    - condition: template
                      value_template: "{{ is_state('binary_sensor.' ~ repeat.item.key, 'on') }}"
                  then:
                    - alias: "Send actionable iOS notification"
                      action: notify.mobile_app_nates_iphone
                      data:
                        title: "Vacuum Maintenance Needed"
                        message: "{{ repeat.item.label }}"
                        data:
                          tag: "roborock_maintenance_{{ repeat.item.key }}"
                          actions:
                            - action: "ROBOROCK_RESET_{{ repeat.item.key }}"
                              title: "Reset"
      - alias: "Sensor resolved — clear lock-screen notification"
        conditions:
          - condition: trigger
            id: sensor_resolved
        sequence:
          - variables:
              sensor_key: "{{ trigger.to_state.object_id }}"
          - alias: "Clear the iOS notification by tag"
            action: notify.mobile_app_nates_iphone
            data:
              message: "clear_notification"
              data:
                tag: "roborock_maintenance_{{ sensor_key }}"
```

### `automation.roborock_dispatch_maintenance_reset`

*Friendly name: Roborock: Dispatch Maintenance Reset*

```yaml
alias: "Roborock: Dispatch Maintenance Reset"
description: >-
  When the user taps Reset on a Roborock maintenance notification, presses the
  corresponding consumable reset button. This resets the Roborock internal counter,
  which flips the maintenance sensor off, which clears the iOS notification automatically.
mode: parallel
max: 4
trigger:
  - alias: "iOS notification action fired"
    platform: event
    event_type: mobile_app_notification_action
variables:
  action_id: "{{ trigger.event.data.action | default('') }}"
  sensor_key: "{{ action_id | replace('ROBOROCK_RESET_', '') }}"
  button_map:
    roborock_clean_sensor: button.roborock_q8_max_reset_sensor_consumable
    roborock_replace_filter: button.roborock_q8_max_reset_air_filter_consumable
    roborock_replace_main_brush: button.roborock_q8_max_reset_main_brush_consumable
    roborock_replace_side_brush: button.roborock_q8_max_reset_side_brush_consumable
  target_button: "{{ button_map[sensor_key] | default('') }}"
condition:
  - alias: "Action is a Roborock reset"
    condition: template
    value_template: "{{ action_id.startswith('ROBOROCK_RESET_') }}"
  - alias: "Target button is valid"
    condition: template
    value_template: "{{ target_button != '' }}"
action:
  - alias: "Press the consumable reset button"
    action: button.press
    target:
      entity_id: "{{ target_button }}"
```

---

## Related HA Config

### Shared automations

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Reminder Notifications | `automation.household_reminder_notifications` | automation |
| Household: Reminder Mark Complete | `automation.household_reminder_mark_complete` | automation |

### Roborock maintenance automations

| Friendly Name | Entity ID | Type |
|---|---|---|
| Roborock: Notify maintenance needed | `automation.roborock_notify_maintenance_needed` | automation |
| Roborock: Dispatch Maintenance Reset | `automation.roborock_dispatch_maintenance_reset` | automation |

### Roborock maintenance sensors

| Friendly Name | Entity ID | Type | Notes |
|---|---|---|---|
| Roborock Maintenance Required | `sensor.roborock_maintenance_required` | sensor (template) | `True` when any of the four Roborock binary sensors is in Problem state |

### Per-reminder helpers

| Reminder | Last-Done Helper | Offset Helper | Due Sensor | Overdue Sensor |
|---|---|---|---|---|
| Accord Washed | `input_datetime.accord_washed` | `input_number.accord_washed_offset` | `sensor.accord_washed_due` | `binary_sensor.accord_washed_overdue` |
| Coffee Grinder Cleaned | `input_datetime.coffee_grinder_cleaned` | `input_number.coffee_grinder_cleaned_offset` | `sensor.coffee_grinder_cleaned_due` | `binary_sensor.coffee_grinder_cleaned_overdue` |
| Dishwasher Cleaned | `input_datetime.dishwasher_cleaned` | `input_number.dishwasher_cleaned_offset` | `sensor.dishwasher_cleaned_due` | `binary_sensor.dishwasher_cleaned_overdue` |
| Disposal Cleaned | `input_datetime.disposal_cleaned` | `input_number.disposal_cleaned_offset` | `sensor.disposal_cleaned_due` | `binary_sensor.disposal_cleaned_overdue` |
| Razor Blade Changed | `input_datetime.razor_blade_changed` | `input_number.razor_blade_changed_offset` | `sensor.razor_blade_changed_due` | `binary_sensor.razor_blade_changed_overdue` |
| Toothbrushes Changed | `input_datetime.toothbrushes_changed` | `input_number.toothbrushes_changed_offset` | `sensor.toothbrushes_changed_due` | `binary_sensor.toothbrushes_changed_overdue` |
| Washer Cleaned | `input_datetime.washer_cleaned` | `input_number.washer_cleaned_offset` | `sensor.washer_cleaned_due` | `binary_sensor.washer_cleaned_overdue` |
| Water Filter Changed | `input_datetime.water_filter_changed` | `input_number.water_filter_changed_offset` | `sensor.water_filter_changed_due` | `binary_sensor.water_filter_changed_overdue` |

---

## Troubleshooting

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

**Notification stacks instead of replacing**

Both the edge_on send and the daily re-send must use the same `tag: reminder_<key>`. If the tag differs between calls (e.g., one uses `binary_sensor.accord_washed_overdue` as the tag and another uses `accord_washed`), iOS treats them as different notifications and stacks them.
