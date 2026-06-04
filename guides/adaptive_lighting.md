# Adaptive Lighting
*Last updated: June 2026*

The canonical document for Adaptive Lighting (AL) configuration in this home. Covers the three canonical AL instance profiles, the sleep-mode wiring strategy, and the MQTT-based pre-staging system that prevents bulbs from flashing to their previous state on turn-on.

---

## Overview

Adaptive Lighting adjusts lights' brightness and color temperature through the day based on a configurable sun-position curve. Three canonical AL instances are maintained:

- **Standard** — brightness + color adaptation for ceiling fan fixtures where AL owns brightness entirely (`light.master_bedroom_fan`, `light.living_room_fan`, `light.office_ceiling`).
- **Color Only** — color temperature adaptation only for all other household lights. `switch.adaptive_lighting_adapt_brightness_color_only` is permanently off, making color-only behavior architectural rather than reliant on ephemeral manual-control state.
- **Avery Schedule** — brightness + color adaptation for Avery's ceiling (`light.avery_room_ceiling`), maintained as a separate instance to allow `automation.avery_room_sleep_mode` to enable sleep mode independently before `input_boolean.everyone_sleeping` activates.

MQTT-based pre-staging is deployed for Standard, Color Only, and Avery Schedule ceiling fixtures with Z2M-managed bulbs. Color Only ceiling fixtures receive color-only payloads — brightness is omitted so bulbs retain their user-set level on turn-on. Fixtures not compatible with pre-staging are listed in Step 4.

---

## Architecture

```
Standard (brightness + color; AL owns brightness)
│  light.master_bedroom_fan (4 bulbs)           ← full pre-stage payload
│  light.living_room_fan (3 bulbs)              ← full pre-stage payload
│  light.office_ceiling (2 bulbs)               ← full pre-stage payload
└── automation.al_pre_stage_standard

Color Only (color only; adapt_brightness switch permanently off)
│  light.entrance_ceiling (2 bulbs)             ← color-only pre-stage payload
│  light.bathroom_hallway_ceiling (2 bulbs)     ← color-only pre-stage payload
│  light.portable_accent_lamp                   ← color-only pre-stage payload
│  light.kitchen_counter_strip                  (not pre-staged — not compatible)
│  light.kitchen_sink_bulb                      (not pre-staged — not compatible)
│  light.bathroom_night_lamp                    (not pre-staged — not compatible)
│  light.living_room_status_lamp                (not pre-staged — not compatible)
│  light.office_presence_sensor                 (not pre-staged — not compatible)
│  light.office_bourbon_lamp                    (not pre-staged — not compatible)
│  light.master_bedroom_nightstand_lamp_left    (not pre-staged — not compatible)
│  light.avery_room_desk_lamp                   (not pre-staged — not compatible)
└── automation.al_pre_stage_standard (shared)

Avery Schedule (brightness + color; sleep mode isolation)
│  light.avery_room_ceiling (2 bulbs)           ← full pre-stage payload (Avery Schedule instance)
└── automation.al_pre_stage_standard (shared)
```

### Design decisions

#### 1. Hybrid clamping over pure sun-tracking

AL's default behavior tracks the real sun, which means lights stay bright and cool past 9 pm in summer and start warming/dimming by 5 pm in winter. The four clamp settings (`min_sunrise_time`, `max_sunrise_time`, `min_sunset_time`, `max_sunset_time`) bound when AL's "sunrise event" and "sunset event" can occur. Within those bounds, AL still uses real sun position; outside them, AL uses the clamp. The result is meaningful seasonal variation but never outside the user's actual day.

#### 2. tanh brightness mode

AL's `default` brightness mode produces a bell curve peaked at solar noon — peak brightness is hit at noon, not at the user's preferred mid-morning point. `tanh` mode decouples brightness ramp shape from sun elevation. Two settings (`brightness_mode_time_dark`, `brightness_mode_time_light`) define a smooth S-curve centered on the (clamped) sunrise/sunset events, giving explicit control over when the morning ramp completes and when evening wind-down begins.

#### 3. Two instances: Standard (full) and Color Only (color only)

Ceiling fan fixtures belong in Standard — AL owns their brightness entirely. All other household lights belong in Color Only.

