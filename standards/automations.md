# Home Assistant Automation Standard
*Version 1.16 — September 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.16 | September 2026 | Synced the §3.2 integration labels table — added `int_laundry` (Laundry), `int_vacuum_cleaning_routine` (Vacuum), and `int_inovelli_fan_canopy` (Ceiling Fan), which existed in HA but had drifted out of the table. Friendly names for the latter two are deliberately shortened from their guide names |
| 1.15 | August 2026 | Added §5.12 (Confirmed Arrival) — generalizes §5.10's entry-evidence insight into a shared `input_boolean.arrival_confirmed`, set by `automation.household_confirm_arrival`, that any arrival-triggered automation consumes instead of `zone.home` directly |
| 1.14 | August 2026 | Amended §5.4 — added a blast-radius check before parallelizing actions (broad label/area targets or dynamic `for_each` counts warrant more care than a handful of literal-entity calls) |
| 1.13 | August 2026 | Rewrote §5.10 — the door-state gate never engaged because `zone.home` fires at the GPS geofence, before the person reaches the garage door, so the wait was always skipped; replaced with a bounded wait on evidence of entry (garage door closing behind them, or the front door lock releasing). Added §5.11 (semantic triggers and conditions). Amended §5.3 — `note:` is now a recognized, optional field alongside `alias:` for longer explanations. Updated §3.2 `text_to_speech` label description to remove the retired `notify.reminder_*` Chime TTS platform in favor of calling `chime_tts.say` directly from `script.household_tts_announce`. |
| 1.12 | August 2026 | Reverted presence guidance in §3.2 and §5.10 from `sensor.household_people_home` back to `zone.home` — the HA-core startup race condition that motivated the workaround sensor (§3.2, v1.9) was fixed upstream; the new-house rebuild reads `zone.home` directly throughout and the workaround sensor was not recreated |
| 1.11 | August 2026 | Added §5.9 exception: `light.turn_on` actions with color/brightness/effect data must use literal `entity_id`, not `label_id`/`area_id`, to keep the automation editor's GUI picker usable |
| 1.10 | July 2026 | Assigned color `green` to functional taxonomy labels (`notification`, `text_to_speech`, `device_tracker`, `presence`); corrected `int_home_alarm` from `indigo` to `purple` |
| 1.9 | July 2026 | Added `presence` label; updated section 5.10 to reference `sensor.household_people_home` instead of `zone.home` |
| 1.8 | June 2026 | Added section 5.10: arrival-triggered TTS garage entry grace window |
| 1.7 | June 2026 | Updated TTS delivery pattern: automations call `script.household_tts_announce` instead of `notify.reminder_*` directly; updated `text_to_speech` label criterion accordingly; removed deprecated `media_player.play_media` from `notification` label criterion |
| 1.6 | June 2026 | Added `text_to_speech` label for TTS-specific filtering alongside `notification` |
| 1.5 | June 2026 | Added `int_home_alarm` (Home Alarm) and `waqi` (WAQI) to integration labels table |
| 1.4 | June 2026 | Extended integration labels to non-automation entities directly enrolled in a guide-documented integration; defined the enrollment boundary (direct classification only, not transitive membership) |
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

#### Notification label — color `green`

Applied to every automation that sends a push notification or TTS announcement, regardless of its primary category. Use this to filter "all automations that touch the notification system" across Security, Routines, Maintenance, and other categories.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `notification` | Notification | Any automation with a `notify.*` action |

#### Text to Speech label — color `green`

Applied to every automation that delivers a spoken TTS announcement, regardless of its primary category. Carries alongside `notification` — TTS automations should have both labels. Use `text_to_speech` to filter specifically for automations that speak, as distinct from those that only push silent notifications.

TTS announcements in this instance are delivered via `script.household_tts_announce`, which performs a video call check before routing to `chime_tts.say` at the resolved HomePod. Automations should call the script rather than `chime_tts.say` directly — the script is what applies the video call check and the per-room volume table. See `guides/chime_tts.md` for the script's fields and behavior.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `text_to_speech` | Text to Speech | Any automation with a `script.household_tts_announce` action |

#### Device Tracker label — color `green`, icon `mdi:map-marker-account`

Applied to every automation that updates device tracker state, regardless of its primary category. Use this to find all automations that participate in the presence tracking pipeline — useful when debugging presence issues or auditing what breaks if the tracking architecture changes.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `device_tracker` | Device Tracker | Any automation with an `mqtt.publish` call targeting a `presence/*` topic, or a `device_tracker.see` call |

#### Presence label — color `green`, icon `mdi:home-account`

Applied to every automation that gates on or reacts to household presence state — who is home, whether anyone is home, and arrival/departure events. Use this to find all automations that would be affected by changes to the presence sensing architecture.

