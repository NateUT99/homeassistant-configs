# Home Alarm

*Last updated: June 2026*

---

## Overview

The home alarm uses HA's built-in Manual Alarm Control Panel as the state machine and two automations to handle perimeter detection and notifications. When the alarm is armed and a monitored sensor opens — an exterior door, window, garage door, or person detected by the kitchen camera — the perimeter trigger automation records what fired, optionally saves a camera snapshot, and trips the panel. The notification automation reacts to the panel's state changes: sending critical iOS pushes naming the specific trigger, engaging the Reolink camera siren when no one is home, and sending an immediate follow-up with a camera image if a person is subsequently detected while the alarm is active.

---

## Architecture

```
  Perimeter sensors                Kitchen camera
  (doors, windows,                 binary_sensor.kitchen_camera_person
   garage door)                              │
        │                                    │
        └──────────────┬─────────────────────┘
                       ▼
   automation.household_alarm_perimeter_trigger
        │   (mode: single)
        ├─ writes trigger description to input_text.alarm_trigger_description
        ├─ if person detected: saves snapshot → /config/www/snapshots/alarm_latest.jpg
        └─ calls alarm_control_panel.alarm_trigger
                       │
                       ▼
         alarm_control_panel.home_alarm
           state: triggered
                       │
                       ▼
   automation.household_alarm_state_notifications
        │   (mode: parallel, max: 3)
        │
        ├─ triggered branch:
        │    ├─ siren.turn_on (60s, armed_away only)
        │    ├─ tts.speak if everyone_sleeping
        │    └─ repeat every 90s (max 10):
        │         critical push naming trigger + optional snapshot image
        │         (stops early if alarm leaves triggered state)
        │         → siren.turn_off after loop exits
        │
        ├─ person_while_triggered branch (separate execution):
        │    fires when binary_sensor.kitchen_camera_person → on (3s debounce)
        │    while alarm is triggered AND person was not the original trigger
        │    ├─ saves fresh snapshot
        │    └─ critical push with image (tag: home_alarm_person)
        │
        ├─ armed branch:
        │    └─ standard push (tag: home_alarm)
        │
        └─ disarmed branch:
             ├─ siren.turn_off
             └─ disarmed confirmation push (replaces home_alarm tag)
```

**Key design decisions:**

- *Two-automation split.* The perimeter trigger writes context before tripping the panel; the notification automation reads it after the state change. This is more reliable than merging — if both lived in one automation, the notification branch would read state that the trigger branch had already mutated. (See LESSONS.md.)
- *`input_text` as the context bridge.* `input_text.alarm_trigger_description` carries the human-readable trigger name between automations. Synchronous HA service calls ensure the helper is written before the panel state transitions.
- *Snapshot at trigger time, not notification delivery time.* `camera.snapshot` runs immediately when person detection fires or when a follow-up detection occurs while triggered. The static file `/config/www/snapshots/alarm_latest.jpg` is what iOS fetches when the notification arrives — not a live proxy.
- *Siren gated on prior arm state.* The notification automation checks `trigger.from_state.state == 'armed_away'` to decide whether to activate the siren. Armed away = no one home = siren appropriate. Armed night = someone sleeping = no siren.
- *Person follow-up deduplication.* If person detection was the original trigger, `input_text.alarm_trigger_description` already contains "Person Detected". The `person_while_triggered` branch skips itself in that case to avoid a duplicate notification.
- *Audio backend is inline.* `siren.turn_on` / `siren.turn_off` are called directly in the notification automation. If HomePods or a hybrid audio approach is added later, edit the `triggered` and `disarmed` branches of `automation.household_alarm_state_notifications` — the siren calls are clearly aliased.

---

## Prerequisites

- Manual Alarm Control Panel configured in `configuration.yaml` (see **Alarm Panel Configuration** below for the snapshot)
- Alarm disarm code stored in `secrets.yaml` as `alarm_code` (migrated from plaintext in May 2026)
- Reolink kitchen camera integrated via the Reolink integration, with AI person detection enabled
- `notify.mobile_app_nates_iphone` available
- Master bedroom HomePod available as `media_player.master_bedroom_homepod` for TTS
- `/config/www/snapshots/` directory created on the HA host (see **Setup** below)

