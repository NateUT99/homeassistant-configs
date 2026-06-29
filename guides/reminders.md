# Reminder System
*Last updated: June 2026*

---

## Overview

Three distinct reminder patterns are documented here. They share a common philosophy — actionable iOS notifications with tag-based lifecycle management and a Mark Complete action — but differ in how they determine when to fire and how they close the loop.

| Pattern | Trigger | Close loop via | Use for |
|---|---|---|---|
| **Interval-Based** | Interval since last done | Mark Complete → set last-done date | Regular maintenance tasks (car wash, filter change, etc.) |
| **Sensor-Threshold** | Vacuum returns to dock | Mark Complete → press integration reset button | Consumable-driven maintenance tied to vacuum usage |
| **Calendar-Driven** | Calendar event tomorrow | Mark Complete → disarm pending boolean | Fixed-schedule events driven by an external calendar |

---

## Interval-Based Reminders

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

**5. Register the new sensor in the shared notification automations**

In `automation.household_reminder_notifications`, add `binary_sensor.<key>_overdue` to **both** the `edge_on` trigger's `entity_id` list and the `edge_off` trigger's `entity_id` list. Also add `<key>` (without `_overdue`) to the `for_each` list in the daily branch.

> **Coordinated change:** The `for_each` list in `automation.household_reminder_notifications` and the trigger `entity_id` lists are the canonical registration point for all reminders. Adding a new reminder requires updating all three lists in sync — they are duplicates of the same set.

**6. Add the task card to the mobile dashboard**

New tasks must be added to the `mobile-home` dashboard in the `#reminders` pop-up. The pop-up is organized into three sections — **Overdue**, **Upcoming**, and **Current** — and each reminder appears once per section (three card instances total per reminder), each gated by a `visibility` condition that determines which section it renders in.

In Bubble Card, `hold_action` at the top level binds to the icon area — use `button_action.hold_action` to bind to the card body where the user expects to hold:

```yaml
# Template for all three section instances — change `styles` and `visibility` per section
type: custom:bubble-card
card_type: button
button_type: state
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

**Overdue instance** — place after the Overdue separator:
```yaml
styles: "ha-icon { color: var(--error-color) !important; }"
visibility:
  - condition: state
    entity: binary_sensor.<key>_overdue
    state: "on"
```

**Upcoming instance** — place after the Upcoming separator:
```yaml
styles: "ha-icon { color: var(--warning-color) !important; }"
visibility:
  - condition: template
    value_template: >-
      {% set d = states('sensor.<key>_due') %}
      {{ is_state('binary_sensor.<key>_overdue','off') and d not in ['unknown','unavailable']
         and (strptime(d, '%B %d, %Y').date() - now().date()).days <= 7 }}
```

**Current instance** — place after the Current header card:
```yaml
styles: "ha-icon { color: var(--success-color) !important; }"
visibility:
  - condition: state
    entity: input_boolean.mobile_show_reminders_current
    state: "on"
  - condition: template
    value_template: >-
      {% set d = states('sensor.<key>_due') %}
      {{ is_state('binary_sensor.<key>_overdue','off') and d not in ['unknown','unavailable']
         and (strptime(d, '%B %d, %Y').date() - now().date()).days > 7 }}
```

The Upcoming separator's visibility template must also be updated to include the new reminder key so it shows when the new reminder is in the 7-day window. Locate the Upcoming separator card and add `'<key>'` to its `keys` list.

> **Coordinated change:** Adding a new reminder requires four artifacts (helpers + template sensors) plus three `#reminders` pop-up card instances (one per section) and an update to the Upcoming separator's aggregate template. All must be kept in sync with the automation registrations in step 5. `script.reminder_mark_complete` is shared — no script changes needed when adding a new reminder.

### Shared Scripts & Automations

#### `automation.household_reminder_notifications`

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

Assign to the **Routines** category with labels **Notification**, **Reminders**, and **Whole Home**. Leave area unset.

#### `automation.household_reminder_mark_complete`

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

Assign to the **Routines** category with labels **Reminders** and **Whole Home**. Leave area unset.

#### `script.reminder_mark_complete`

*Friendly name: Reminder: Mark Complete*

Sets the given `input_datetime` entity to today's date. All reminder cards on the dashboard call this script for their hold action. The script exists because Jinja2 templates in Lovelace card action `data` fields are not evaluated by the frontend — the date string `{{ now().strftime('%Y-%m-%d') }}` is passed literally to the service and fails validation. Running the same logic inside a script works because scripts execute server-side where Jinja2 templates are always evaluated.

