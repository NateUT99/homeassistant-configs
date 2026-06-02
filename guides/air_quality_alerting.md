# Air Quality Alerting

*Last updated: June 2026*

## Overview

Monitors outdoor air quality via the WAQI (World Air Quality Index) integration and notifies occupants to close windows when the AQI rises above a configured threshold. A companion automation clears the notification automatically when the AQI drops back below threshold or all exterior windows are closed. TTS announcements play on HomePods in the kitchen and office at the time of alert.

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
 window_alert                 alert_clear
   ├─ iOS push notification     └─ clear iOS notification (tag)
   └─ TTS: kitchen + office
            HomePods
```

The threshold helper (`binary_sensor.home_air_quality_index_high`) is the single source of truth for whether air quality is currently actionable. It goes `on` when AQI exceeds 125 and does not go `off` until AQI drops to 120 (5-point hysteresis), preventing notification churn if the sensor hovers near the boundary.

The alert automation has three entry-path triggers to cover all situations where conditions first become fully met:

- **AQI crosses above threshold** — primary trigger
- **First person arrives home** — AQI was already bad while no one was home
- **A window is opened** — someone opened a window while AQI was already bad

In all three cases, conditions (threshold on, windows open, someone home, not sleeping) are evaluated before acting. The clear automation fires unconditionally on its triggers — clearing a non-existent notification is a harmless no-op.

> **Coordinated change:** The threshold value (125) and hysteresis (5) are set on `binary_sensor.home_air_quality_index_high`. If you want to change the alert threshold, update the threshold helper configuration — do not add numeric conditions to the automations.

---

## Prerequisites

- WAQI integration configured with a nearby monitoring station (**Settings → Devices & Services → WAQI**)
- `binary_sensor.exterior_window_open` — a binary sensor group that is `on` when any exterior window is open
- `input_boolean.everyone_sleeping` — sleep state helper used to suppress alerts overnight
- HA Companion App installed on `notify.mobile_app_nates_iphone`
- Nabu Casa subscription active (cloud TTS via `tts.home_assistant_cloud`)

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
alias: Air Quality Window Alert
description: >-
  Notifies to close windows when outdoor AQI exceeds 125 with at least one
  exterior window open, someone home, and everyone not sleeping. Fires on AQI
  crossing above threshold, first person arrival, or a window opened under
  already-bad AQI. Notification is cleared by Air Quality Alert Clear.
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
    entity_id: binary_sensor.exterior_window_open
    to: "on"
    alias: Exterior window opened
    id: window_opened
conditions:
  - condition: state
    entity_id: binary_sensor.home_air_quality_index_high
    state: "on"
    alias: AQI above threshold
  - condition: state
    entity_id: binary_sensor.exterior_window_open
    state: "on"
    alias: Exterior windows are open
  - condition: numeric_state
    entity_id: zone.home
    above: 0
    alias: Someone is home
  - condition: state
    entity_id: input_boolean.everyone_sleeping
    state: "off"
    alias: Not everyone sleeping
actions:
  - alias: Send close-windows air quality notification
    action: notify.mobile_app_nates_iphone
    data:
      title: "Close the Windows — Poor Air Quality"
      message: >-
        Outdoor AQI is {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
        Close the windows to keep indoor air clean.
      data:
        tag: air_quality_window_alert
  - alias: Announce on kitchen and office HomePods
    action: media_player.play_media
    target:
      entity_id:
        - media_player.kitchen_homepod
        - media_player.office_homepod
    data:
      announce: true
      extra:
        volume: 65
      media:
        media_content_id: >-
          media-source://tts/cloud?message=Heads up — outdoor air quality index is
          {{ states('sensor.toledo_ohio_usa_air_quality_index') }}.
          Consider closing the windows.
        media_content_type: music
mode: single
```

Assign to the **Climate** category with labels `notification` and `scope_whole_home`, area **Outside**.

### 4. Create the Clear Automation

```yaml
alias: Air Quality Alert Clear
description: >-
  Clears the air quality close-windows notification when AQI drops back below
  threshold or all exterior windows are closed. Companion to Air Quality Window Alert.
triggers:
  - trigger: state
    entity_id: binary_sensor.home_air_quality_index_high
    to: "off"
    alias: AQI drops below threshold
  - trigger: state
    entity_id: binary_sensor.exterior_window_open
    to: "off"
    alias: All exterior windows closed
actions:
  - alias: Clear air quality window alert notification
    action: notify.mobile_app_nates_iphone
    data:
      message: clear_notification
      data:
        tag: air_quality_window_alert
mode: single
```

Assign to the **Climate** category with labels `notification` and `scope_whole_home`, area **Outside**.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Toledo, Ohio, USA Air Quality Index | `sensor.toledo_ohio_usa_air_quality_index` | Sensor (WAQI integration) |
| Home Air Quality Index High | `binary_sensor.home_air_quality_index_high` | Threshold helper |
| Air Quality Window Alert | `automation.air_quality_window_alert` | Automation |
| Air Quality Alert Clear | `automation.air_quality_alert_clear` | Automation |

---

## Troubleshooting

### TTS action fails with an unknown error

`tts.speak` targeting HomePods via the Apple TV integration fails with `miniaudio.DecodeError: ('failed to init decoder', -1)`. The Apple TV integration's RAOP streaming layer passes the Nabu Casa audio URL through miniaudio, which cannot decode the format Nabu Casa generates. Use `media_player.play_media` with `announce: true` and the `media-source://tts/cloud?message=...` URI instead — this routes through HA's announce pipeline and bypasses pyatv entirely. See `LESSONS.md` for the full pattern.

### Threshold helper entity ID contains the station name

HA derives the threshold helper entity ID from the source sensor's name, not the helper's display name. After creation, manually rename the entity ID via **Settings → Devices & Services → Helpers → ⋮ → Settings → Entity ID** and update any automations that reference it.