---

## Setup

### Create the snapshot directory

The camera snapshot step writes to `/config/www/snapshots/alarm_latest.jpg`. HA does not create missing parent directories — if `snapshots/` does not exist, the step fails silently. Create it once via the Terminal & SSH add-on or File Editor:

```bash
mkdir -p /config/www/snapshots
```

The `/config/www/` path is served by HA at `/local/`. A file at `/config/www/snapshots/alarm_latest.jpg` is accessible in notifications as `/local/snapshots/alarm_latest.jpg`.

---

## Alarm Panel Configuration

> **Note:** The Manual Alarm Control Panel is configured in `configuration.yaml` on the HA host — not in this repo. The table below is a snapshot captured June 2026 for disaster recovery reference. Treat `configuration.yaml` as the authoritative source.

| Attribute | Value |
|---|---|
| Entity ID | `alarm_control_panel.home_alarm` |
| Friendly name | Home Alarm |
| `code_format` | `number` |
| `code_arm_required` | `false` (arm without code; disarm requires code) |
| Supported features | 14 (arm_away, arm_home/night, trigger) |
| Disarm code | `!secret alarm_code` |

Typical `configuration.yaml` stanza for reference:

```yaml
alarm_control_panel:
  - platform: manual
    name: Home Alarm
    code: !secret alarm_code
    code_arm_required: false
    arming_time: 30
    delay_time: 30
    trigger_time: 300
    disarmed:
      trigger_time: 0
    armed_home:
      arming_time: 0
      delay_time: 0
```

> **Coordinated change:** If arming/delay/trigger times change in `configuration.yaml`, update this stanza to match.

---

## State Helpers

| Friendly Name | Entity ID | Type | Role |
|---|---|---|---|
| Alarm Trigger Description | `input_text.alarm_trigger_description` | `input_text` | Carries the human-readable trigger name from the perimeter trigger automation to the notification automation. Written before the alarm panel is tripped; read when composing push message text and deciding whether to attach a snapshot. |

---

## Automations

### `automation.household_alarm_perimeter_trigger`

*Friendly name: Household: Alarm Perimeter Trigger*

Monitors the five perimeter sensors and the kitchen camera's person detection binary sensor. When the alarm is armed and any trigger fires, it records a description of what opened, optionally captures a camera snapshot, then trips the panel.

The `variables` block computes the trigger description at fire time using `trigger.entity_id` and live sensor state. The description is written to `input_text.alarm_trigger_description` before calling `alarm_control_panel.alarm_trigger` to guarantee the helper is set before the notification automation reads it.

> **Coordinated change:** `trigger_description` hard-codes the five individual perimeter sensor entity IDs in its `sensor_map`. If a new exterior sensor is added (or renamed), add it to both the trigger list and the `sensor_map` dictionary.

