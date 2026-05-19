# Adaptive Lighting
*Last updated: May 2026*

The canonical document for Adaptive Lighting (AL) configuration in this home. Covers the four canonical AL instance profiles, the sleep-mode wiring strategy, and the MQTT-based pre-staging system that prevents bulbs from flashing to their previous state on turn-on.

---

## Overview

Adaptive Lighting adjusts lights' brightness and color temperature through the day based on a configurable sun-position curve. Four canonical AL instances are maintained:

- **Standard** — brightness + color adaptation for main ceiling fixtures (`light.master_bedroom_fan`, `light.living_room_fan`, `light.office_ceiling`).
- **Color Only** — color-only adaptation (adapt_brightness permanently off) for fixtures where brightness is set manually (`light.entrance_ceiling`, `light.kitchen_counter_strip`, `light.bathroom_hallway_ceiling`).
- **Avery Schedule** — brightness + color adaptation on an earlier evening schedule for Avery's room (`light.avery_room_ceiling`).
- **Status Lamps** — flat-brightness color adaptation for indicator and night-navigation lamps (`light.bathroom_night_lamp`, `light.living_room_status_lamp`, `light.office_presence_sensor`). Brightness is pinned at 35%; status colors set by automations persist until the light is turned off.

Five legacy AL instances also exist and are pending decommission — see [Legacy instances](#legacy-instances). They are not part of this guide's configuration model.

MQTT-based pre-staging is deployed for all Standard and Avery Schedule fixtures, and for the Z2M-managed Color Only fixtures (entrance ceiling, bathroom hallway ceiling). Kitchen counter strip is not pre-staged.

---

## Architecture

```
Standard (brightness + color)                Color Only (color only)
│  light.master_bedroom_fan (4 bulbs)        │  light.entrance_ceiling (2 bulbs)
│  light.living_room_fan (3 bulbs)           │  light.kitchen_counter_strip
│  light.office_ceiling (2 bulbs)            │  light.bathroom_hallway_ceiling (2 bulbs)
└── automation.al_pre_stage_standard ────────┘
    (triggers on Standard brightness_pct; covers both groups)

Avery Schedule (brightness + color; earlier evening)
│  light.avery_room_ceiling (2 bulbs)
└── automation.al_pre_stage_avery_schedule

Status Lamps (flat 35% brightness; autoreset off)
   light.bathroom_night_lamp
   light.living_room_status_lamp
   light.office_presence_sensor
```

### Design decisions

#### 1. Hybrid clamping over pure sun-tracking

AL's default behavior tracks the real sun, which means lights stay bright and cool past 9 pm in summer and start warming/dimming by 5 pm in winter. The four clamp settings (`min_sunrise_time`, `max_sunrise_time`, `min_sunset_time`, `max_sunset_time`) bound when AL's "sunrise event" and "sunset event" can occur. Within those bounds, AL still uses real sun position; outside them, AL uses the clamp. The result is meaningful seasonal variation but never outside the user's actual day.

#### 2. tanh brightness mode

AL's `default` brightness mode produces a bell curve peaked at solar noon — peak brightness is hit at noon, not at the user's preferred mid-morning point. `tanh` mode decouples brightness ramp shape from sun elevation. Two settings (`brightness_mode_time_dark`, `brightness_mode_time_light`) define a smooth S-curve centered on the (clamped) sunrise/sunset events, giving explicit control over when the morning ramp completes and when evening wind-down begins.

#### 3. Standard vs Color Only: same curve, different brightness behavior

Standard and Color Only share identical curve settings and schedule clamps. The distinction is behavioral: Standard fixtures are dimmer-capable ceiling lights where AL should own both brightness and color. Color Only fixtures are set to a user-preferred brightness at turn-on; AL should only guide color temperature. The `switch.adaptive_lighting_adapt_brightness_color_only` switch is permanently off.

Both instances read from `switch.adaptive_lighting_standard` in the pre-staging automation — they follow the same household schedule and produce identical curve outputs.

#### 4. Conservative brightness range

Standard range: `min_brightness: 60` to `max_brightness: 95`. The 60% floor is the evening floor *before sleep mode*, not the night floor — sleep mode drops brightness to `sleep_brightness: 2` independently. Tune `min_brightness` toward 40–50 if the wind-down hour feels too active.

#### 5. Sleep mode via automation, not schedule

Sleep mode is not tied to a fixed time. It is triggered explicitly by the "Everyone Sleeping" automation, which calls `switch.turn_on` on each canonical instance's sleep-mode switch entity. This decouples sleep behavior from the AL curve — sleep mode kicks in only when actually going to bed. See [Step 3 — Sleep-mode wiring](#step-3--sleep-mode-wiring) for entity IDs.

#### 6. Explicit commands win over adaptation

`adapt_only_on_bare_turn_on: true` means that when `light.turn_on` is called with brightness or color specified (a scene, voice command, "set to 70%"), AL skips adaptation and marks the light as manually controlled. Only "bare" turn-ons — `light.turn_on` with no brightness or color — are adapted to the curve. Apple Home turn-ons via Matter Hub and Z2M Aqara button triggers send bare turn-ons by default.

#### 7. skip_redundant_commands tradeoff

With `skip_redundant_commands: true`, AL compares the target value against HA's recorded state before sending a command. If already equal, the command is skipped.

**Why enabled:** With ~15 bulbs across five instances running `interval: 90` cycles, redundant commands during flat parts of the curve (midday peak, overnight floor) generate meaningful Zigbee/Hue chatter.

**Tradeoff:** A brief mesh hiccup or Z2M restart can leave HA's recorded state out of step with the bulb's actual state. AL silently skips a command, leaving the bulb at the wrong value until the curve target changes meaningfully. Recovery is automatic — the next sunrise or sunset transition forces fresh commands.

#### 8. MQTT pre-staging for off-state bulbs

AL only sends commands to bulbs that are on. Off bulbs catch up via `intercept: true` when HA processes a `light.turn_on` call, but this has two failure modes:

1. **Z2M command translation.** Z2M may translate the intercepted call into multiple sequential Zigbee commands — causing a brief flash at the bulb's previous on-state before new values land.
2. **Turn-on paths that bypass HA.** Zigbee bindings, physical wall switches, or any other path that doesn't go through `light.turn_on`.

Pre-staging addresses both by publishing the current AL target values directly to each bulb via MQTT while the bulb is off. With `execute_if_off: true` enabled on the bulb, Z2M stores the values without turning it on. When any turn-on event occurs, the bulb powers up at the pre-staged values immediately.

The pre-staging automation triggers on `brightness_pct` attribute changes. Both brightness and color temperature are sent in each publish — brightness is chosen as the trigger because it ramps monotonically.

---

## Prerequisites

| Item | Notes |
|---|---|
| HACS installed | Required to install AL. |
| Bulbs paired to Z2M | Required for MQTT pre-staging. Non-Z2M bulbs (Hue bridge-managed) cannot be pre-staged. |
| Bulbs support `execute_if_off` | All Hue White Ambiance and Essentials bulbs do. Verified by functional test in Step 4. |
| Entity IDs follow the naming standard | Bulb entities follow `light.[area]_[fixture]_bulb_[n]`. |
| Z2M friendly names known per bulb | MQTT topics use Z2M friendly names verbatim, including spaces and case. Verify in Z2M frontend. |

---

## Step 1 — Install Adaptive Lighting via HACS

1. Open **HACS → Integrations**, search for "Adaptive Lighting", download.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**, search for "Adaptive Lighting", add.
4. Name the first instance "Standard" when prompted.
5. Repeat steps 3–4 for each remaining canonical instance: Color Only, Avery Schedule, Status Lamps.

Each instance creates a set of switch entities (master, adapt_brightness, adapt_color, sleep_mode) under the AL domain.

---

## Step 2 — Configure the four canonical AL instances

Each instance is configured at **Settings → Devices & Services → Adaptive Lighting → [Instance Name] → Configure**. All settings below reflect live configuration.

### 2a. Standard

**Lights:** `light.master_bedroom_fan`, `light.living_room_fan`, `light.office_ceiling`

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.adaptive_lighting_standard` | on |
| `switch.adaptive_lighting_adapt_brightness_standard` | on |
| `switch.adaptive_lighting_adapt_color_standard` | on |
| `switch.adaptive_lighting_sleep_mode_standard` | off — controlled by "Everyone Sleeping" automation |

**Settings:**

| Setting | Value | Rationale |
|---|---|---|
| `interval` | `90` | Seconds between adaptation cycles. |
| `transition` | `45` | Seconds per adaptation step. Smooth fades. |
| `initial_transition` | `1` | Near-instant on first turn-on. |
| `min_brightness` | `60` | Evening floor before sleep mode. Tune toward 40–50 if wind-down feels too active. |
| `max_brightness` | `95` | Daytime ceiling. Never run at 100%. |
| `sleep_brightness` | `2` | Sleep mode floor. |
| `min_color_temp` | `2000` | Warmest (K). Hue's standard warmest value. |
| `max_color_temp` | `5500` | Coolest at solar noon. 6500K reads as harsh in residential ceiling fixtures. |
| `sleep_color_temp` | `2000` | Matches `min_color_temp` — bulb sits at its warmest during sleep mode. |
| `sleep_rgb_color` | `[131, 17, 0]` | Deep red used if sleep mode is active and an RGB command is issued. |
| `brightness_mode` | `tanh` | Smooth S-curve; decouples ramp shape from sun elevation. |
| `brightness_mode_time_dark` | `1800` | 30 min pre-ramp tail before/after clamped sunrise/sunset. |
| `brightness_mode_time_light` | `5400` | 90 min ramp to reach max / begin wind-down. |
| `min_sunrise_time` | `06:30` | Earliest the morning ramp can be anchored. Prevents 5 am ramps in summer. |
| `max_sunrise_time` | `07:30` | Latest morning ramp anchor. Ensures ramp is underway by 7 am in winter. |
| `min_sunset_time` | `20:00` | Earliest evening wind-down can begin. |
| `max_sunset_time` | `21:00` | Latest wind-down anchor. Fully warm/dim by ~21:30 year-round. |
| `take_over_control` | `true` | Manual changes pause AL for that light. |
| `take_over_control_mode` | `pause_changed` | Pauses only the changed attribute, not the entire light. |
| `adapt_only_on_bare_turn_on` | `true` | Skip adaptation if `light.turn_on` specifies brightness or color. |
| `detect_non_ha_changes` | `false` | Avoids false-positive manual-control flags from non-HA sources. |
| `autoreset_control_seconds` | `1800` | Manual-control pause clears after 30 min. |
| `skip_redundant_commands` | `true` | Skips commands when target equals recorded state. Reduces Zigbee traffic. See Design Decision §7. |
| `send_split_delay` | `100` | 100 ms delay between brightness and color commands on the same bulb. |
| `prefer_rgb_color` | `false` | Use color temperature, not RGB. |
| `only_once` | `false` | Continuous adaptation throughout the day, not just at turn-on. |
| `separate_turn_on_commands` | `false` | |
| `adapt_delay` | `0` | |

> **Coordinated change:** `min_brightness` (60) and `max_brightness` (95) are mirrored by the Living Room Hue Sync Mode Configurator's restore branch (`guides/hue_sync.md`). If you change them here, update the restore branch YAML and the Configuration Reference table in `hue_sync.md` to match.

### 2b. Color Only

**Lights:** `light.entrance_ceiling`, `light.kitchen_counter_strip`, `light.bathroom_hallway_ceiling`

Color Only has identical configuration to Standard. The distinction is that `switch.adaptive_lighting_adapt_brightness_color_only` is permanently **off** — AL only adjusts color temperature, not brightness, on these fixtures.

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.adaptive_lighting_color_only` | on |
| `switch.adaptive_lighting_adapt_brightness_color_only` | **off** — leave this off |
| `switch.adaptive_lighting_adapt_color_color_only` | on |
| `switch.adaptive_lighting_sleep_mode_color_only` | off — controlled by "Everyone Sleeping" automation |

**Settings:** All settings match Standard. See §2a for the full table.

### 2c. Avery Schedule

**Lights:** `light.avery_room_ceiling`

Avery Schedule shares most settings with Standard but uses an earlier evening schedule (Avery's bedtime is ~20:30) and faster adaptation cycles.

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.adaptive_lighting_avery_schedule` | on |
| `switch.adaptive_lighting_adapt_brightness_avery_schedule` | on |
| `switch.adaptive_lighting_adapt_color_avery_schedule` | on |
| `switch.adaptive_lighting_sleep_mode_avery_schedule` | off — controlled by "Everyone Sleeping" automation |

**Settings (deviations from Standard):**

| Setting | Avery Schedule | Standard | Reason |
|---|---|---|---|
| `interval` | `45` | `90` | Shorter cycles for more responsive adaptation during wind-down. |
| `transition` | `90` | `45` | Slower fades feel more gradual at bedtime. |
| `min_brightness` | `65` | `60` | Slightly higher floor for Avery's room. |
| `min_sunset_time` | `19:30` | `20:00` | Begin warming earlier to match earlier bedtime. |
| `max_sunset_time` | `20:00` | `21:00` | Fully warm/dim by 20:30 reading time. |
| `send_split_delay` | `0` | `100` | Single light; no split delay needed. |

All other settings match Standard. The morning ramp is shared (same wake-up schedule).

### 2d. Status Lamps

**Lights:** `light.bathroom_night_lamp`, `light.living_room_status_lamp`, `light.office_presence_sensor`

Status Lamps is a color-only AL profile for indicator-style and night-navigation lamps. Like Color Only, `adapt_brightness` is off — AL adjusts color temperature only; brightness is set entirely by the calling automations. Brightness by state:

- **Alarm armed away** (`automation.sync_living_room_status_lamp_to_alarm_and_guest_modes`): red at 50%
- **Guest mode** (same automation): green at 50%
- **Everyone sleeping** (same automation): warm white at 35%
- **Bare turn-on** (`automation.luminance_bathroom_night_lamp`): last brightness (AL does not touch brightness)

`autoreset_control_seconds: 0` prevents AL from resuming color adaptation after any explicit state change — status colors persist until the light is turned off.

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.status_lamps_adaptive_lighting_status_lamps` | on |
| `switch.adaptive_lighting_status_lamps_adaptive_lighting_adapt_brightness_status_lamps` | **off** — leave this off |
| `switch.adaptive_lighting_status_lamps_adaptive_lighting_adapt_color_status_lamps` | on |
| `switch.adaptive_lighting_status_lamps_adaptive_lighting_sleep_mode_status_lamps` | off |

> **Note:** Status Lamps switch entity IDs use an unusual naming pattern (title prepended before `adaptive_lighting_`) due to how the integration was originally registered. Verify in Developer Tools → States before referencing in automations.

**Settings:**

| Setting | Value | Notes |
|---|---|---|
| `interval` | `90` | Matches Color Only baseline. |
| `transition` | `45` | |
| `initial_transition` | `1` | |
| `min_brightness` | `35` | Not applied (adapt_brightness switch is off). Set as a safe default if brightness adaptation is ever re-enabled. |
| `max_brightness` | `35` | Same — safe default only. |
| `sleep_brightness` | `35` | Same — safe default only. |
| `min_color_temp` | `2000` | |
| `max_color_temp` | `5500` | |
| `sleep_color_temp` | `2000` | |
| `sleep_rgb_color` | `[131, 17, 0]` | Aligned to Color Only. |
| `brightness_mode` | `tanh` | |
| `brightness_mode_time_dark` | `1800` | |
| `brightness_mode_time_light` | `5400` | |
| `min_sunrise_time` | `06:30` | Aligned to Color Only. |
| `max_sunrise_time` | `07:30` | |
| `min_sunset_time` | `20:00` | |
| `max_sunset_time` | `21:00` | |
| `take_over_control` | `true` | |
| `take_over_control_mode` | `pause_changed` | Aligned to Color Only. Safe in combination with `autoreset_control_seconds: 0`. |
| `adapt_only_on_bare_turn_on` | `true` | |
| `detect_non_ha_changes` | `false` | |
| `autoreset_control_seconds` | `0` | **Load-bearing.** See callout below. |
| `skip_redundant_commands` | `true` | Aligned to Color Only. |
| `send_split_delay` | `100` | Aligned to Color Only. |
| `prefer_rgb_color` | `false` | |
| `only_once` | `false` | |
| `separate_turn_on_commands` | `true` | |
| `adapt_delay` | `0` | |

> **Coordinated change:** `autoreset_control_seconds: 0` is load-bearing. `automation.sync_living_room_status_lamp_to_alarm_and_guest_modes` only re-fires on alarm/guest/sleep state changes — a re-armed alarm would silently lose its red indicator after 30 min if autoreset were nonzero. Do not align this setting to Standard or Color Only. The `min_brightness`, `max_brightness`, and `sleep_brightness` values are not currently applied (adapt_brightness switch is off) but are set to 35 as a safe default if brightness adaptation is ever re-enabled.

---

## Step 3 — Sleep-mode wiring

Sleep mode is not scheduled. The "Everyone Sleeping" automation turns sleep mode on for all canonical instances when `input_boolean.everyone_sleeping` turns on, and off when it turns off.

In the "Everyone Sleeping" automation, call `switch.turn_on` / `switch.turn_off` targeting these entities:

| Instance | Sleep Mode Switch |
|---|---|
| Standard | `switch.adaptive_lighting_sleep_mode_standard` |
| Color Only | `switch.adaptive_lighting_sleep_mode_color_only` |
| Avery Schedule | `switch.adaptive_lighting_sleep_mode_avery_schedule` |
| Status Lamps | `switch.adaptive_lighting_status_lamps_adaptive_lighting_sleep_mode_status_lamps` |

> The "Everyone Sleeping" automation is a household-wide automation outside the scope of this guide. This step documents the sleep-mode switch entity IDs it must reference.

---

## Step 4 — MQTT pre-staging

Pre-staging prevents bulbs from flashing to their previous state on turn-on. See [Architecture §8](#8-mqtt-pre-staging-for-off-state-bulbs) for the full rationale.

### Enable execute_if_off on each bulb

For every bulb to be pre-staged, run this in **Developer Tools → Actions** (YAML mode), substituting the Z2M friendly name:

```yaml
action: mqtt.publish
data:
  topic: "zigbee2mqtt/<Z2M FRIENDLY NAME>/set"
  payload: >-
    {
      "color_options": {"execute_if_off": true},
      "level_config": {"execute_if_off": true},
      "power_on_behavior": "previous"
    }
```

Three settings are pushed in one publish:

- `color_options.execute_if_off: true` — color temperature commands are stored while off
- `level_config.execute_if_off: true` — brightness commands are stored while off
- `power_on_behavior: previous` — restore previous brightness/color after a power outage rather than booting to full-on

### Verify and functional test

After publishing, open Z2M frontend → device state for one of the bulbs. It should show `execute_if_off: true` in both `color_options` and `level_config`.

Then confirm the bulb actually honors `execute_if_off` before committing to the automation:

1. Disable AL for the fixture (turn off the main AL switch).
2. Turn all bulbs in the fixture off.
3. Publish a deliberate dim/warm payload in Developer Tools → Actions:

   ```yaml
   action: mqtt.publish
   data:
     topic: "zigbee2mqtt/<Z2M FRIENDLY NAME>/set"
     payload: '{"state": null, "brightness": 50, "color_temp": 400}'
   ```

4. Confirm Z2M device state shows `brightness: 50`, `color_temp: 400`, `state: "OFF"`.
5. Turn the bulb on by any method. It should power up at ~20% brightness (~2500K).
6. Re-enable AL.

### Deployed automation: AL Pre-Stage — Standard (`automation.al_pre_stage_standard`)

Covers all Standard and Color Only fixtures with Z2M-managed bulbs. Standard fixtures receive full payloads (brightness + color temp). Entrance Ceiling and Bathroom Hallway Ceiling receive color-only payloads (brightness omitted — adapt_brightness is off for these Color Only fixtures). Kitchen Counter Strip is not pre-staged.

```yaml
alias: AL Pre-Stage — Standard
description: >-
  Keeps bulbs covered by both Standard and Color Only pre-loaded with the
  current Adaptive Lighting values whenever they are off. With execute_if_off
  enabled on the bulbs (set via direct MQTT publish), Z2M stores the values
  without turning the bulb on — so the next turn-on, from any source, lands
  at the correct adapted state instead of the last-on values.

  Solves the "flash to previous brightness/color before AL catches up" problem
  for turn-on paths that bypass HA's light.turn_on service: Zigbee bindings,
  physical power cycles, and any other on-event AL's intercept doesn't see.

  Triggered on attribute change of switch.adaptive_lighting_standard
  (brightness_pct only). Both Standard and Color Only follow the same
  household schedule and calculate identical curve values, so reading from a
  single switch is mathematically correct for all covered fixtures.

  Two payload types are used:
    - Full payload (state, brightness, color_temp) for Standard fixtures.
    - Color-only payload (state, color_temp) for Color Only fixtures —
      brightness intentionally omitted so the bulb retains its user-set value.

  Per-fixture blocks run in series with a 0.5-second stagger to spread the
  MQTT publish burst over time. Within each fixture, per-bulb publishes run
  in parallel. Only publishes to bulbs that are currently off.

mode: single
max_exceeded: silent

variables:
  al_switch: switch.adaptive_lighting_standard

trigger:
  - id: brightness_changed
    alias: AL recalculated brightness_pct
    platform: state
    entity_id: switch.adaptive_lighting_standard
    attribute: brightness_pct

action:
  - alias: Pre-stage Office Ceiling bulbs in parallel
    parallel:
      - alias: Office Ceiling Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.office_ceiling_bulb_1
            state: "off"
        then:
          - alias: Publish current AL curve values to Office Ceiling Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Office Ceiling Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Office Ceiling Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.office_ceiling_bulb_2
            state: "off"
        then:
          - alias: Publish current AL curve values to Office Ceiling Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Office Ceiling Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Master Bedroom Fan bulbs in parallel
    parallel:
      - alias: Master Bedroom Fan Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.master_bedroom_fan_bulb_1
            state: "off"
        then:
          - alias: Publish current AL curve values to Master Bedroom Fan Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Master Bedroom Fan Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Master Bedroom Fan Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.master_bedroom_fan_bulb_2
            state: "off"
        then:
          - alias: Publish current AL curve values to Master Bedroom Fan Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Master Bedroom Fan Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Master Bedroom Fan Bulb 3 — pre-stage if currently off
        if:
          - alias: Bulb 3 is off
            condition: state
            entity_id: light.master_bedroom_fan_bulb_3
            state: "off"
        then:
          - alias: Publish current AL curve values to Master Bedroom Fan Bulb 3
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Master Bedroom Fan Bulb 3/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Master Bedroom Fan Bulb 4 — pre-stage if currently off
        if:
          - alias: Bulb 4 is off
            condition: state
            entity_id: light.master_bedroom_fan_bulb_4
            state: "off"
        then:
          - alias: Publish current AL curve values to Master Bedroom Fan Bulb 4
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Master Bedroom Fan Bulb 4/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Living Room Fan bulbs in parallel
    parallel:
      - alias: Living Room Fan Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.living_room_fan_bulb_1
            state: "off"
        then:
          - alias: Publish current AL curve values to Living Room Fan Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Living Room Fan Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Living Room Fan Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.living_room_fan_bulb_2
            state: "off"
        then:
          - alias: Publish current AL curve values to Living Room Fan Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Living Room Fan Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Living Room Fan Bulb 3 — pre-stage if currently off
        if:
          - alias: Bulb 3 is off
            condition: state
            entity_id: light.living_room_fan_bulb_3
            state: "off"
        then:
          - alias: Publish current AL curve values to Living Room Fan Bulb 3
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Living Room Fan Bulb 3/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Entrance Ceiling bulbs in parallel (color-only)
    parallel:
      - alias: Entrance Ceiling Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.entrance_ceiling_bulb_1
            state: "off"
        then:
          - alias: Publish current AL color temp to Entrance Ceiling Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Entrance Ceiling Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Entrance Ceiling Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.entrance_ceiling_bulb_2
            state: "off"
        then:
          - alias: Publish current AL color temp to Entrance Ceiling Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Entrance Ceiling Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Bathroom Hallway Ceiling bulbs in parallel (color-only)
    parallel:
      - alias: Bathroom Hallway Ceiling Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.bathroom_hallway_ceiling_bulb_1
            state:
              - "off"
        then:
          - alias: Publish current AL color temp to Bathroom Hallway Ceiling Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Bathroom Hallway Ceiling Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Bathroom Hallway Ceiling Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.bathroom_hallway_ceiling_bulb_2
            state:
              - "off"
        then:
          - alias: Publish current AL color temp to Bathroom Hallway Ceiling Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Bathroom Hallway Ceiling Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
```

### Deployed automation: AL Pre-Stage — Avery Schedule (`automation.al_pre_stage_avery_schedule`)

Covers Avery Room Ceiling. Same pattern as Standard — full brightness + color temp payload. Reads from `switch.adaptive_lighting_avery_schedule` so it follows Avery's schedule clamp, not the household schedule.

```yaml
alias: AL Pre-Stage — Avery Schedule
description: >-
  Keeps bulbs covered by Avery Schedule pre-loaded with the current Adaptive
  Lighting brightness and color temperature whenever they are off. Same payload
  structure as Standard — full brightness + color_temp. The schedule difference
  (earlier evening) is handled by the AL switch's own configuration.

  Currently covers Avery Room Ceiling only. The stagger pattern is in place
  for future additions.

mode: single
max_exceeded: silent

variables:
  al_switch: switch.adaptive_lighting_avery_schedule

trigger:
  - id: brightness_changed
    alias: AL recalculated brightness_pct
    platform: state
    entity_id: switch.adaptive_lighting_avery_schedule
    attribute: brightness_pct

action:
  - alias: Pre-stage Avery Room Ceiling bulbs in parallel
    parallel:
      - alias: Avery Room Ceiling Bulb 1 — pre-stage if currently off
        if:
          - alias: Bulb 1 is off
            condition: state
            entity_id: light.avery_room_ceiling_bulb_1
            state: "off"
        then:
          - alias: Publish current AL curve values to Avery Room Ceiling Bulb 1
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Avery Room Ceiling Bulb 1/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
      - alias: Avery Room Ceiling Bulb 2 — pre-stage if currently off
        if:
          - alias: Bulb 2 is off
            condition: state
            entity_id: light.avery_room_ceiling_bulb_2
            state: "off"
        then:
          - alias: Publish current AL curve values to Avery Room Ceiling Bulb 2
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/Avery Room Ceiling Bulb 2/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
```

### Adding a new fixture

To pre-stage a new fixture, add it to the relevant automation:

- Standard or Color Only fixture → extend `automation.al_pre_stage_standard`
- Avery Schedule fixture → extend `automation.al_pre_stage_avery_schedule`
- Status Lamps fixtures are not pre-staged (single-entity lamps, not multi-bulb fixtures)

Before extending: confirm the fixture's bulbs are Z2M-managed, collect bulb entity IDs (`light.[area]_[fixture]_bulb_[n]`) and Z2M friendly names, and run the functional test above.

Add a new `parallel` block following the pattern of existing blocks, followed by a `delay: milliseconds: 500` stagger. For Standard fixtures, use the full payload (brightness + color temp). For Color Only fixtures, use the color-only payload (color temp only).

Brightness conversion: AL exposes `brightness_pct` (0–100); Z2M expects `brightness` (0–254). Template: `{{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }}`.

---

## Legacy instances

Five AL instances from before the canonical-instance model are pending decommission. They are not managed as part of this guide's configuration model.

- **Office - Bourbon Lamp** — `light.office_bourbon_lamp`
- **Master Bedroom Accent Lamps** — `light.master_bedroom_nightstand_lamp_left`, `light.portable_accent_lamp`
- **Master Bedroom - Bathroom Fan** — `light.master_bathroom_fan`
- **Outside - Porch Lights** — `light.outside_porch_ceiling`
- **Avery Room Desk Lamp** — `light.avery_room_desk_lamp`

---

## Related HA Config

| Artifact | Entity ID | Type |
|---|---|---|
| Standard Adaptive Lighting | `switch.adaptive_lighting_standard` | AL Switch |
| Standard Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_standard` | AL Switch |
| Standard Adapt Color | `switch.adaptive_lighting_adapt_color_standard` | AL Switch |
| Standard Sleep Mode | `switch.adaptive_lighting_sleep_mode_standard` | AL Switch |
| Color Only Adaptive Lighting | `switch.adaptive_lighting_color_only` | AL Switch |
| Color Only Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_color_only` | AL Switch |
| Color Only Adapt Color | `switch.adaptive_lighting_adapt_color_color_only` | AL Switch |
| Color Only Sleep Mode | `switch.adaptive_lighting_sleep_mode_color_only` | AL Switch |
| Avery Schedule Adaptive Lighting | `switch.adaptive_lighting_avery_schedule` | AL Switch |
| Avery Schedule Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_avery_schedule` | AL Switch |
| Avery Schedule Adapt Color | `switch.adaptive_lighting_adapt_color_avery_schedule` | AL Switch |
| Avery Schedule Sleep Mode | `switch.adaptive_lighting_sleep_mode_avery_schedule` | AL Switch |
| Status Lamps Adaptive Lighting | `switch.status_lamps_adaptive_lighting_status_lamps` | AL Switch |
| Status Lamps Adapt Brightness | `switch.adaptive_lighting_status_lamps_adaptive_lighting_adapt_brightness_status_lamps` | AL Switch |
| Status Lamps Adapt Color | `switch.adaptive_lighting_status_lamps_adaptive_lighting_adapt_color_status_lamps` | AL Switch |
| Status Lamps Sleep Mode | `switch.adaptive_lighting_status_lamps_adaptive_lighting_sleep_mode_status_lamps` | AL Switch |
| AL Pre-Stage — Standard | `automation.al_pre_stage_standard` | Automation |
| AL Pre-Stage — Avery Schedule | `automation.al_pre_stage_avery_schedule` | Automation |

---

## Related Files

No on-disk files are created or modified by this integration. All artifacts live in HA.

---

## Related Documents

- `standards/naming.md` — entity ID and friendly name conventions used throughout this document
- `guides/hue_sync.md` — the Hue Sync system that manipulates AL Standard's brightness limits at runtime via `adaptive_lighting.change_switch_settings`; its restore values (60/95%) must track Standard's `min_brightness`/`max_brightness`

---

## Troubleshooting

### AL Configuration

| Symptom | Likely Cause | Fix |
|---|---|---|
| Inconsistent brightness across bulbs in the same fixture | One bulb is "manually controlled" while others are adapting | Toggle the bulb off/on, or call `adaptive_lighting.set_manual_control` to clear the flag |
| Sleep mode not triggering | "Everyone Sleeping" automation references wrong entity IDs | Verify entity IDs in Step 3 against Developer Tools → States; Status Lamps uses the long entity ID format |
| Specific bulb stuck at wrong brightness/color while others adapt | `skip_redundant_commands` is skipping due to stale HA state after a mesh hiccup or Z2M restart | Disable `skip_redundant_commands` on that switch temporarily; re-enable when resolved |
| Status lamp color overwritten after ~30 minutes | Status Lamps `autoreset_control_seconds` set to nonzero | Verify `autoreset_control_seconds: 0` on the Status Lamps AL instance |

### Pre-Staging

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bulb powers up at old values after deployment | Bulb didn't accept `execute_if_off`, or Z2M didn't pass it through | Re-run the execute_if_off publish; verify Z2M device state shows `execute_if_off: true` in both `color_options` and `level_config` |
| Automation never triggers | Wrong AL switch entity ID, or `brightness_pct` attribute absent | Open Developer Tools → States → AL switch; verify entity ID and attribute name |
| Automation triggers but Z2M shows no publishes | Wrong topic — Z2M friendly name typo, or spaces not quoted | Compare topic against Z2M frontend's exact friendly name |
| Bulb still flashes on turn-on after deployment | Pre-staged values are stale (AL was off during the last recalc) | Verify AL is enabled for this fixture; check Last Triggered on the automation |
| One bulb adapts correctly, another doesn't | Only one bulb has `execute_if_off` set | Re-run the execute_if_off publish for the affected bulb; verify via Z2M device state |
| Pre-staging publishes to bulbs that are on | `condition: state` check missing or wrong | Each bulb block must have an `if` check confirming `state: "off"` before publishing |