The key architectural choice: `switch.adaptive_lighting_adapt_brightness_color_only` is permanently off. This makes it impossible for AL to adapt brightness for Color Only lights regardless of manual-control state or restarts. The alternative — relying on `adapt_only_on_bare_turn_on` and `take_over_control_mode: pause_changed` to build up manual-control state — was fragile: HA restarts wiped the in-memory state, causing lights to jump to AL's brightness curve until manually corrected.

`autoreset_control_seconds: 0` on both instances means manually-set colors persist until the light is turned off. This is load-bearing for `automation.sync_living_room_status_lamp_to_alarm_and_guest_modes`, which sets status colors (red for armed away, green for guest mode) that must survive until state changes again — a nonzero autoreset would silently overwrite a red indicator after the reset interval.

#### 4. Conservative brightness range

Standard range: `min_brightness: 60` to `max_brightness: 95`. The 60% floor is the evening floor *before sleep mode*, not the night floor — sleep mode drops brightness to `sleep_brightness: 2` independently. Tune `min_brightness` toward 40–50 if the wind-down hour feels too active.

#### 5. Sleep mode via automation, not schedule

Sleep mode is not tied to a fixed time. It is triggered explicitly by the "Everyone Sleeping" automation, which calls `switch.turn_on` on each canonical instance's sleep-mode switch entity. This decouples sleep behavior from the AL curve — sleep mode kicks in only when actually going to bed. See [Step 3 — Sleep-mode wiring](#step-3--sleep-mode-wiring) for entity IDs.

#### 6. Explicit commands win over adaptation

`adapt_only_on_bare_turn_on: true` means that when `light.turn_on` is called with brightness or color specified (a scene, voice command, "set to 70%"), AL skips adaptation and marks the light as manually controlled. Only "bare" turn-ons — `light.turn_on` with no brightness or color — are adapted to the curve. Apple Home turn-ons via Matter Hub and Z2M Aqara button triggers send bare turn-ons by default.

#### 7. skip_redundant_commands tradeoff

With `skip_redundant_commands: true`, AL compares the target value against HA's recorded state before sending a command. If already equal, the command is skipped.

**Why enabled:** With ~20 bulbs across two canonical instances running `interval: 90` cycles, redundant commands during flat parts of the curve (midday peak, overnight floor) generate meaningful Zigbee/Hue chatter.

**Tradeoff:** A brief mesh hiccup or Z2M restart can leave HA's recorded state out of step with the bulb's actual state. AL silently skips a command, leaving the bulb at the wrong value until the curve target changes meaningfully. Recovery is automatic — the next sunrise or sunset transition forces fresh commands.

#### 8. MQTT pre-staging for off-state bulbs

AL only sends commands to bulbs that are on. Off bulbs catch up via `intercept: true` when HA processes a `light.turn_on` call, but this has two failure modes:

1. **Z2M command translation.** Z2M may translate the intercepted call into multiple sequential Zigbee commands — causing a brief flash at the bulb's previous on-state before new values land.
2. **Turn-on paths that bypass HA.** Zigbee bindings, physical wall switches, or any other path that doesn't go through `light.turn_on`.

Pre-staging addresses both by publishing the current AL target values directly to each bulb via MQTT while the bulb is off. With `execute_if_off: true` enabled on the bulb, Z2M stores the values without turning it on. When any turn-on event occurs, the bulb powers up at the pre-staged values immediately.

The pre-staging automation runs on a 10-minute schedule. Both brightness and color temperature are sent in each publish. The interval is short enough that even during the steepest part of the evening ramp, a bulb turning on lands within imperceptible range of the current curve target.

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
5. Repeat steps 3–4 for the remaining canonical instance: Avery Schedule.

Each instance creates a set of switch entities (master, adapt_brightness, adapt_color, sleep_mode) under the AL domain.

---

## Step 2 — Configure the two canonical AL instances

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
| `autoreset_control_seconds` | `1800` | AL reclaims control 30 minutes after a manual change. Appropriate for ceiling fixtures where AL fully owns brightness — no status color persistence concern. |
| `skip_redundant_commands` | `true` | Skips commands when target equals recorded state. Reduces Zigbee traffic. See Design Decision §7. |
| `send_split_delay` | `0` | Hue bulbs on Z2M handle brightness and color in a single command; split delay not needed. |
| `prefer_rgb_color` | `false` | Use color temperature, not RGB. |
| `only_once` | `false` | Continuous adaptation throughout the day, not just at turn-on. |
| `separate_turn_on_commands` | `false` | |
| `adapt_delay` | `0` | |

### 2b. Color Only