```yaml
alias: "Household: Alarm Perimeter Trigger"
description: >-
  If the home alarm is armed (away or night) and a perimeter sensor opens,
  trigger the alarm. The kitchen camera is only honored when armed away, so
  normal nighttime movement in the kitchen does not trigger the alarm.
  Before triggering, stores the trigger source in
  input_text.alarm_trigger_description so the notification automation can
  name it in the push message. When person detection fires, also saves a
  camera snapshot to /config/www/snapshots/alarm_latest.jpg.
mode: single
variables:
  trigger_description: >-
    {%- if trigger.entity_id == 'cover.garage_door_garage' -%}
    Garage Door Opened
    {%- elif trigger.entity_id == 'binary_sensor.kitchen_camera_person' -%}
    Person Detected (Kitchen Camera)
    {%- else -%}
      {%- set sensor_map = {
        'binary_sensor.entrance_front_door_contact': 'Front Door',
        'binary_sensor.office_sliding_door_contact': 'Office Sliding Door',
        'binary_sensor.garage_interior_door_contact': 'Garage Interior Door',
        'binary_sensor.master_bedroom_windows': 'Master Bedroom Windows',
        'binary_sensor.avery_room_window': 'Avery Room Window'
      } -%}
      {%- set ns = namespace(found=[]) -%}
      {%- for eid, label in sensor_map.items() -%}
        {%- if is_state(eid, 'on') -%}
          {%- set ns.found = ns.found + [label] -%}
        {%- endif -%}
      {%- endfor -%}
      {{ (ns.found | join(', ') + ' Opened') if ns.found else 'Unknown sensor' }}
    {%- endif %}
trigger:
  - alias: "Garage door opened"
    platform: state
    entity_id: cover.garage_door_garage
    id: perimeter

  - alias: "Exterior door or window opened"
    platform: state
    entity_id: binary_sensor.exterior_door_window_open
    to: "on"
    id: perimeter

  - alias: "Kitchen camera detected a person"
    platform: state
    entity_id: binary_sensor.kitchen_camera_person
    to: "on"
    id: interior_motion

condition:
  - alias: "Alarm is armed (away or night)"
    condition: or
    conditions:
      - condition: state
        entity_id: alarm_control_panel.home_alarm
        state: armed_away
      - condition: state
        entity_id: alarm_control_panel.home_alarm
        state: armed_night

action:
  - alias: "Route by alarm state"
    choose:
      - alias: "Armed away - any perimeter or interior motion trigger"
        conditions:
          - condition: state
            entity_id: alarm_control_panel.home_alarm
            state: armed_away
        sequence:
          - alias: "Record trigger description"
            action: input_text.set_value
            target:
              entity_id: input_text.alarm_trigger_description
            data:
              value: "{{ trigger_description | trim }}"

          - alias: "Save camera snapshot if person detected"
            if:
              - alias: "Trigger was person detection"
                condition: template
                value_template: >-
                  {{ trigger.entity_id == 'binary_sensor.kitchen_camera_person' }}
            then:
              - alias: "Snapshot kitchen camera to disk"
                action: camera.snapshot
                target:
                  entity_id: camera.kitchen_camera_fluent
                data:
                  filename: /config/www/snapshots/alarm_latest.jpg

          - alias: "Trigger the alarm"
            action: alarm_control_panel.alarm_trigger
            target:
              entity_id: alarm_control_panel.home_alarm

      - alias: "Armed night - perimeter only (ignore interior motion)"
        conditions:
          - condition: state
            entity_id: alarm_control_panel.home_alarm
            state: armed_night
          - condition: trigger
            id: perimeter
        sequence:
          - alias: "Record trigger description"
            action: input_text.set_value
            target:
              entity_id: input_text.alarm_trigger_description
            data:
              value: "{{ trigger_description | trim }}"

          - alias: "Trigger the alarm"
            action: alarm_control_panel.alarm_trigger
            target:
              entity_id: alarm_control_panel.home_alarm
```

---

### `automation.household_alarm_state_notifications`

*Friendly name: Household: Alarm State Notifications*

Reacts to alarm panel state changes. All alarm notifications share the `home_alarm` tag so each new state replaces the previous notification — no stacking except for the `home_alarm_person` follow-up tag.

The `triggered` branch starts the siren (armed_away only) and runs a critical-push loop every 90 seconds. The `person_while_triggered` branch fires independently on person detection while the alarm is active, sending a fresh snapshot immediately. The `disarmed` branch stops the siren and clears the notification.

