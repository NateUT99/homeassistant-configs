# Outdoor Air Quality Alerting

*Last updated: June 2026*

## Overview

Monitors outdoor air quality via the WAQI (World Air Quality Index) integration and notifies occupants to close exterior doors and windows when the AQI rises above a configured threshold. A companion automation clears the notification automatically when the AQI drops back below threshold or all exterior doors and windows are closed.

Delivery varies by situation:

- **AQI spikes while awake, door/window open** — TTS on kitchen HomePod
- **First person arrives home, door/window open** — waits for interior garage door to close, then TTS on kitchen HomePod
- **Everyone wakes up while AQI is bad** — TTS on master bedroom HomePod (no door/window requirement — warns before anything is opened)
- **AQI spikes while sleeping** — iOS push notification
- **AQI clears while awake and outdoor feels cooler than indoor** — TTS on kitchen HomePod suggesting windows can be opened

---

## Architecture

```
WAQI API ──► sensor.toledo_ohio_usa_air_quality_index
                          │
                          ▼
           binary_sensor.outdoor_air_quality_index_high
           (threshold helper: upper 125, hysteresis 5)
                          │
              ┌───────────┴────────────┐
           on │                        │ off
              ▼                        ▼
 automation.outdoor_air_           automation.outdoor_air_
 quality_index_alert               quality_index_alert_clear
   ├─ sleeping + AQI high → push     ├─ aqi_clears + awake + cooler outside
   ├─ sleeping_ends + AQI high       │    → TTS (kitchen HomePod)
   │    → TTS (master bedroom)       └─ always → clear iOS notification (tag)
   ├─ aqi_spike + door open
   │    → TTS (kitchen HomePod)
   └─ person_arrives + door open
        → garage wait → TTS (kitchen)
```

The threshold helper (`binary_sensor.outdoor_air_quality_index_high`) is the single source of truth for whether air quality is currently actionable. It goes `on` when AQI exceeds 125 and does not go `off` until AQI drops to 120 (5-point hysteresis), preventing notification churn if the sensor hovers near the boundary.

The alert automation has three entry-path triggers:

- **AQI crosses above threshold** (`aqi_spike`) — primary trigger; requires a door or window to be open to announce
- **First person arrives home** (`person_arrives`) — covers the case where AQI was already bad while no one was home; requires a door or window open; waits for the interior garage door to close before announcing so the person is actually inside
- **Everyone wakes up** (`sleeping_ends`) — `input_boolean.everyone_sleeping` transitions off; announces on the master bedroom HomePod regardless of door/window state so occupants are warned before opening anything

The sole root condition is someone home — AQI is checked per-branch rather than at the root so the `sleeping_ends` path can announce even if AQI changes while the automation is evaluating. The door/window open requirement is enforced per-branch so the `sleeping_ends` path can bypass it.

When a door or window is opened while AQI is already bad, `automation.household_thermostat_exterior_open_pause` owns that notification moment — it fires at the 3-minute mark and includes a conditional AQI mention in its TTS and push notification. This avoids duplicate alerts from two automations firing simultaneously.

The action block uses a `choose` with native `condition: trigger` branches:

1. AQI high + everyone sleeping → push notification (any trigger)
2. AQI high + `sleeping_ends` → immediate TTS on master bedroom HomePod
3. AQI high + `person_arrives` + door/window open → wait for garage interior door `open → closed` (5-min timeout) → 15-second buffer → TTS on kitchen HomePod
4. AQI high + `aqi_spike` + door/window open → immediate TTS on kitchen HomePod

The clear automation fires on two triggers. The push dismiss is unconditional — clearing a non-existent notification is a harmless no-op. The TTS fires only when the `aqi_clears` trigger (not the door-close trigger) fires, someone is home, everyone is awake, and outdoor feels-like temperature is lower than indoor.

> **Coordinated change:** The threshold value (125) and hysteresis (5) are set on `binary_sensor.outdoor_air_quality_index_high`. If you want to change the alert threshold, update the threshold helper configuration — do not add numeric conditions to the automations.

> **Coordinated change:** The 3-minute door/window-open alert path lives in `automation.household_thermostat_exterior_open_pause`, not here. If you modify the door-open notification behavior (timing, message, sleep gating), update that automation — not this one.

---

## Prerequisites

