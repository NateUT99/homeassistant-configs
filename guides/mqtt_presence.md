# MQTT Presence Tracking

*Last updated: May 2026*

## Overview

MQTT retained messages serve as the persistence layer for device tracker state. Each tracker publishes `home` or `not_home` to a `presence/<tracker_name>` topic with `retain=true`. When HA restarts, the MQTT broker replays the retained messages and restores tracker state immediately — no startup correction automation needed. Trackers are registered via MQTT auto-discovery so no `known_devices.yaml` file or manual entity configuration is required.

HomeKit's geofence detection updates significantly faster than the HA Companion app (~10–30 seconds vs. 2–5 minutes), so the primary presence source for household members is a HomeKit automation that toggles an `input_boolean.<name>_home` helper. The `household_homekit_presence_sync` automation watches those booleans and publishes to the appropriate MQTT tracker topics.

---

## Architecture

```
HomeKit geofence
       │
       ▼
input_boolean.<name>_home  (on = home, off = not_home)
       │
       ▼
automation.household_homekit_presence_sync
       │  mqtt.publish, retain=true
       ▼
MQTT topic: presence/homekit_<name>
       │
       ▼
device_tracker.homekit_<name>  (created via MQTT auto-discovery)
       │
       ▼
person.<name>
```

The presence sync automation derives the tracker name from the boolean's `object_id` using the template `{{ trigger.to_state.object_id | replace('_home', '') }}`, so `input_boolean.nate_home` automatically maps to topic `presence/homekit_nate`. Adding a new household member requires only adding their boolean to the trigger list — the routing logic is already generic.

The guest tracker follows a different path: `input_boolean.guest_mode` → `automation.household_status_lights_home_mode` → `presence/guest_tracker`. It is not driven by HomeKit geofencing.

---

## Prerequisites

- Mosquitto (or equivalent) MQTT broker installed and connected to HA
- MQTT integration configured with auto-discovery enabled (discovery prefix: `homeassistant`)
- HomeKit hub (Apple TV or HomePod) on the network for geofence automation support
- Home app or Shortcuts automation that toggles the `input_boolean.<name>_home` helper on arrive/depart
- `automation.household_homekit_presence_sync` enabled

---

## Adding a New Household Member's Tracker

Follow these steps in order. Steps 1 and 2 can be completed in either order, but both must be done before Step 5.

### Step 1: Create the input_boolean

In HA, create a new toggle helper:

- **Entity ID:** `input_boolean.<name>_home` — e.g., `input_boolean.alex_home`
- **Name:** `<Name> Home` — e.g., `Alex Home`

### Step 2: Expose the helper to Matter Hub

The `input_boolean` must be bridged to HomeKit via the Matter Hub add-on so the Home app can toggle it.

In the Matter Hub add-on, add the new `input_boolean.<name>_home` entity to the list of exposed entities. The helper will appear as a switch in Apple Home once bridged.

### Step 3: Create the HomeKit automation

In the Apple Home app (or Shortcuts), create two automations for the person:

- **When you arrive home** → set `<Name> Home` switch to On
- **When you leave home** → set `<Name> Home` switch to Off

A home hub (HomePod or Apple TV) must be online for geofence automations to fire. Without a hub, the Home app does not evaluate geofence conditions.

### Step 4: Publish the MQTT discovery config

Publish to `homeassistant/device_tracker/homekit_<name>/config` with `retain=true`:

```json
{
  "name": "HomeKit <Name>",
  "unique_id": "homekit_<name>_presence",
  "state_topic": "presence/homekit_<name>",
  "payload_home": "home",
  "payload_not_home": "not_home"
}
```

Replace `<name>` and `<Name>` with the person's lowercase and title-case name. Example for "Alex":

- Config topic: `homeassistant/device_tracker/homekit_alex/config`
- Payload:

```json
{
  "name": "HomeKit Alex",
  "unique_id": "homekit_alex_presence",
  "state_topic": "presence/homekit_alex",
  "payload_home": "home",
  "payload_not_home": "not_home"
}
```

HA derives the entity ID by slugifying the `name` field — "HomeKit Alex" → `device_tracker.homekit_alex`. Name the tracker carefully to match the desired entity ID.