```yaml
alias: "Household: Alarm State Notifications"
description: >-
  Handles the full push notification lifecycle for the home alarm panel.
  All notifications share the home_alarm tag so each new state replaces
  the previous notification — no stacking.

  Triggered: Activates the camera siren for 60s (armed_away only). Sends
  a critical push every 90s for up to 10 iterations naming the triggering
  sensor from input_text.alarm_trigger_description; attaches a camera
  snapshot when person detection fired. Also plays TTS if everyone is
  sleeping. Stops siren after the loop or on disarm.

  Person detected while triggered: If person detection fires after a
  door/window caused the initial trigger, sends an immediate followup
  critical push with a fresh snapshot (tag home_alarm_person — stacks
  alongside the main alarm notification). Skipped if person detection
  was the original trigger.

  Disarmed: Stops siren and replaces the active alarm notification with
  a disarmed confirmation.
mode: parallel
max: 3

trigger:
  - alias: "Alarm enters triggered state"
    platform: state
    entity_id: alarm_control_panel.home_alarm
    to: triggered
    id: triggered

  - alias: "Alarm enters armed away mode"
    platform: state
    entity_id: alarm_control_panel.home_alarm
    to: armed_away
    id: armed

  - alias: "Alarm enters armed night mode"
    platform: state
    entity_id: alarm_control_panel.home_alarm
    to: armed_night
    id: armed

  - alias: "Alarm is disarmed"
    platform: state
    entity_id: alarm_control_panel.home_alarm
    to: disarmed
    id: disarmed

  - alias: "Kitchen camera detects person while alarm is triggered"
    platform: state
    entity_id: binary_sensor.kitchen_camera_person
    to: "on"
    for:
      seconds: 3
    id: person_while_triggered

condition: []

action:
  - alias: "Route by alarm state"
    choose:
      - alias: "Triggered — activate siren, repeat critical push until state changes"
        conditions:
          - condition: trigger
            id: triggered
        sequence:
          - alias: "Activate siren if armed away (no one home)"
            if:
              - alias: "Prior alarm state was armed away"
                condition: template
                value_template: "{{ trigger.from_state.state == 'armed_away' }}"
            then:
              - alias: "Turn on kitchen camera siren for 60 seconds at full volume"
                action: siren.turn_on
                target:
                  entity_id: siren.kitchen_camera_siren
                data:
                  duration: 60
                  volume_level: 1

          - alias: "Announce alarm via TTS if everyone is sleeping"
            if:
              - alias: "Everyone is sleeping"
                condition: state
                entity_id: input_boolean.everyone_sleeping
                state: "on"
            then:
              - alias: "Speak alarm alert to master bedroom HomePod"
                action: tts.speak
                target:
                  entity_id: tts.home_assistant_cloud
                data:
                  media_player_entity_id: media_player.master_bedroom_homepod
                  message: "Alert! The home alarm has been triggered. {{ states('input_text.alarm_trigger_description') | trim }}."

          - alias: "Send critical notifications every 90s while triggered (max 10)"
            repeat:
              count: 10
              sequence:
                - alias: "Stop if alarm is no longer triggered"
                  if:
                    - alias: "Alarm has left triggered state"
                      condition: not
                      conditions:
                        - condition: state
                          entity_id: alarm_control_panel.home_alarm
                          state: triggered
                  then:
                    - alias: "Exit the loop"
                      stop: "Alarm no longer triggered"

                - alias: "Send push — person detected (with camera snapshot)"
                  if:
                    - alias: "Trigger was person detection"
                      condition: template
                      value_template: >-
                        {{ 'Person Detected' in states('input_text.alarm_trigger_description') }}
                  then:
                    - alias: "Send critical push with camera image"
                      action: notify.mobile_app_nates_iphone
                      data:
                        title: "Colony Drive"
                        message: "🚨 {{ states('input_text.alarm_trigger_description') | trim }}"
                        data:
                          push:
                            sound:
                              name: default
                              critical: 1
                              volume: 1
                          tag: home_alarm
                          image: /local/snapshots/alarm_latest.jpg
                  else:
                    - alias: "Send critical push to iPhone"
                      action: notify.mobile_app_nates_iphone
                      data:
                        title: "Colony Drive"
                        message: "🚨 {{ states('input_text.alarm_trigger_description') | trim }}"
                        data:
                          push:
                            sound:
                              name: default
                              critical: 1
                              volume: 1
                          tag: home_alarm

                - alias: "Wait before re-notifying"
                  delay:
                    seconds: 90

          - alias: "Stop siren after notification loop ends"
            action: siren.turn_off
            target:
              entity_id: siren.kitchen_camera_siren

      - alias: "Person detected while alarm is triggered — send followup with snapshot"
        conditions:
          - condition: trigger
            id: person_while_triggered
          - condition: state
            entity_id: alarm_control_panel.home_alarm
            state: triggered
          - alias: "Person was not the original alarm trigger"
            condition: template
            value_template: >-
              {{ 'Person Detected' not in states('input_text.alarm_trigger_description') }}
        sequence:
          - alias: "Save fresh camera snapshot"
            action: camera.snapshot
            target:
              entity_id: camera.kitchen_camera_fluent
            data:
              filename: /config/www/snapshots/alarm_latest.jpg

          - alias: "Send critical push with person image"
            action: notify.mobile_app_nates_iphone
            data:
              title: "Colony Drive"
              message: "🚨 Person Detected (Kitchen Camera)"
              data:
                push:
                  sound:
                    name: default
                    critical: 1
                    volume: 1
                tag: home_alarm_person
                image: /local/snapshots/alarm_latest.jpg

      - alias: "Armed — send standard armed notification"
        conditions:
          - condition: trigger
            id: armed
        sequence:
          - alias: "Send armed notification to iPhone"
            action: notify.mobile_app_nates_iphone
            data:
              title: "Colony Drive"
              message: "🚨 Alarm Armed — {{ 'Away' if trigger.to_state.state == 'armed_away' else 'Night' }}"
              data:
                tag: home_alarm

      - alias: "Disarmed — stop siren and replace alarm notification with confirmation"
        conditions:
          - condition: trigger
            id: disarmed
        sequence:
          - alias: "Stop camera siren"
            action: siren.turn_off
            target:
              entity_id: siren.kitchen_camera_siren

          - alias: "Send disarmed confirmation to iPhone"
            action: notify.mobile_app_nates_iphone
            data:
              title: "Colony Drive"
              message: "✅ Alarm Disarmed"
              data:
                tag: home_alarm
```

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: Alarm Perimeter Trigger | `automation.household_alarm_perimeter_trigger` | `automation` |
| Household: Alarm State Notifications | `automation.household_alarm_state_notifications` | `automation` |
| Alarm Trigger Description | `input_text.alarm_trigger_description` | `input_text` |
| Home Alarm | `alarm_control_panel.home_alarm` | `alarm_control_panel` |
| Camera Fluent | `camera.kitchen_camera_fluent` | `camera` |
| Camera Siren | `siren.kitchen_camera_siren` | `siren` |
| Camera Person | `binary_sensor.kitchen_camera_person` | `binary_sensor` |
| Exterior Door/Window Open | `binary_sensor.exterior_door_window_open` | `binary_sensor` (group) |