```yaml
alias: "Reminder: Mark Complete"
description: >-
  Sets the given input_datetime entity to today's date, marking a reminder as
  done. Called from dashboard reminder cards — Jinja2 templates in Lovelace
  card action data are not evaluated by the frontend. Any action that needs
  the current date must be routed through a server-side script where templates
  are evaluated normally.
icon: mdi:calendar-check
fields:
  reminder_entity:
    description: The input_datetime entity to set to today
    required: true
    selector:
      entity:
        domain: input_datetime
sequence:
  - action: input_datetime.set_datetime
    target:
      entity_id: "{{ reminder_entity }}"
    data:
      date: "{{ now().strftime('%Y-%m-%d') }}"
mode: parallel
max: 8
```

Assign to the **Routines** category with label **Reminders**. Leave area unset.

### Example: Household Maintenance Tasks

The eight household maintenance reminders currently configured follow the interval-based pattern. All share the two automations above; only their per-item helpers differ.

#### Current reminders

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

#### Worked example — Accord Washed

**Current configuration (as of May 2026):** last washed 2026-02-17, interval 30 days, due 2026-03-19.

| Helper | Entity ID | Type | Value |
|---|---|---|---|
| Accord Washed | `input_datetime.accord_washed` | `input_datetime` | Last-done date (user-sets to mark complete) |
| Accord Washed Offset | `input_number.accord_washed_offset` | `input_number` | 30 days |
| Accord Washed Due | `sensor.accord_washed_due` | `sensor` (template) | `(last-done + 30 days)` as formatted string, e.g. `March 19, 2026` |
| Accord Washed Overdue | `binary_sensor.accord_washed_overdue` | `binary_sensor` (template) | `on` when today >= due |

### Related HA Config

#### Shared scripts & automations

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Reminder Notifications | `automation.household_reminder_notifications` | automation |
| Household: Reminder Mark Complete | `automation.household_reminder_mark_complete` | automation |
| Reminder: Mark Complete | `script.reminder_mark_complete` | script |

#### Per-reminder helpers

See the Current reminders table above.

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

**Notification stacks instead of replacing**

Both the edge_on send and the daily re-send must use the same `tag: reminder_<key>`. If the tag differs between calls (e.g., one uses `binary_sensor.accord_washed_overdue` as the tag and another uses `accord_washed`), iOS treats them as different notifications and stacks them.

---

## Sensor-Threshold Notifications

A pattern for maintenance tasks where an external integration — not a user-managed date — tracks usage and signals when attention is needed. The trigger is a sensor flipping to Problem state, not a time-based due date. Notifications fire when a relevant event occurs (e.g., the vacuum returning to its dock), and the close-the-loop action interacts with the integration directly (pressing a reset button) rather than updating a date helper.

This pattern requires no per-item date or interval helpers. The integration owns the usage tracking; HA just observes the sensor state and routes notifications.

### Example: Roborock Consumables

The Roborock integration tracks four consumables internally and flips binary sensors to Problem state when each item needs maintenance. Notifications fire when the vacuum returns to its dock after a cleaning run. Tapping Reset on the notification presses the corresponding integration reset button, which resets the internal counter and resolves the sensor automatically.

#### Architecture

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

#### Sensor and Reset Button Mapping

| Binary Sensor | Notification Label | Reset Button |
|---|---|---|
| `binary_sensor.roborock_clean_sensor` | Clean Sensor | `button.roborock_q8_max_reset_sensor_consumable` |
| `binary_sensor.roborock_replace_filter` | Replace Filter | `button.roborock_q8_max_reset_air_filter_consumable` |
| `binary_sensor.roborock_replace_main_brush` | Replace Main Brush | `button.roborock_q8_max_reset_main_brush_consumable` |
| `binary_sensor.roborock_replace_side_brush` | Replace Side Brush | `button.roborock_q8_max_reset_side_brush_consumable` |

#### `automation.roborock_notify_maintenance_needed`

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

Assign to the **Maintenance** category with labels **Notification** and **Reminders**. Leave area unset.

#### `automation.roborock_dispatch_maintenance_reset`

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

Assign to the **Maintenance** category with label **Reminders**. Leave area unset.

#### Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Roborock: Notify maintenance needed | `automation.roborock_notify_maintenance_needed` | automation |
| Roborock: Dispatch Maintenance Reset | `automation.roborock_dispatch_maintenance_reset` | automation |
| Roborock Maintenance Required | `sensor.roborock_maintenance_required` | sensor (template) |

---

## Calendar-Driven Reminders

A pattern for fixed-schedule events where the schedule is owned by an external calendar rather than by HA helpers. HA queries the calendar for upcoming events and sends notifications based on what it finds. Because the calendar is the source of truth, there is no last-done date or interval to manage — only a pending boolean that carries state across the notification lifecycle.

This pattern suits events that recur on a predictable external schedule (weekly, biweekly, seasonal) and where the notification timing is tied to the event date rather than an interval since last action. It uses a two-stage notification: an evening send the day before, and a critical escalation on the morning of the event if not yet acknowledged.

