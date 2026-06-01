# Home Assistant Automation Standard
*Version 1.4 — June 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.4 | June 2026 | Extended integration labels to non-automation entities directly enrolled in a guide-documented integration; defined the enrollment boundary (direct configuration only, not transitive membership) |
| 1.3 | May 2026 | Added `device_tracker` label — applied to any automation that updates device tracker state via `mqtt.publish` to a `presence/*` topic or `device_tracker.see`; enables auditing the presence tracking pipeline across categories |
| 1.2 | May 2026 | Removed Notifications category — category describes domain, not delivery mechanism; safety alerts → Security, recurring reminders → Routines, consumable tracking → Maintenance. Added `notification` label to mark any automation that sends a push or TTS notification |
| 1.1 | May 2026 | Renamed Media category to Entertainment — scope expanded beyond AV to include other entertainment devices (e.g. pinball machines) |
| 1.0 | May 2026 | Initial release — absorbs automation conventions from CLAUDE.md; adds organization taxonomy (categories, labels, area assignment) and naming rules |

---

## 1. Purpose & Scope

This document defines the standard for creating, naming, organizing, and documenting automations in the Home Assistant instance. It governs:

- How automations are categorized and labeled in the HA registry
- How automation entity IDs and friendly names are formed
- What every automation's YAML must contain (description, mode, step aliases)
- YAML conventions for triggers, conditions, actions, and choose blocks

**Out of scope:** Entity naming for devices, sensors, helpers, and scripts — see `standards/naming.md`. Implementation guides for specific integrations live in `guides/`.

---

## 2. Core Principles

- **Purpose-based organization** — automations are grouped by what they *do*, not by what triggers them or which devices they touch
- **Aliases everywhere** — every trigger, condition, action, choose branch, and repeat block gets an alias
- **Mode always explicit** — no automation relies on the default mode
- **Description always present** — every automation documents what it does and when it fires
- **Entity IDs reflect purpose** — the ID describes the outcome, not the trigger or platform
- **Single area or no area** — automations either belong to one area or they don't belong to any; no forced "primary area" for cross-cutting automations

---

## 3. Organization

### 3.1 Categories

Every automation belongs to exactly one category, chosen by primary *purpose* (not trigger type, not device type):

| Category | Definition | Boundary notes |
|---|---|---|
| **Lighting** | Primary outcome is controlling light state, color, or brightness | Includes button-, motion-, remote-, sensor-, and time-triggered lighting. Any automation whose first-order effect the user would describe as "the lights do something." |
| **Climate** | Thermostat, HVAC, fans, and temperature-driven actions | Includes mode changes, fan speed, and smart scheduling tied to temperature or HVAC state |
| **Security** | Alarm panel state machine, armed-state-aware automations, and life-safety sensor alerts | Includes alarm state transitions and hazard alerts (water leak, freezer left open) — the notification is the delivery mechanism, not the category |
| **Person** | Arrivals, departures, and sleep modes — household state derived from what people are doing | Presence and sleep share state and gate each other; they live in one category |
| **Entertainment** | AV equipment, game consoles, pinball machines, and other entertainment devices — including mode toggles for the entertainment experience | Includes Movie Mode toggling since its purpose is the entertainment experience; not limited to audio/video |
| **Routines** | Recurring time-based actions: sunrise/sunset cycles, daily resets, holiday loops, scheduled vacuum runs, reminder notification lifecycle | The defining characteristic is a recurring time trigger; reminder automations belong here because the daily re-send and overdue-clearing logic is time-driven housekeeping |
| **Maintenance** | Housekeeping the user never directly observes | State sync, metadata helpers, startup refreshes, vacuum progress tracking, consumable lifecycle, device-tracker reconciliation, integration housekeeping |

> The category list is the approved registry. Do not create new categories without extending this standard. Treat an ambiguous automation as an invitation to revisit the boundary note for the categories it might belong to.

**Boundary examples for commonly ambiguous cases:**

- Water leak / freezer door alert → **Security** (life-safety sensor alert; notification is the delivery mechanism)
- Alarm state transition (armed → pending, triggered → disarmed) → **Security** (consults or reacts to alarm panel state)
- Recurring reminder notification lifecycle → **Routines** (time-driven daily re-send and overdue-clearing)
- Vacuum consumable lifecycle notifications → **Maintenance** (consumable tracking triggered at dock return)
- Movie Mode toggle automation → **Entertainment** (sets state consumed by entertainment-experience automations)
- Holiday Christmas color cycle → **Routines** (time-driven recurring cycle)
- Litra Glow startup refresh → **Maintenance** (integration housekeeping)

### 3.2 Labels

Labels let automations carry orthogonal metadata that categories can't express. Three label families exist for automation organization, both distinguished from broadcast-target labels by an ID prefix.