---

## Security Summary

| Control | Detail |
|---|---|
| Siren activation | Gated on `trigger.from_state.state == 'armed_away'`; never activates when someone is home |
| Siren auto-stop | `duration: 60` — stops automatically after 60 seconds regardless of alarm state |
| Siren defensive stop | `siren.turn_off` called on disarm and at the end of the push loop as defense-in-depth |
| Snapshot storage | Written to `/config/www/snapshots/` on the local HA host; served via `/local/` (HA-authenticated) |
| Notification images | `image: /local/snapshots/alarm_latest.jpg` — fetched by the iOS Companion app over the authenticated HA connection; no external URLs |
| Alarm code | Stored in `secrets.yaml` as `alarm_code` (migrated from `configuration.yaml` plaintext, May 2026) |

---

## Troubleshooting

**Camera snapshot not appearing in notifications.**
Check two things: (1) `/config/www/snapshots/` exists on the HA host — the snapshot step fails silently if the directory is missing. Create it via Terminal & SSH: `mkdir -p /config/www/snapshots`. (2) The Reolink kitchen camera was not in privacy mode at the moment of detection. Privacy mode disables the sensor and the camera simultaneously, so person detection cannot fire while privacy mode is on — but if the camera was toggled mid-session, confirm the camera entity is not `unavailable`.

**Siren did not activate.**
Confirm the alarm was in `armed_away` state (not `armed_night`) before it was triggered. The siren is intentionally suppressed when anyone is home. Check `trigger.from_state.state` in the automation trace — it should read `armed_away` for the siren to engage.

**"Person Detected" follow-up notification fires on every alarm trigger.**
If the original trigger was person detection itself, the deduplication condition (`'Person Detected' not in states('input_text.alarm_trigger_description')`) should suppress the follow-up. If it is firing anyway, check that `input_text.alarm_trigger_description` was written before the alarm panel transitioned — inspect the perimeter trigger automation trace to confirm the `input_text.set_value` step ran and the value is correct.
