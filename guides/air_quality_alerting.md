# Air Quality Alerting

*Last updated: June 2026*

## Overview

Monitors outdoor air quality via the WAQI (World Air Quality Index) integration and notifies occupants to close exterior doors and windows when the AQI rises above a configured threshold. A companion automation clears the notification automatically when the AQI drops back below threshold or all exterior doors and windows are closed.

Delivery varies by situation:

- **AQI spikes while awake, door/window open** — TTS on kitchen HomePod
- **First person arrives home, door/window open** — waits for interior garage door to close, then TTS on kitchen HomePod
- **Everyone wakes up while AQI is bad** — TTS on master bedroom HomePod (no door/window requirement — warns before anything is opened)
- **AQI spikes while sleeping** — iOS push notification

---

## Architecture

```
WAQI API ──► sensor.toledo_ohio_usa_air_quality_index
                          │
                          ▼
           binary_sensor.home_air_quality_index_high
           (threshold helper: upper 125, hysteresis 5)
                          │
              ┌───────────┴────────────┐
           on │                        │ off
              ▼                        ▼
 automation.air_quality_      automation.air_quality_
 index_alert                  index_alert_clear
   ├─ sleeping → iOS push notification   └─ clear iOS notification (tag)
   ├─ sleeping_ends → TTS (master bedroom HomePod)
   ├─ aqi_spike + door/window open → TTS (kitchen HomePod)
   └─ person_arrives + door/window open → wait for garage door → TTS (kitchen HomePod)
```

The threshold helper (`binary_sensor.home_air_quality_index_high`) is the single source of truth for whether air quality is currently actionable. It goes `on` when AQI exceeds 125 and does not go `off` until AQI drops to 120 (5-point hysteresis), preventing notification churn if the sensor hovers near the boundary.

The alert automation has three entry-path triggers:

- **AQI crosses above threshold** (`aqi_spike`) — primary trigger; requires a door or window to be open to announce
- **First person arrives home** (`person_arrives`) — covers the case where AQI was already bad while no one was home; requires a door or window open; waits for the interior garage door to close before announcing so the person is actually inside
- **Everyone wakes up** (`sleeping_ends`) — `input_boolean.everyone_sleeping` transitions off; announces on the master bedroom HomePod regardless of door/window state so occupants are warned before opening anything

Root conditions apply to all triggers: AQI above threshold and someone home. The door/window open requirement is enforced per-branch (not at root) so the `sleeping_ends` path can bypass it.

When a door or window is opened while AQI is already bad, `automation.household_thermostat_exterior_open_pause` owns that notification moment — it fires at the 3-minute mark and includes a conditional AQI mention in its TTS and push notification. This avoids duplicate alerts from two automations firing simultaneously.

The action block uses a `choose` with native `condition: trigger` branches:

1. Everyone sleeping → push notification (any trigger)
2. `sleeping_ends` → immediate TTS on master bedroom HomePod
3. `person_arrives` + door/window open → wait for garage interior door `open → closed` (5-min timeout) → 15-second buffer → TTS on kitchen HomePod
4. `aqi_spike` + door/window open → immediate TTS on kitchen HomePod

The clear automation fires unconditionally on its triggers — clearing a non-existent notification is a harmless no-op.

> **Coordinated change:** The threshold value (125) and hysteresis (5) are set on `binary_sensor.home_air_quality_index_high`. If you want to change the alert threshold, update the threshold helper configuration — do not add numeric conditions to the automations.

> **Coordinated change:** The 3-minute door/window-open alert path lives in `automation.household_thermostat_exterior_open_pause`, not here. If you modify the door-open notification behavior (timing, message, sleep gating), update that automation — not this one.

---

## Prerequisites

- WAQI integration configured with a nearby monitoring station (**Settings → Devices & Services → WAQI**)
- `binary_sensor.exterior_door_window_open` — a binary sensor group that is `on` when any exterior door or window is open
- `binary_sensor.garage_interior_door_contact` — contact sensor on the door between garage and home interior
- `input_boolean.everyone_sleeping` — sleep state helper used to branch between TTS and push notification
- HA Companion App installed on `notify.mobile_app_nates_iphone`
- Nabu Casa subscription active (cloud TTS via `tts.home_assistant_cloud`)
- `media_player.master_bedroom_homepod` — HomePod in master bedroom for wakeup announcements

---

## Steps

### 1. Configure the WAQI Integration

Add the WAQI integration via **Settings → Devices & Services → Add Integration → WAQI**. Enter a monitoring station name or coordinates near your location. The integration creates a sensor with state equal to the current AQI integer value.

The resulting sensor entity (`sensor.toledo_ohio_usa_air_quality_index`) is named after the nearest station — the entity ID will vary by location.

### 2. Create the Threshold Helper

Navigate to **Settings → Devices & Services → Helpers → Create Helper → Threshold**. Configure:

| Field | Value |
|---|---|
| Entity | `sensor.toledo_ohio_usa_air_quality_index` |
| Upper threshold | `125` |
| Hysteresis | `5` |

After creation, rename the entity ID to `binary_sensor.home_air_quality_index_high` via **Settings → Devices & Services → Helpers → Home Air Quality Index High → ⋮ → Settings → Entity ID**. The auto-generated ID will include the station name and should be overridden.

> **Threshold rationale:** AQI 0–100 is broadly safe for the general public. The 101–150 range ("Unhealthy for Sensitive Groups") is not likely to affect most people. 125 is chosen as a meaningful midpoint — high enough to avoid alert fatigue during marginal days, low enough to catch conditions genuinely heading toward the 151+ "Unhealthy" range.

### 3. Create the Alert Automation