> **Broadcast-target labels** (e.g., `noonehome`, `everyone_is_sleeping`) are used in service calls to target groups of devices. They serve a different purpose and are not part of this taxonomy. When a broadcast-target label is needed, its name follows the entity-naming convention, not this one.

#### Notification label

Applied to every automation that sends a push notification or TTS announcement, regardless of its primary category. Use this to filter "all automations that touch the notification system" across Security, Routines, Maintenance, and other categories.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `notification` | Notification | Any automation with a `notify.*` action or a `media_player.play_media` announce action |

#### Device Tracker label — icon `mdi:map-marker-account`

Applied to every automation that updates device tracker state, regardless of its primary category. Use this to find all automations that participate in the presence tracking pipeline — useful when debugging presence issues or auditing what breaks if the tracking architecture changes.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `device_tracker` | Device Tracker | Any automation with an `mqtt.publish` call targeting a `presence/*` topic, or a `device_tracker.see` call |

#### Scope labels — color `blue`

Applied to automations that affect more than one area. Single-area automations use the area assignment field instead; no scope label is applied.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `scope_whole_home` | Whole Home | Affects all or most areas (arrive/leave, sleep modes, AL pre-stage, alarm) |
| `scope_multi_area` | Multi-Area | Affects more than one area but not the whole home (water leak across bathrooms+kitchen+utility; perimeter sensors) |

#### Integration labels — color `purple`

Applied to automations that belong to a documented integration in `guides/`, and to non-automation entities that are directly enrolled in or configured by that integration. These link back to the integration's design document and support audits of "what does removing this integration affect?"

| Label ID | Friendly Name |
|---|---|
| `int_hue_sync` | Hue Sync |
| `int_adaptive_lighting` | Adaptive Lighting |
| `reminders` | Reminders |
| `int_litra_glow` | Litra Glow |

> The `reminders` label predates this taxonomy and is applied to all reminder-system helpers and automations. Its ID does not carry the `int_` prefix — this is an intentional exception, not a bug to fix.

When a new guide is added, a matching `int_<guide_name>` label is created (color: purple) before the guide's automations are created or migrated. HA does not allow specifying a label ID on creation — use a two-step approach: create the label with the desired ID as the name (HA slugifies it into the ID), then update it with the clean friendly name, color, and icon.

An automation may carry zero, one, or more integration labels. A guide-documented automation always carries its guide's label. Non-automation entities that are directly configured by the integration also carry the label — for example, lights enrolled in an Adaptive Lighting instance. Entities only transitively affected (such as individual members of a light group that is itself enrolled) do not.

### 3.3 Area Assignment

- **Single-area automations:** set the area in the entity registry to that area.
- **Multi-area or whole-home automations:** leave area unset; apply the appropriate `scope_*` label instead. Do not force a "primary area" — it hides cross-cutting automations from area-filtered views without conveying useful information.
- **Integration-scoped automations:** use the primary area of the integration if one exists (e.g., Hue Sync → Living Room; Litra Glow → Office). If the integration spans areas, leave area unset and apply `scope_*`.

---

## 4. Naming

Automation naming follows the general rules in `standards/naming.md` (snake_case, Title Case, apostrophes dropped) and adds automation-specific structure.

### 4.1 Entity ID Format

```
automation.<scope_prefix>_<purpose_phrase>
```

The `<scope_prefix>` is one of three forms:

| Scope | Prefix | Examples |
|---|---|---|
| Single area | The `area_id` from the area registry | `automation.kitchen_freezer_door_left_open` |
| Integration-scoped | The integration's short code | `automation.al_pre_stage_standard`, `automation.hue_sync_stop_on_ps5_power_off` |
| Whole-home / no single area | `household` | `automation.household_first_arrives_home`, `automation.household_everyone_sleeping` |

The `<purpose_phrase>` describes *what the automation does*, not what triggers it:

- `kitchen_freezer_door_left_open` — purpose is "notify about an open freezer door," not `kitchen_door_state_changed`
- `living_room_tv_power_handler` — purpose is "handle TV power events," not `living_room_tv_on_off`

**Forbidden prefixes** (these describe triggers or platforms, not purpose):

`tts_`, `luminance_`, `metadata_`, `sensor_`, `state_`, `motion_`, `time_`, `door_`, `button_`, `remote_`

**Forbidden suffixes and patterns:**

`_v2`, `_2`, `_new`, `new_automation`, `new_automation_N`

If the entity_id starts with `new_automation`, renaming it is not optional — it must be corrected before the automation is considered compliant.

### 4.2 Friendly Name Format

```
<Scope>: <Purpose>
```

The Scope is the human-readable form of the entity-ID scope prefix:

| Entity ID scope | Friendly name scope |
|---|---|
| An `area_id` | The area's friendly name (`Kitchen`, `Living Room`, `Master Bedroom`) |
| Integration short code | The integration's proper name (`Adaptive Lighting`, `Hue Sync`, `Litra Glow`) |
| `household` | `Household` |

The separator is a colon followed by a space. Title Case for both halves.