### Example: Trash & Recycling Pickup

The pickup schedule lives in an iCloud-published calendar subscribed in HA as `calendar.family` via the Remote Calendar integration. Single all-day events drive the logic: **"Trash Pickup"** (weekly, every Wednesday) and **"Trash & Recycling Pickup"** (biweekly, every other Wednesday). The event title directly encodes whether recycling is included that week — no separate series to correlate.

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

#### `automation.household_pickup_reminder`

*Friendly name: Household: Trash Pickup Reminder*

```yaml
alias: "Household: Trash Pickup Reminder"
description: >-
  At 19:00, queries the Family calendar for tomorrow and sends a push + TTS
  notification if pickup is found, arming the pending boolean. At 20:00, sends
  a TTS repeat if pickup is still pending and someone is home. The 07:00
  morning critical fires if still unacknowledged.
mode: single
trigger:
  - id: evening_check
    alias: "7pm daily check"
    platform: time
    at: "19:00:00"
  - id: tts_repeat
    alias: "8pm TTS repeat"
    platform: time
    at: "20:00:00"
action:
  - alias: "Route by trigger"
    choose:
      - alias: "Evening check — query calendar, send push + TTS, arm pending"
        conditions:
          - condition: trigger
            id: evening_check
        sequence:
          - alias: "Compute tomorrow's window"
            variables:
              tomorrow_start: "{{ (now() + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00') }}"
              tomorrow_end: "{{ (now() + timedelta(days=1)).strftime('%Y-%m-%d 23:59:59') }}"
          - alias: "Fetch tomorrow's events from the Family calendar"
            action: calendar.get_events
            target:
              entity_id: calendar.family
            data:
              start_date_time: "{{ tomorrow_start }}"
              end_date_time: "{{ tomorrow_end }}"
            response_variable: family_events
          - alias: "Extract pickup event from response"
            variables:
              summaries: >-
                {{ family_events['calendar.family']['events']
                   | map(attribute='summary') | list }}
              has_pickup: >-
                {{ 'Trash Pickup' in summaries or 'Trash & Recycling Pickup' in summaries }}
              label: >-
                {%- if 'Trash & Recycling Pickup' in summaries -%}Trash & Recycling
                {%- else -%}Trash
                {%- endif -%}
          - alias: "Store the label for the morning critical reminder"
            action: input_text.set_value
            target:
              entity_id: input_text.trash_pickup_pending_label
            data:
              value: "{{ label }}"
          - alias: "Store the pickup date for dashboard display"
            action: input_text.set_value
            target:
              entity_id: input_text.trash_next_pickup_date
            data:
              value: "{{ (now() + timedelta(days=1)).strftime('%a, %b %-d') }}"
          - alias: "Arm or clear pending based on tomorrow's events"
            choose:
              - alias: "Pickup tomorrow — arm pending and send notification"
                conditions:
                  - condition: template
                    value_template: "{{ has_pickup }}"
                sequence:
                  - alias: "Arm the pending state"
                    action: input_boolean.turn_on
                    target:
                      entity_id: input_boolean.trash_pickup_pending
                  - alias: "Send actionable iOS notification"
                    action: notify.mobile_app_nates_iphone
                    data:
                      title: "Pickup Tomorrow"
                      message: "{{ label }} bin{{ 's' if '&' in label else '' }} out tonight"
                      data:
                        tag: "pickup"
                        actions:
                          - action: "PICKUP_MARK_COMPLETE"
                            title: "Mark Complete"
                  - alias: "Send audio announcement to kitchen if someone is home"
                    if:
                      - condition: numeric_state
                        entity_id: zone.home
                        above: 0
                    then:
                      - alias: "Send TTS announcement to Kitchen HomePod"
                        action: notify.reminder_kitchen
                        metadata: {}
                        data:
                          message: "Don't forget, the {{ label }} bin{{ 's' if '&' in label else '' }} need{{ '' if '&' in label else 's' }} to go out tonight!"
            default:
              - alias: "No pickup tomorrow — clear pending (housekeeping)"
                action: input_boolean.turn_off
                target:
                  entity_id: input_boolean.trash_pickup_pending
      - alias: "8pm TTS repeat — if pickup still pending and someone home"
        conditions:
          - condition: trigger
            id: tts_repeat
          - condition: state
            entity_id: input_boolean.trash_pickup_pending
            state: "on"
          - condition: numeric_state
            entity_id: zone.home
            above: 0
        sequence:
          - alias: "Read stored label"
            variables:
              label: "{{ states('input_text.trash_pickup_pending_label') }}"
          - alias: "Send TTS repeat to Kitchen HomePod"
            action: notify.reminder_kitchen
            metadata: {}
            data:
              message: "Reminder — the {{ label }} bin{{ 's' if '&' in label else '' }} still need{{ '' if '&' in label else 's' }} to go out tonight!"
```