> **Note:** The `object_id` field in MQTT discovery payloads is not honored for the `device_tracker` platform. Entity IDs are always derived from the slugified `name` field. If the resulting entity ID does not match what you want, rename it via **Settings → Entities** in the HA UI, or with `ha_set_entity(new_entity_id=...)`. Renaming only updates the HA registry entry; the MQTT discovery config does not need to change.

Then publish an initial state to the state topic:

- Topic: `presence/homekit_<name>` — e.g., `presence/homekit_alex`
- Payload: `not_home` (safe default; the HomeKit automation will correct to `home` if the person is currently home)
- Retain: true

Without an initial retained message, the tracker entity starts in `unknown` state until the next geofence event fires.

### Step 5: Add the boolean to the presence sync automation

Add the new boolean to both trigger groups in `automation.household_homekit_presence_sync`. The variable template handles topic routing automatically — no other changes to the automation are needed.

Current trigger configuration with placeholders for the new person:

```yaml
trigger:
  - alias: "Someone arrived home"
    entity_id:
      - input_boolean.nate_home
      - input_boolean.alex_home   # new person
    from: "off"
    to: "on"
    id: arrived
    platform: state

  - alias: "Someone left home"
    entity_id:
      - input_boolean.nate_home
      - input_boolean.alex_home   # new person
    from: "on"
    to: "off"
    id: departed
    platform: state
```

The automation runs in `queued` mode with `max: 4`. This cap is sufficient for up to four household members firing simultaneously; increase `max` if the household grows beyond that.

### Step 6: Add the tracker to the Person entity

In **Settings → People**, edit the person entity for the new household member and add `device_tracker.homekit_<name>` to their tracked devices list. HA merges state from all trackers; the person entity reports `home` if any tracker shows `home`.

If a person entity does not yet exist, create one in **Settings → People → Add Person**.

---

## Existing Trackers

| Friendly Name | Entity ID | State Topic | Driven By |
|---|---|---|---|
| Nate HomeKit | `device_tracker.homekit_nate` | `presence/homekit_nate` | `input_boolean.nate_home` via `automation.household_homekit_presence_sync` |
| Guest | `device_tracker.guest_tracker` | `presence/guest_tracker` | `input_boolean.guest_mode` via `automation.household_status_lights_home_mode` |

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household: HomeKit Presence Sync | `automation.household_homekit_presence_sync` | Automation |
| Nate HomeKit | `device_tracker.homekit_nate` | Device Tracker |
| Guest | `device_tracker.guest_tracker` | Device Tracker |

---

## Troubleshooting

**Tracker state is `unknown` after HA restart**

Check that both the discovery config and the state topic were published with `retain=true`. Without retain, the broker drops messages on restart and HA sees no state. Verify with an MQTT client (e.g., MQTT Explorer) that the retained flag is set on both topics.

**Entity ID created does not match the expected pattern**

HA slugifies the `name` field to produce the entity ID; the `object_id` field is ignored for the `device_tracker` platform. Rename via **Settings → Entities** or `ha_set_entity(new_entity_id=...)`. This updates only the HA entity registry — the MQTT discovery config does not need to change.

If the rename fails with "entity with this ID is already registered," check for disabled or hidden entities with the same ID. Remove those entries, then retry the rename.

**HomeKit automation does not fire**

- Confirm the `input_boolean` is exposed via Matter Hub. The helper must appear as a switch in Apple Home before a Home automation can target it.
- A home hub (HomePod or Apple TV) must be online. Without a hub, geofence automations are evaluated on the device, which requires the device to be in range of the home network — geofence triggers will not fire reliably.
- The presence sync automation suppresses triggers for 5 minutes after HA startup (uptime guard condition). This is intentional — stale boolean state from before a restart does not cause spurious presence events.

**Person entity shows `unknown` or wrong state after adding the tracker**

Person entity tracker lists do not update automatically when trackers are added via MQTT discovery. After adding `device_tracker.homekit_<name>` in **Settings → People**, save the person entity. HA will begin merging the new tracker's state immediately.
