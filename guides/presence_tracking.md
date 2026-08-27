# Presence Tracking

*Last updated: August 2026 (Confirmed Arrival added)*

## Overview

Household presence is derived from HomeKit's geofence detection, which updates significantly faster than the HA Companion app (~10–30 seconds vs. 2–5 minutes). A HomeKit automation toggles an `input_boolean.<name>_home` helper on arrive/depart; a Template Helper `device_tracker` reads that boolean and reports `home`/`not_home`; the tracker feeds a `person` entity, which is what `zone.home`'s occupant count and every presence-based automation actually consult.

This replaces an earlier MQTT-backed design (`presence/<name>` retained-message topics, MQTT auto-discovery, a startup recovery automation) that required running a Mosquitto broker. That design existed to solve state persistence across HA restarts. It turned out to solve a problem that doesn't exist: `input_boolean` already implements `RestoreEntity` and restores its last state on every HA restart with no configuration required. A Template Helper `device_tracker` re-evaluates its template from current entity states the moment it loads, so on restart it reads the already-restored `input_boolean` value directly — no retained messages, no recovery automation, no broker. This was verified empirically (see [Troubleshooting](#troubleshooting)) before decommissioning the MQTT design, including a full HA restart with `guest_mode` left `on` to confirm both trackers and the guest `person` entity survive correctly.

## Architecture

```
HomeKit geofence
       │
       ▼
input_boolean.<name>_home        (on = home, off = not_home)
       │                          restored automatically across HA restarts (RestoreEntity)
       ▼
device_tracker.homekit_<name>    (Template Helper, in_zones template — no automation needed)
       │
       ▼
person.<name>
       │
       ▼
zone.home occupant count
```

```
input_boolean.guest_mode
       │
       ▼
device_tracker.guest_tracker     (Template Helper, in_zones template)
       │
       ▼
person.guest                     (created with no linked HA user — tracking-only)
       │
       ▼
zone.home occupant count
```

**Key design decisions:**

- **Template Helper, not YAML `template:` platform.** Both produce the same `device_tracker` entity, but the Helper (config-entry flow, created via `ha_config_set_helper`) is hot-reloadable and fully MCP/UI-manageable, while the YAML platform requires editing `configuration.yaml` on the HA host and a full HA restart to pick up a new `template:` top-level key. There's no functional reason to prefer YAML here — this repo's HA best-practices skill flags the Helper as the correct approach for exactly this reason.
- **`in_zones` must contain the zone's full `entity_id` (`zone.home`), not the bare slug (`home`).** This is not proofread by config validation — a bare slug silently evaluates to an empty `in_zones` list forever, with no error anywhere. See [Troubleshooting](#troubleshooting).
- **`person.guest` has no linked HA user.** HA persons don't require a user account — a tracking-only person is exactly the mechanism for a guest. This matters because `zone.home`'s occupant count is driven by `person` entities only, not by `device_tracker` entities directly. A `device_tracker.guest_tracker` with no `person` wrapping it would never show up in `zone.home`'s count, however correct its own `home`/`not_home` state was — the earlier MQTT design's guest path had exactly this gap (a `device_tracker.guest_tracker` existed, but no `person.guest` ever wrapped it).

## Prerequisites

- HomeKit hub (Apple TV or HomePod) on the network for geofence automation support
- Home app or Shortcuts automation that toggles the relevant `input_boolean` helper on arrive/depart
- The `input_boolean` must be exposed to Apple Home so the Home app can toggle it, via Matter Hub (RiDDiX fork) — the standard bridge for this house per `LESSONS.md`. **Not yet installed in the new house as of this writing.** Confirm it's running before relying on the HomeKit automation half of this design; the `device_tracker` → `person` → `zone` chain documented here works independently of how the `input_boolean` gets toggled.

## Adding a New Household Member's Tracker

### Step 1: Create the input_boolean

- **Entity ID:** `input_boolean.<name>_home` — e.g., `input_boolean.alex_home`
- **Name:** `<Name> Home` — e.g., `Alex Home`

Omit `initial` — setting it disables restore-on-restart, which is the behavior this whole design depends on.