- WAQI integration configured with a nearby monitoring station (**Settings → Devices & Services → WAQI**)
- `binary_sensor.exterior_door_window_open` — a binary sensor group that is `on` when any exterior door or window is open
- `binary_sensor.garage_interior_door_contact` — contact sensor on the door between garage and home interior
- `input_boolean.everyone_sleeping` — sleep state helper used to branch between TTS and push notification
- HA Companion App installed on `notify.mobile_app_nates_iphone`
- Chime TTS active with `notify.reminder_kitchen` and `notify.reminder_master_bedroom` configured (see `guides/chime_tts.md`)
- `script.household_tts_announce` available (created as part of Chime TTS setup)
- `sensor.outside_feels_like_temperature` — outdoor feels-like temperature used to gate the AQI-cleared announcement
- `sensor.apartment_temperature` — indoor temperature reference for the same comparison

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

After creation, rename the entity ID to `binary_sensor.outdoor_air_quality_index_high` via **Settings → Devices & Services → Helpers → Outdoor Air Quality Index High → ⋮ → Settings → Entity ID**. The auto-generated ID will include the station name and should be overridden.

> **Threshold rationale:** AQI 0–100 is broadly safe for the general public. The 101–150 range ("Unhealthy for Sensitive Groups") is not likely to affect most people. 125 is chosen as a meaningful midpoint — high enough to avoid alert fatigue during marginal days, low enough to catch conditions genuinely heading toward the 151+ "Unhealthy" range.

### 3. Create the Alert Automation

Create Outdoor Air Quality Index Alert (`automation.outdoor_air_quality_index_alert`), `mode: single`.

**Triggers** — use these trigger IDs exactly; the action block branches on them:

| ID | Platform | Entity | Config |
|---|---|---|---|
| `aqi_spike` | state | `binary_sensor.outdoor_air_quality_index_high` | to: on |
| `person_arrives` | numeric_state | `zone.home` | above: 0 |
| `sleeping_ends` | state | `input_boolean.everyone_sleeping` | from: on → to: off |

**Root condition:** `zone.home` numeric_state above 0 (someone is home). AQI state is checked per-branch rather than at the root so the `sleeping_ends` path can announce even if the threshold sensor changes while the automation is evaluating.

**Action:** `choose` block with four branches as described in the Architecture section above.

Assign to the **Climate** category with labels **Notification**, **Text to Speech**, **Whole Home**, and **WAQI**, area **Outside**.

### 4. Create the Clear Automation

Create Outdoor Air Quality Index Alert Clear (`automation.outdoor_air_quality_index_alert_clear`), `mode: single`.

**Triggers:**

| ID | Platform | Entity | Config |
|---|---|---|---|
| `aqi_clears` | state | `binary_sensor.outdoor_air_quality_index_high` | to: off |
| *(no id)* | state | `binary_sensor.exterior_door_window_open` | to: off |

**Action:** `choose` block with one branch for the `aqi_clears` trigger (gated on someone home, everyone awake, and outdoor feels-like below indoor temperature) → `script.household_tts_announce` (target: kitchen). Unconditional second action clears the push notification tag regardless of trigger (a clear on a non-existent notification is a no-op).

Assign to the **Climate** category with labels **Notification**, **Text to Speech**, **Whole Home**, and **WAQI**, area **Outside**.

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Toledo, Ohio, USA Air Quality Index | `sensor.toledo_ohio_usa_air_quality_index` | Sensor (WAQI integration) |
| Outdoor Air Quality Index High | `binary_sensor.outdoor_air_quality_index_high` | Threshold helper |
| Outdoor Air Quality Index Alert | `automation.outdoor_air_quality_index_alert` | Automation |
| Outdoor Air Quality Index Alert Clear | `automation.outdoor_air_quality_index_alert_clear` | Automation |

---

## Troubleshooting

### TTS announcements use Chime TTS, not tts.speak or media_player.play_media

`tts.speak` targeting HomePods fails with `miniaudio.DecodeError` (pyatv decode issue). `media_player.play_media` with `announce: true` works but delivers a bare spoken message without a chime. The correct pattern for this instance is `script.household_tts_announce` — this routes to the appropriate Chime TTS service, prepends a soft chime before speaking, and handles the video call suppression check. See `guides/chime_tts.md` for the script's fields and `LESSONS.md` for background on the pyatv failure.

---

## Related Documents

- `guides/chime_tts.md` — setup and configuration for the `notify.reminder_*` TTS services used by both automations

---

## Troubleshooting (continued)

### Threshold helper entity ID contains the station name

HA derives the threshold helper entity ID from the source sensor's name, not the helper's display name. After creation, manually rename the entity ID via **Settings → Devices & Services → Helpers → ⋮ → Settings → Entity ID** and update any automations that reference it.