**Lights:** `light.entrance_ceiling`, `light.bathroom_hallway_ceiling`, `light.portable_accent_lamp`, `light.kitchen_counter_strip`, `light.kitchen_sink_bulb`, `light.bathroom_night_lamp`, `light.living_room_status_lamp`, `light.office_presence_sensor`, `light.office_bourbon_lamp`, `light.master_bedroom_nightstand_lamp_left`, `light.avery_room_desk_lamp`

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.adaptive_lighting_color_only` | on |
| `switch.adaptive_lighting_adapt_brightness_color_only` | **off — permanently disabled** |
| `switch.adaptive_lighting_adapt_color_color_only` | on |
| `switch.adaptive_lighting_sleep_mode_color_only` | off — controlled by "Everyone Sleeping" automation |

**Settings (deviations from Standard):**

| Setting | Color Only | Standard | Reason |
|---|---|---|---|
| `autoreset_control_seconds` | `0` | `1800` | Status lamps (`living_room_status_lamp`, `office_presence_sensor`) hold specific RGB colors (red/green) set by `automation.sync_living_room_status_lamp_to_alarm_and_guest_modes`. A nonzero autoreset would silently overwrite a red "armed away" indicator after the reset interval. |

All other curve and timing settings match Standard. Change them in both instances together if adjusting the curve.

> **Coordinated change:** `autoreset_control_seconds: 0` is load-bearing for `automation.sync_living_room_status_lamp_to_alarm_and_guest_modes`. That automation sets status colors (red for alarm armed away, green for guest mode, warm white for sleep) that must persist until the light is turned off — it only re-fires on state changes. A nonzero autoreset would silently overwrite a red "armed away" indicator after the reset interval. Do not change this setting without also reworking the sync automation to re-fire periodically.

> **Note:** `switch.adaptive_lighting_adapt_brightness_color_only` must remain off. Re-enabling it would cause AL to adapt brightness for all Color Only lights, including those whose automations set specific levels (status lamps, bathroom night lamp). See Design Decision §3.

> **Note:** `light.avery_room_desk_lamp` is in Color Only even though it is in Avery's room — it is a lamp where the user controls brightness, not a ceiling fixture. Its button automation (`automation.avery_s_room_desk_lamp_remote_is_pressed`) uses `adaptive_lighting.set_manual_control` and `adaptive_lighting.apply` referencing `switch.adaptive_lighting_color_only` to re-apply AL color after an explicit brightness turn-on.

### 2c. Avery Schedule

**Lights:** `light.avery_room_ceiling`

Avery Schedule shares all settings with Standard. A separate instance is maintained to allow `automation.avery_room_sleep_mode` to enable sleep mode on Avery's ceiling independently, before `input_boolean.everyone_sleeping` activates.

**Runtime switches:**

| Entity ID | Default State |
|---|---|
| `switch.adaptive_lighting_avery_schedule` | on |
| `switch.adaptive_lighting_adapt_brightness_avery_schedule` | on |
| `switch.adaptive_lighting_adapt_color_avery_schedule` | on |
| `switch.adaptive_lighting_sleep_mode_avery_schedule` | off — controlled by "Everyone Sleeping" automation |

All settings match Standard.


---

## Step 3 — Sleep-mode wiring

Sleep mode is not scheduled. The "Everyone Sleeping" automation turns sleep mode on for all canonical instances when `input_boolean.everyone_sleeping` turns on, and off when it turns off.

In the "Everyone Sleeping" automation, call `switch.turn_on` / `switch.turn_off` targeting these entities:

| Instance | Sleep Mode Switch |
|---|---|
| Standard | `switch.adaptive_lighting_sleep_mode_standard` |
| Color Only | `switch.adaptive_lighting_sleep_mode_color_only` |
| Avery Schedule | `switch.adaptive_lighting_sleep_mode_avery_schedule` |

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

### Fixtures not compatible with pre-staging

The following fixtures are under AL control but cannot be pre-staged. All require hardware replacement before pre-staging is possible.

| Fixture | Entity | Instance |
|---|---|---|
| Kitchen Counter Strip | `light.kitchen_counter_strip` | Color Only |
| Kitchen Sink | `light.kitchen_sink_bulb` | Color Only |
| Bathroom Night Lamp | `light.bathroom_night_lamp` | Color Only |
| Living Room Status Lamp | `light.living_room_status_lamp` | Color Only |
| Office Presence Sensor | `light.office_presence_sensor` | Color Only |
| Office Bourbon Lamp | `light.office_bourbon_lamp` | Color Only |
| Master Bedroom Nightstand Lamp | `light.master_bedroom_nightstand_lamp_left` | Color Only |
| Avery Room Desk Lamp | `light.avery_room_desk_lamp` | Color Only |

### Deployed automation: AL Pre-Stage (`automation.al_pre_stage_standard`)

Covers all pre-stage-compatible fixtures. Standard and Avery Schedule fixtures receive full payloads (brightness + color temp), each referencing their respective AL switch. Color Only fixtures receive color-only payloads — brightness omitted so the bulb retains its user-set level on turn-on.

Per-fixture blocks run in series with a 0.5-second stagger. Within each fixture, per-bulb publishes run in parallel. Only publishes to bulbs that are currently off.

```yaml
alias: "Adaptive Lighting: Pre-Stage"
description: >-
  Keeps all pre-stage-compatible bulbs loaded with current Adaptive Lighting
  values whenever they are off. With execute_if_off enabled on the bulbs (set
  via direct MQTT publish), Z2M stores the values without turning the bulb on —
  so the next turn-on, from any source, lands at the correct adapted state
  instead of the last-on values.

  Solves the "flash to previous brightness/color before AL catches up" problem
  for turn-on paths that bypass HA's light.turn_on service: Zigbee bindings,
  physical power cycles, and any other on-event AL's intercept doesn't see.

  Runs on a 10-minute schedule. Standard and Avery Schedule fixtures receive
  full payloads (brightness + color temp). Color Only fixtures receive
  color-only payloads — brightness intentionally omitted so the bulb retains
  its user-set value. Brightness and color temp are pre-computed once per run
  in the variables block and referenced in each payload.

  Per-fixture blocks run in series with a 0.5-second stagger to spread the
  MQTT publish burst. Within each fixture, per-bulb publishes run in parallel.
  Only publishes to bulbs that are currently off.