```yaml
alias: Air Quality Index Alert
description: >-
  Notifies when outdoor AQI exceeds 125 with someone home. When awake with a
  door or window open, announces on the kitchen HomePod; for person_arrives,
  waits for the interior garage door to close first. When everyone wakes up,
  announces on the master bedroom HomePod regardless of door/window state.
  When sleeping, sends a push notification instead. Notification is cleared by
  Air Quality Index Alert Clear.
triggers:
  - trigger: state
    entity_id: binary_sensor.home_air_quality_index_high
    to: "on"
    alias: AQI rises above threshold
    id: aqi_spike
  - trigger: numeric_state
    entity_id: zone.home
    above: 0
    alias: First person arrives home
    id: person_arrives
  - trigger: state
    entity_id: input_boolean.everyone_sleeping
    from: "on"
    to: "off"
    alias: Everyone wakes up
    id: sleeping_ends
conditions:
  - condition: state
    entity_id: binary_sensor.home_air_quality_index_high
    state: "on"
    alias: AQI above threshold
  - condition: numeric_state
    entity_id: zone.home
    above: 0
    alias: Someone is home
actions:
  - alias: Branch on sleeping state and trigger
    choose:
      - conditions:
          - condition: state
            entity_id: input_boolean.everyone_sleeping
            state: "on"
            alias: Everyone sleeping
        sequence:
          - alias: Send push notification
            action: notify.mobile_app_nates_iphone
            data:
              title: "Close Doors & Windows — Poor Air Quality"
              message: >-
                Outdoor AQI is {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
                Close exterior doors and windows to keep indoor air clean.
              data:
                tag: air_quality_index_alert
      - conditions:
          - condition: trigger
            id: sleeping_ends
        sequence:
          - alias: Announce on master bedroom HomePod
            action: media_player.play_media
            target:
              entity_id: media_player.master_bedroom_homepod
            data:
              announce: true
              extra:
                volume: 65
              media:
                media_content_id: >-
                  media-source://tts/cloud?message=Heads up — outdoor air quality index is
                  {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
                  Consider keeping doors and windows closed.
                media_content_type: music
      - conditions:
          - condition: trigger
            id: person_arrives
          - condition: state
            entity_id: binary_sensor.exterior_door_window_open
            state: "on"
            alias: Exterior door or window is open
        sequence:
          - alias: Wait for interior garage door to close
            wait_for_trigger:
              - trigger: state
                entity_id: binary_sensor.garage_interior_door_contact
                from: "on"
                to: "off"
            timeout:
              minutes: 5
            continue_on_timeout: true
          - alias: Buffer after entry
            delay:
              seconds: 15
          - alias: Announce on kitchen HomePod
            action: media_player.play_media
            target:
              entity_id: media_player.kitchen_homepod
            data:
              announce: true
              extra:
                volume: 65
              media:
                media_content_id: >-
                  media-source://tts/cloud?message=Heads up — outdoor air quality index is
                  {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
                  Consider closing exterior doors and windows.
                media_content_type: music
      - conditions:
          - condition: trigger
            id: aqi_spike
          - condition: state
            entity_id: binary_sensor.exterior_door_window_open
            state: "on"
            alias: Exterior door or window is open
        sequence:
          - alias: Announce on kitchen HomePod
            action: media_player.play_media
            target:
              entity_id: media_player.kitchen_homepod
            data:
              announce: true
              extra:
                volume: 65
              media:
                media_content_id: >-
                  media-source://tts/cloud?message=Heads up — outdoor air quality index is
                  {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
                  Consider closing exterior doors and windows.
                media_content_type: music
mode: single
```

Assign to the **Climate** category with labels `notification`, `scope_whole_home`, and `int_waqi`, area **Outside**.

### 4. Create the Clear Automation

```yaml
alias: Air Quality Index Alert Clear
description: >-
  Clears the air quality alert notification when AQI drops back below threshold
  or all exterior doors and windows are closed. Companion to Air Quality Index Alert.
triggers:
  - trigger: state
    entity_id: binary_sensor.home_air_quality_index_high
    to: "off"
    alias: AQI drops below threshold
  - trigger: state
    entity_id: binary_sensor.exterior_door_window_open
    to: "off"
    alias: All exterior doors / windows closed
actions:
  - alias: Clear air quality alert notification
    action: notify.mobile_app_nates_iphone
    data:
      message: clear_notification
      data:
        tag: air_quality_index_alert
mode: single
```

Assign to the **Climate** category with labels `notification`, `scope_whole_home`, and `int_waqi`, area **Outside**.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Toledo, Ohio, USA Air Quality Index | `sensor.toledo_ohio_usa_air_quality_index` | Sensor (WAQI integration) |
| Home Air Quality Index High | `binary_sensor.home_air_quality_index_high` | Threshold helper |
| Air Quality Index Alert | `automation.air_quality_index_alert` | Automation |
| Air Quality Index Alert Clear | `automation.air_quality_index_alert_clear` | Automation |

---

## Troubleshooting

### TTS action fails with an unknown error

`tts.speak` targeting HomePods via the Apple TV integration fails with `miniaudio.DecodeError: ('failed to init decoder', -1)`. The Apple TV integration's RAOP streaming layer passes the Nabu Casa audio URL through miniaudio, which cannot decode the format Nabu Casa generates. Use `media_player.play_media` with `announce: true` and the `media-source://tts/cloud?message=...` URI instead — this routes through HA's announce pipeline and bypasses pyatv entirely. See `LESSONS.md` for the full pattern.

### Threshold helper entity ID contains the station name

HA derives the threshold helper entity ID from the source sensor's name, not the helper's display name. After creation, manually rename the entity ID via **Settings → Devices & Services → Helpers → ⋮ → Settings → Entity ID** and update any automations that reference it.