Assign to the **Routines** category with labels **Notification**, **text_to_speech**, and **Reminders**. Leave area unset.

#### `automation.household_pickup_morning_critical`

*Friendly name: Household: Trash Pickup Morning Critical*

```yaml
alias: "Household: Trash Pickup Morning Critical"
description: >-
  At 07:00, if trash pickup is still pending, sends a critical iOS alarm but
  leaves the pending boolean armed so the dashboard chip stays visible (red).
  At 09:00, if still pending, silently disarms — the mark_complete edge_off
  then clears the iOS notification. Requires Critical Alerts entitlement on
  the iPhone Companion app.
mode: single
trigger:
  - id: critical
    alias: "7am critical alarm"
    platform: time
    at: "07:00:00"
  - id: cleanup
    alias: "9am cleanup"
    platform: time
    at: "09:00:00"
condition:
  - alias: "Pickup still pending"
    condition: state
    entity_id: input_boolean.trash_pickup_pending
    state: "on"
action:
  - alias: "Route by trigger"
    choose:
      - alias: "7am — send critical alarm, leave pending armed"
        conditions:
          - condition: trigger
            id: critical
        sequence:
          - alias: "Capture the stored label"
            variables:
              label: "{{ states('input_text.trash_pickup_pending_label') }}"
          - alias: "Send critical iOS alarm"
            action: notify.mobile_app_nates_iphone
            data:
              title: "Pickup TODAY"
              message: "{{ label }} bin{{ 's' if '&' in label else '' }} out NOW"
              data:
                push:
                  sound:
                    name: default
                    critical: 1
                    volume: 1.0
                tag: "pickup"
                actions:
                  - action: "PICKUP_MARK_COMPLETE"
                    title: "Mark Complete"
      - alias: "9am — silently disarm if still pending"
        conditions:
          - condition: trigger
            id: cleanup
        sequence:
          - alias: "Disarm pending boolean"
            action: input_boolean.turn_off
            target:
              entity_id: input_boolean.trash_pickup_pending
```

Assign to the **Routines** category with labels **Notification** and **Reminders**. Leave area unset.

#### `automation.household_pickup_mark_complete`

*Friendly name: Household: Trash Pickup Mark Complete*

```yaml
alias: "Household: Trash Pickup Mark Complete"
description: >-
  Disarms input_boolean.trash_pickup_pending and clears the iOS lock-screen
  notification by tag whenever the boolean turns off from any source: a
  notification Mark Complete tap, a dashboard hold action, or the morning
  critical automation. The edge_off trigger covers the dashboard-dismiss path;
  the notification_action trigger covers the iOS lock-screen path. Both action
  sequences are idempotent, so running both (the notification action turns off
  the boolean, which re-fires edge_off) is harmless.
mode: parallel
max: 2
trigger:
  - id: notification_action
    alias: "iOS notification Mark Complete tapped"
    platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "PICKUP_MARK_COMPLETE"
  - id: edge_off
    alias: "Pending boolean turned off from dashboard or other source"
    platform: state
    entity_id: input_boolean.trash_pickup_pending
    from: "on"
    to: "off"
action:
  - alias: "Disarm pending state"
    action: input_boolean.turn_off
    target:
      entity_id: input_boolean.trash_pickup_pending
  - alias: "Clear the iOS notification by tag"
    action: notify.mobile_app_nates_iphone
    data:
      message: "clear_notification"
      data:
        tag: "pickup"
```

Assign to the **Routines** category with labels **Notification** and **Reminders**. Leave area unset.

#### Dashboard Integration

The trash pickup pending state is surfaced directly on the `mobile-app` dashboard alongside the interval-based overdue reminders:

- **Chip strip trash button** — a conditional sub-button in the second row (position 7, after washer/dryer). Visible only when `input_boolean.trash_pickup_pending` is on. Icon only — no text. Icon is `mdi:trash-can` on trash-only weeks or `mdi:recycle` on combined weeks, derived from `input_text.trash_pickup_pending_label`. Color is orange (19:00–06:59, evening before pickup) or red (07:00–18:59, morning of pickup day). Hold = turn off the boolean with confirmation. Tap = no action.
- **`#reminders` pop-up** — trash is no longer shown here. The pop-up contains only the interval-based maintenance reminder cards.
- **`number.overdue_reminders_count` template** — counts only interval-based `binary_sensor.*_overdue` sensors in `on` state. Trash pickup pending is no longer included in this count.

The `edge_off` trigger on `automation.household_pickup_mark_complete` handles the dashboard-dismiss path: holding the trash chip turns off the boolean, which fires the trigger, which clears the iOS notification — identical outcome to tapping Mark Complete on the lock screen.

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