### Step 2: Expose the helper to Apple Home

In the Matter Hub add-on, add `input_boolean.<name>_home` to the list of exposed entities. It must appear as a switch in the Home app before Step 3 can target it. See [Prerequisites](#prerequisites) — Matter Hub is not yet installed in the new house.

### Step 3: Create the HomeKit automation

In the Apple Home app (or Shortcuts), create two automations:

- **When you arrive home** → set `<Name> Home` switch to On
- **When you leave home** → set `<Name> Home` switch to Off

A home hub (HomePod or Apple TV) must be online for geofence automations to fire.

### Step 4: Create the Template Helper device_tracker

Via `ha_config_set_helper` (`helper_type: template`), submit the menu step first, then the device_tracker fields:

```
# Step A — select sub-type
action: create
helper_type: template
name: "HomeKit Alex"
config: { next_step_id: "device_tracker" }

# Step B — configure the tracker (use the entry_id returned by Step A)
action: update
helper_type: template
helper_id: <entry_id from Step A>
config:
  in_zones: >-
    {{ ['zone.home'] if is_state('input_boolean.alex_home', 'on') else [] }}
```

This produces `device_tracker.homekit_alex`. The entity ID is slugified from the `name` given in Step A — the options-flow update in Step B cannot rename it (a `name` key there is silently ignored). If the resulting slug isn't what you want, rename via `ha_set_entity(new_entity_id=...)`.

### Step 5: Add the tracker to the Person entity

Update the `person` entity's `device_trackers` list to include `device_tracker.homekit_alex`, alongside any existing Companion App trackers. `ha_config_set_helper(helper_type="person", action="update", ...)` replaces the whole `device_trackers` list, so include the existing entries.

If the person entity doesn't exist yet, create it with `action: create`.

### Step 6: Extend the arrival fast path (optional)

The new person is automatically covered by [Confirmed Arrival](#confirmed-arrival)'s evidence path
as soon as `zone.home`'s occupant count includes them — no config change needed, just a later
confirmation (on the next door/lock event) instead of an immediate one. If the person also uses
the HA Companion App, `sensor.<name>_iphone_activity` will exist and can be added to
`automation.household_confirm_arrival`'s `geofence_arrival` branch as an additional
`condition: state … Automotive` (combined with `or`) to give them the same immediate confirmation
on a drive-home. This is an optimization, not a requirement.

## Guest Tracking

`input_boolean.guest_mode` (already exists) → `device_tracker.guest_tracker` (Template Helper, same `in_zones` pattern) → `person.guest` (created with **no** `user_id` — tracking-only, unlinked to any HA user account).

Whatever toggles `guest_mode` on/off is outside the scope of this guide — the chain downstream of that boolean is what matters here. Follow Steps 4–5 above using `guest_mode` as the source boolean and skipping the person-creation Companion-App-tracker merge (a guest has no Companion App trackers to preserve).

## Confirmed Arrival

`zone.home` answers "is a tracked person's phone within the geofence radius" (~100m on this
instance), which is a different question from "is someone actually inside the house." A walk or
bike ride around the block re-enters the geofence and, for that instant, looks identical to a
genuine drive home. On 2026-08-27 this cut a daytime vacuum run short: the geofence re-entered
mid-walk, docking the robot 26 minutes into the job — 12 minutes before anyone actually reached a
door.

`input_boolean.arrival_confirmed` closes that gap. Automations that act on a first arrival —
docking the vacuum, setting the thermostat preset — trigger on this helper going `on`, not on
`zone.home` directly.

```
  zone.home rises above 0 ──── AND activity = Automotive ───┐   (fast path: real drive-home)
                                                            │
  lock.entrance_front_door → unlocked ───────────┐          │
  binary_sensor.garage_interior_door opened ─────┤          │   (evidence path — CONFIRMS only,
  binary_sensor.kitchen_patio_door opened ───────┼── AND ───┤    never originates: requires a
  cover.garage_door_opener_door → open ──────────┘ zone.home│    tracked person already home)
                                                     > 0    │
                                                            ▼
                                Household: Confirm Arrival (automation)
                                          │
                          input_boolean.arrival_confirmed → on
                                          │
  zone.home → 0 ────────────────────────────────────────────┴──► off
                                          │
              ┌────────────────────────────┼──────────────────────┐
              ▼                            ▼                      ▼
  Vacuum Stops For Occupants   First Arrives Home        (future arrival actions)
        (dock the robot)      (thermostat → Home)
```

**Why two paths.** The fast path buys a couple of minutes on a genuine drive-home, docking the
vacuum before anyone walks in. The evidence path is the correctness backstop and needs no
per-person activity sensor — anything that isn't clearly a car (walking, cycling, running,
stationary, or the sensor's idle `Unknown`) defers to it rather than being enumerated, since
evidence always eventually arrives.

**Why the evidence path requires `zone.home > 0`.** A door or lock event proves entry occurred, not
that it was authorized — `binary_sensor.kitchen_patio_door` in particular carries no authorization
story at all. Gating on a tracked person already being in `zone.home` means evidence can only ever
*confirm* an arrival the geofence already suspects, never *originate* one from an unattended door.

> **`arrival_confirmed` is not an authorization signal.** See `standards/automations.md` §5.12 for
> the full statement of this boundary. It must never gate alarm disarm, lock release, or any other
> security decision — only convenience actions (climate, vacuum, lighting).

**Exception: automations whose action *is* the entry.** `automation.household_nate_presence` opens
the garage door on arrival, so it cannot wait on entry evidence without being circular — it reads
`sensor.nates_iphone_activity` directly instead, gated on `Automotive`, `Unknown`, or
`unavailable`. That automation's cost matrix is inverted from the vacuum's: a spurious garage open
is cheap, so it can afford the looser gate that `Confirm Arrival`'s fast path deliberately avoids.

See [Adding a New Household Member's Tracker](#adding-a-new-household-member's-tracker), Step 6,
for how a new person is picked up by this design.

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| HomeKit Nate | `device_tracker.homekit_nate` | Template Helper (device_tracker) |
| Guest Tracker | `device_tracker.guest_tracker` | Template Helper (device_tracker) |
| Nate | `person.nate` | Person |
| Guest | `person.guest` | Person (no linked user — tracking-only) |
| Nate Home | `input_boolean.nate_home` | Helper |
| Guest Mode | `input_boolean.guest_mode` | Helper |
| Household: Confirm Arrival | `automation.household_confirm_arrival` | Automation |
| Arrival Confirmed | `input_boolean.arrival_confirmed` | Helper |

## Related Documents

- `LESSONS.md` — `in_zones` entity-ID gotcha
- `standards/automations.md` §5.10, §5.12 — arrival-evidence pattern and its generalization into
  `arrival_confirmed`

## Troubleshooting

**`in_zones` template evaluates correctly in isolation but the tracker never shows `home`**

Check the exact value being returned. `in_zones` requires full zone `entity_id`s (`zone.home`), not bare slugs (`home`). A bare slug doesn't error anywhere — not at config validation, not in logs, not in `ha_eval_template`, which will happily render `['home']` since it doesn't know the zone-matching semantics. It only shows up as `in_zones: []` and `state: not_home` on the entity itself, no matter what the source `input_boolean` says. This was the actual root cause behind what initially looked like a startup race condition during this design's validation — the tracker failed to reflect its `input_boolean` both immediately after a reload and after a full restart, which pointed at a timing bug until the zone identifier format was corrected, after which both live toggles and cold-boot restores worked immediately.

**New `device_tracker` doesn't get the entity ID you expect**

The Template Helper's config-flow update step doesn't support renaming (a `name` key passed there is silently ignored with a warning, not an error). The entity ID is fixed from whatever `name` was given at the initial menu-selection (`create`) step. Fix with `ha_set_entity(new_entity_id=...)` after creation.

**`zone.home`'s count doesn't reflect a tracker you know is `home`**

Zone occupant counts are computed from `person` entities only (the zone's `persons` attribute is authoritative), not from raw `device_tracker` entities. A `device_tracker` not wrapped by a `person` entity is invisible to zone counting regardless of its own state.