mode: single
max_exceeded: silent

variables:
  al_switch: switch.adaptive_lighting_standard
  brightness: "{{ ((state_attr('switch.adaptive_lighting_standard', 'brightness_pct') / 100) * 254) | round(0) | int }}"
  color_temp: "{{ state_attr('switch.adaptive_lighting_standard', 'color_temp_mired') | int }}"

trigger:
  - trigger: time_pattern
    minutes: /10

action:
  - alias: Pre-stage Office Ceiling bulbs in parallel (brightness & color)
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Master Bedroom Fan bulbs in parallel (brightness & color)
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Living Room Fan bulbs in parallel (brightness & color)
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Entrance Ceiling bulbs in parallel (color)
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
              payload: '{"state": null, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Bathroom Hallway Ceiling bulbs in parallel (color)
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
              payload: '{"state": null, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Portable Accent Lamp — pre-stage if currently off (color)
    if:
      - alias: Lamp is off
        condition: state
        entity_id: light.portable_accent_lamp
        state: "off"
    then:
      - alias: Publish current AL color temp to Portable Accent Lamp
        action: mqtt.publish
        data:
          topic: "zigbee2mqtt/Portable Accent Lamp/set"
          payload: '{"state": null, "color_temp": {{ color_temp }}}'

  - alias: Stagger before next fixture
    delay:
      milliseconds: 500

  - alias: Pre-stage Avery Room Ceiling bulbs in parallel (brightness & color)
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
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
              payload: '{"state": null, "brightness": {{ brightness }}, "color_temp": {{ color_temp }}}'