```
Kitchen: Freezer Door Left Open
Living Room: TV Power Handler
Adaptive Lighting: Pre-Stage Standard & Color Only
Household: First Arrives Home
```

The friendly name slugged to snake_case must produce the entity_id (colon → underscore, apostrophes dropped, spaces → underscores). If the slug doesn't match, one of them is wrong.

---

## 5. Automation Content

### 5.1 Description

Every automation has a non-empty `description` field containing:

1. **What it does** — one sentence describing the outcome.
2. **When it fires** — trigger summary in plain English.
3. **Why it exists** — the constraint, edge case, or coordination it solves. Omit only when the first two make the reason obvious.

One-liners are fine for simple automations. Multi-paragraph descriptions are encouraged when the automation has non-obvious invariants, coordination with other automations, or deliberate edge-case handling.

**Formatting:** The description field renders markdown. One-sentence descriptions need no formatting. For multi-paragraph descriptions, use markdown to aid readability: newlines for paragraph breaks, `- ` for lists, `**bold**` for key terms. Avoid headers (`#`) — the description isn't long enough to need navigation, and headers add visual weight without benefit.

### 5.2 Mode

Specify `mode` explicitly on every automation. Do not rely on the HA default (`single`).

```yaml
mode: single     # use when only one concurrent execution is needed
mode: restart    # use for fast-firing triggers where only the latest matters
mode: queued     # use when all executions must run, in order
mode: parallel   # use when executions are independent and concurrent
```

For `queued` and `parallel`, always set `max`. For alert-style automations that run in parallel, set a reasonable upper bound.

### 5.3 Step Aliases

Every trigger, condition, action, `choose` branch, `repeat` block, and parallel arm gets an `alias` field. Aliases are what make the HA trace view readable during debugging.

```yaml
trigger:
  - alias: "Motion detected in office"
    platform: state
    entity_id: binary_sensor.office_motion
    to: "on"
condition:
  - alias: "Only during work hours"
    condition: time
    after: "08:00:00"
    before: "18:00:00"
action:
  - alias: "Turn on key light"
    action: light.turn_on
    target:
      entity_id: light.office_key_light
```

### 5.4 Parallel vs. Sequential Actions

- Use **parallel blocks** for independent actions where ordering doesn't matter and concurrent execution is faster.
- Use **sequential ordering** when actions depend on each other, or when perceptible-impact actions should fire first and background housekeeping should fire last.

### 5.5 Choose Blocks

- Every `choose` branch gets an `alias` describing the condition it handles.
- Include a `default` branch with an alias when the absence of a match is meaningful. Omit `default` when no action is the intended outcome for unmatched conditions.

### 5.6 Guards on Restoration Branches

Automations that restore a prior state (e.g., turning a thermostat back on after a door closes) must verify the current state before restoring. Do not assume that because the automation turned something off, it can blindly turn it back on — the user may have changed it in the interim.

### 5.7 Avoid Unnecessary Guards

Do not wrap actions in `if`/`then` blocks when the action is a no-op if the condition is false. Calling `light.turn_off` on an already-off light, or `switch.turn_on` on an already-on switch, does nothing — the guard adds complexity without value. Only add a condition when the action would cause a problem if the condition is not met.

### 5.8 Templated Entity IDs in Conditions

`condition: state` does not accept templated entity IDs. Use `condition: template` with `states()` instead.

```yaml
# Wrong — fails silently
- condition: state
  entity_id: "light.{{ states('input_text.target_light') }}"
  state: "on"

# Right
- condition: template
  value_template: "{{ is_state('light.' ~ states('input_text.target_light'), 'on') }}"
```

### 5.9 Entity Targeting

- Prefer label-targeted actions when broadcasting to a group of devices (e.g., `label.noonehome`).
- Use `target:` syntax over `data: entity_id:` in service calls — it is the modern form.

---

## 6. Quick Reference

### Naming

| Situation | Entity ID pattern | Friendly name pattern |
|---|---|---|
| Single-area automation | `automation.[area_id]_[purpose]` | `[Area Name]: [Purpose]` |
| Integration-scoped | `automation.[integration_code]_[purpose]` | `[Integration Name]: [Purpose]` |
| Whole-home | `automation.household_[purpose]` | `Household: [Purpose]` |

### Organization

| What you're assigning | Tool | Rule |
|---|---|---|
| Category | HA category registry | One per automation; use the 7 approved categories only |
| Scope label | HA label registry | Only for multi-area or whole-home automations |
| Integration label | HA label registry | For every automation documented in a `guides/` file |
| Area | HA entity registry | Single-area automations only; leave unset for multi-area |

### Required fields

| Field | Required | Notes |
|---|---|---|
| `alias` | Yes, on every step | Triggers, conditions, actions, choose branches, repeat blocks |
| `description` | Yes | What it does, when it fires, why it exists |
| `mode` | Yes | Never omit; always explicit |