Presence state is read from `zone.home`. A startup race condition introduced in HA 2024.x — `zone.home` derived its occupant count from `person.in_zones` (populated late after MQTT reconnects) rather than `person.state` (restored immediately from the entity registry) — briefly required a workaround: `sensor.household_people_home`, a template sensor counting `person.state == "home"` directly, used at the old apartment. HA core fixed the underlying bug in a later release, so `zone.home` is safe to read directly again. The new-house rebuild uses `zone.home` throughout; the workaround sensor was not recreated.

| Label ID | Friendly Name | When to apply |
|---|---|---|
| `presence` | Presence | Any automation with a trigger, condition, or action that reads household presence state |

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
| `int_home_alarm` | Home Alarm |
| `int_litra_glow` | Litra Glow |
| `int_laundry` | Laundry |
| `int_vacuum_cleaning_routine` | Vacuum |
| `int_inovelli_fan_canopy` | Ceiling Fan |
| `reminders` | Reminders |
| `waqi` | WAQI |

> The `reminders` label predates this taxonomy and is applied to all reminder-system helpers and automations. Its ID does not carry the `int_` prefix — this is an intentional exception, not a bug to fix.

When a new guide is added, a matching `int_<guide_name>` label is created (color: purple) before the guide's automations are created or migrated. HA does not allow specifying a label ID on creation — use a two-step approach: create the label with the desired ID as the name (HA slugifies it into the ID), then update it with the clean friendly name, color, and icon. The friendly name can be shortened from the guide name when the guide name is unwieldy as a chip label — `int_vacuum_cleaning_routine` displays as "Vacuum", `int_inovelli_fan_canopy` as "Ceiling Fan" — but the label ID always stays `int_<guide_name>` so the link back to the guide is unambiguous.

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

**`alias` vs. `note`:** `alias` is a brief label — a few words summarizing the step. It's what renders in the trace view and the editor's step list, so it must stay scannable; do not extend it into a paragraph. When a step has rationale, threshold justification, an edge case, or a timing caveat worth recording, put it in the optional `note` field instead of stretching the alias. `note` is not required on every step — add it only where there's something non-obvious to explain.

```yaml
trigger:
  - trigger: door.opened
    target:
      entity_id: binary_sensor.utility_room_door
    alias: "Door opened"
    note: >-
      Fires immediately on the door contact. Paired with a sustained
      occupancy trigger elsewhere in this automation because a bare
      door edge misses cycles that finish while the door happens to
      already be open.
```

### 5.4 Parallel vs. Sequential Actions

- Use **parallel blocks** for independent actions where ordering doesn't matter and concurrent execution is faster.
- Use **sequential ordering** when actions depend on each other, or when perceptible-impact actions should fire first and background housekeeping should fire last.
- **Check the blast radius before parallelizing.** A `parallel:` block with a handful of literal-entity or single-label service calls (the common case) has no meaningful impact on HA Green. Be more deliberate before parallelizing a block where a target resolves broadly (a label or area covering dozens of entities) or where the action count is itself dynamic (e.g. `repeat.for_each` nested in `parallel`) — that's where concurrent execution can turn into a real burst of simultaneous service calls and device traffic instead of a handful. When in doubt, note the reasoning (entity/action count considered, no adverse impact expected) in the block's `note` field.

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
- **Exception — `light.turn_on` actions carrying color/brightness/effect data:** use a literal `entity_id` list, not `label_id`/`area_id`. The automation editor's GUI can only render the visual brightness/color picker when it can resolve the target to a fixed set of light entities and inspect their supported color modes; label and area targets can't be resolved at design time, so the editor falls back to YAML-only for that action's `data`. This trades away auto-following label/area membership — a newly labeled or added light must be added to the entity_id list manually — but GUI editability takes priority per the author's preference. See `automation.household_status_lights_mode` for the pattern.

### 5.10 Arrival-Triggered TTS: Entry Grace Window

When an automation fires on `zone.home` crossing above 0 (first person arrives) and its action includes a TTS announcement, wait for evidence the person is actually inside before announcing.

`zone.home` crosses at the GPS geofence — roughly the end of the street, still in the car — not at the front door. A gate that checks whether the garage door is *currently* open at that instant will almost always find it closed (nobody has reached it yet) and skip straight to announcing outside, before anyone can hear it. There is also no reliable way to tell in advance which door someone will use, so the wait has to cover both paths at once rather than pick one based on current state.

Place this block before the main action or repeat block, gated on the arrival trigger ID only — no door-state precondition:

```yaml
- alias: "Wait for arrival to get inside"
  if:
    - condition: trigger
      id: someone_arrived          # match the arrival trigger's id
  then:
    - alias: "Wait for entry via garage or front door"
      note: >-
        Garage path: door opens then closes behind them. Front door
        path: no contact sensor exists on this house, so the lock
        unlocking is the signal instead.
      wait_for_trigger:
        - trigger: state
          entity_id: binary_sensor.garage_interior_door
          from: "on"
          to: "off"
        - trigger: state
          entity_id: lock.entrance_front_door
          to: "unlocked"
      timeout:
        minutes: 10
      continue_on_timeout: true
    - alias: "Buffer after entry"
      delay:
        seconds: 30
```

`continue_on_timeout: true` ensures the automation never hangs if neither trigger fires (e.g., a garage-remote departure with no matching return, or a side-door entry this pattern doesn't cover). Adjust the entity IDs to the house's actual interior garage door and front door lock.

**When to skip this pattern:**
- The automation only sends push notifications, not TTS — push delivers to the phone regardless of physical location.
- There is no `zone.home` arrival trigger — the `condition: trigger` gate already handles multi-trigger automations where only one trigger is an arrival.

### 5.11 Semantic Triggers and Conditions

HA 2026.x provides semantic trigger and condition platforms for common device classes — `door.opened`, `door.is_closed`, `occupancy.detected`, `occupancy.cleared`, and similar — that read more clearly than the equivalent raw `state` form and require less boilerplate (no `to:`/`from:` state-string matching).

**Prefer the semantic form wherever one exists for the entity's device class.** Fall back to raw `state` triggers/conditions only where no semantic equivalent exists — which is most non-binary-sensor domains: `input_select` transitions, `zone.home`, `event` entities, `lock` state, and similar.

```yaml
# Preferred — semantic
- trigger: door.opened
  target:
    entity_id: binary_sensor.utility_room_door
  alias: "Door opened"

# Only when no semantic form exists
- trigger: state
  entity_id: input_select.utility_room_washer_status
  to: alerting
  alias: "Washer status: alerting"
```

Semantic triggers still take `alias` and `note` per §5.3 — the semantic form changes the trigger platform, not the documentation requirements.

### 5.12 Confirmed Arrival

`zone.home` fires at the GPS geofence radius (~100m on this instance) — well before anyone reaches
a door. Walking or cycling around the block re-enters the geofence and looks identical, at that
instant, to a genuine drive home. §5.10 first identified this for arrival TTS and worked around it
inline with a `wait_for_trigger` on entry evidence. This section generalizes that pattern into a
shared signal every arrival-triggered automation should consume.

**Any automation that acts on a first-person arrival triggers on `input_boolean.arrival_confirmed`
going `on`, not on `zone.home` directly** — with one exception: an automation whose action *is* the
means of entry (e.g. opening the garage) cannot wait on entry evidence without being circular, and
should use the activity gate directly instead (see `automation.household_nate_presence`).

`input_boolean.arrival_confirmed` is maintained by `automation.household_confirm_arrival`, which
confirms via two independent paths:

- **Fast path:** `zone.home` rises from 0 while the arriving person's activity sensor reads
  `Automotive`. Covers a genuine drive-home immediately, without waiting for a door.
- **Evidence path:** a door or lock signals entry (front door unlocked, garage interior door or
  patio door opened, garage cover opened) while a tracked person is already inside `zone.home`.

Anything that isn't clearly a car — walking, cycling, running, stationary, or the sensor's idle
`Unknown` state — defers to the evidence path rather than being enumerated. Entry evidence always
eventually arrives, so deferring costs latency, never correctness. Do not extend the fast path's
activity list to `Unknown` or `Unavailable` the way `household_nate_presence` does for opening the
garage — a spurious garage open is cheap, a spurious dock or preset change on a shared arrival
signal is not, and `Unknown` is the sensor's common idle state.

> **`arrival_confirmed` is not an authorization signal.** It answers "is someone physically
> inside," not "is this entry authorized." Its evidence inputs are door and lock sensors, which
> prove entry occurred, not that the person entering is permitted to. It must never gate alarm
> disarm, lock release, credential access, or any other security decision — those keep their own
> authenticated paths. Consumers are limited to convenience actions (climate, vacuum, lighting).

This is also why the evidence path's `numeric_state: zone.home above 0` condition exists and must
not be removed as "redundant" with its own trigger: a door or lock event proves entry occurred, not
that a tracked person triggered it. The condition ensures evidence can only *confirm* an arrival
the geofence already suspects, never *originate* one from an unattended door.

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
| `note` | No | Optional longer explanation on a step; use when there's non-obvious rationale — don't stretch `alias` instead |
| `description` | Yes | What it does, when it fires, why it exists |
| `mode` | Yes | Never omit; always explicit |