```

Assign to the **Maintenance** category with labels **Adaptive Lighting** and **Multi-Area**. Leave area unset — the pre-stage automation covers all areas.

### Adding a new fixture

To pre-stage a new fixture, extend `automation.al_pre_stage_standard`. Before extending, confirm the fixture's bulbs are Z2M-managed, collect bulb entity IDs (`light.[area]_[fixture]_bulb_[n]`) and Z2M friendly names, and run the functional test above.

Add a new `parallel` block following the pattern of existing blocks, followed by a `delay: milliseconds: 500` stagger.

- Standard fixture: full payload (brightness + color temp). Reference `al_switch`.
- Color Only fixture: color-only payload (color temp only). Reference `al_switch`.

Brightness and color temp are pre-computed in the automation's `variables` block as `brightness` and `color_temp`. Use `{{ brightness }}` and `{{ color_temp }}` in full payloads; `{{ color_temp }}` alone in color-only payloads. If you ever need the raw conversion: `{{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }}`.

---

## Related HA Config

| Artifact | Entity ID | Type |
|---|---|---|
| Standard Adaptive Lighting | `switch.adaptive_lighting_standard` | AL Switch |
| Standard Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_standard` | AL Switch |
| Standard Adapt Color | `switch.adaptive_lighting_adapt_color_standard` | AL Switch |
| Standard Sleep Mode | `switch.adaptive_lighting_sleep_mode_standard` | AL Switch |
| Color Only Adaptive Lighting | `switch.adaptive_lighting_color_only` | AL Switch |
| Color Only Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_color_only` | AL Switch (permanently off) |
| Color Only Adapt Color | `switch.adaptive_lighting_adapt_color_color_only` | AL Switch |
| Color Only Sleep Mode | `switch.adaptive_lighting_sleep_mode_color_only` | AL Switch |
| Avery Schedule Adaptive Lighting | `switch.adaptive_lighting_avery_schedule` | AL Switch |
| Avery Schedule Adapt Brightness | `switch.adaptive_lighting_adapt_brightness_avery_schedule` | AL Switch |
| Avery Schedule Adapt Color | `switch.adaptive_lighting_adapt_color_avery_schedule` | AL Switch |
| Avery Schedule Sleep Mode | `switch.adaptive_lighting_sleep_mode_avery_schedule` | AL Switch |
| AL Pre-Stage | `automation.al_pre_stage_standard` | Automation |

---

## Related Files

No on-disk files are created or modified by this integration. All artifacts live in HA.

---

## Related Documents

- `standards/naming.md` — entity ID and friendly name conventions used throughout this document
- `guides/hue_sync.md` — the Hue Sync system that dims the Living Room Fan during sync sessions; it relies on `take_over_control_mode: pause_changed` being configured on Standard to pause per-light brightness without affecting the whole instance

---

## Troubleshooting

### AL Configuration

| Symptom | Likely Cause | Fix |
|---|---|---|
| Inconsistent brightness across bulbs in the same fixture | One bulb is "manually controlled" while others are adapting | Toggle the bulb off/on, or call `adaptive_lighting.set_manual_control` to clear the flag |
| Sleep mode not triggering | "Everyone Sleeping" automation references wrong entity IDs | Verify entity IDs in Step 3 against Developer Tools → States |
| Specific bulb stuck at wrong brightness/color while others adapt | `skip_redundant_commands` is skipping due to stale HA state after a mesh hiccup or Z2M restart | Disable `skip_redundant_commands` on that switch temporarily; re-enable when resolved |
| Status lamp color overwritten after a period of time | Standard `autoreset_control_seconds` set to nonzero | Verify `autoreset_control_seconds: 0` on the Standard AL instance |
| Status lamp color overwritten after HA restart | AL's in-memory manual-control state (color paused) is wiped on restart. Status lamps with specific RGB colors (red/green) come back as a bare turn-on and AL adapts color to its curve. | `automation.sync_living_room_status_lamp_to_alarm_and_guest_modes` fires 30s after startup to re-apply the correct status color based on current alarm/guest/sleep state. Non-status Color Only lights are not affected — AL adapting their color temp on restart is the correct behavior. |

### Pre-Staging

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bulb powers up at old values after deployment | Bulb didn't accept `execute_if_off`, or Z2M didn't pass it through | Re-run the execute_if_off publish; verify Z2M device state shows `execute_if_off: true` in both `color_options` and `level_config` |
| Automation never triggers | Wrong AL switch entity ID, or `brightness_pct` attribute absent | Open Developer Tools → States → AL switch; verify entity ID and attribute name |
| Automation triggers but Z2M shows no publishes | Wrong topic — Z2M friendly name typo, or spaces not quoted | Compare topic against Z2M frontend's exact friendly name |
| Bulb still flashes on turn-on after deployment | Pre-staged values are stale (AL was off during the last recalc) | Verify AL is enabled for this fixture; check Last Triggered on the automation |
| One bulb adapts correctly, another doesn't | Only one bulb has `execute_if_off` set | Re-run the execute_if_off publish for the affected bulb; verify via Z2M device state |
| Pre-staging publishes to bulbs that are on | `condition: state` check missing or wrong | Each bulb block must have an `if` check confirming `state: "off"` before publishing |
