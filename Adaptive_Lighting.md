# Adaptive Lighting
*Version 2.0 — May 2026*

The canonical document for Adaptive Lighting (AL) configuration in this home. Covers the design and rationale for how AL is configured, the procedure for enabling MQTT-based pre-staging on a fixture, and the operational concerns around running this setup day-to-day.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 2.0 | May 2026 | Canonical AL document |

---

## 1. Purpose & Scope

This document defines the Adaptive Lighting setup for this home. It is intended as the single source of truth for two related topics:

1. **Design and configuration of AL** — including the curve shape, schedule clamps, brightness/color ranges, and behavioral settings on each AL switch.
2. **Implementation procedure for MQTT-based pre-staging** — a Z2M-mediated technique that pre-loads the current AL target values onto bulbs while they are off, so they power up at the correct adapted state regardless of how the turn-on is triggered.

Audience: future-me and AI assistants helping future-me. The document is written to be self-contained for both: a fresh reader (human or AI) should be able to understand what is configured and why, and given the inputs in §7.2, an AI should be able to mechanically generate the MQTT commands and automation YAML needed to enable pre-staging on additional fixtures.

The fixtures currently covered by this configuration:

- `light.living_room_fan`
- `light.master_bedroom_fan`
- `light.office_ceiling`
- `light.avery_room_ceiling`

The pre-staging procedure (§7) is fixture-agnostic and can apply to any AL-managed fixture in the home.

---

## 2. Goals

1. **Consistency between rooms.** All fixtures share the same brightness curve, color temperature curve, and timing behavior. The only legitimate per-room divergence is bedtime schedule.
2. **Stability across seasons and DST.** Lights follow the user's daily schedule, not the real sun. Wake-up looks the same in January as in July.
3. **Hybrid sun/schedule tracking.** Within a bounded window, lights still respond to actual sun position so winter mornings feel different from summer mornings — but never outside the bounded window.
4. **No flash on turn-on.** Bulbs power up at the current adapted brightness and color temperature, regardless of how the turn-on is triggered. Solved via pre-staging (§3.9, §7).
5. **Single source of tuning.** Settings tables in §4 are the canonical reference. Any divergence in the live configuration is a bug to be reconciled.

---

## 3. Core Design Decisions

### 3.1 Hybrid clamping over pure sun-tracking

Adaptive Lighting's default behavior tracks the real sun, which means lights stay bright and cool past 9pm in summer and start warming/dimming by 5pm in winter. This negates the circadian benefit when the user's actual schedule is fixed year-round.

The four clamp settings (`min_sunrise_time`, `max_sunrise_time`, `min_sunset_time`, `max_sunset_time`) bound when AL's "sunrise event" and "sunset event" can occur. Within those bounds, AL still uses real sun position. Outside them, AL uses the clamp.

This is the "hybrid sun-based but clamped to schedule" approach: meaningful seasonal variation, but never outside the user's actual day.

### 3.2 `tanh` brightness mode over `default`

AL's `default` brightness mode produces a bell curve peaked at solar noon — meaning peak brightness is hit at noon, not at the user's preferred mid-morning point.

`tanh` mode decouples brightness ramp shape from sun elevation. Two settings (`brightness_mode_time_dark`, `brightness_mode_time_light`) define a smooth S-curve transition centered on the (clamped) sunrise/sunset events. This gives explicit control over when the morning ramp starts, when it completes, and the equivalent for the evening wind-down.

The result: lights ramp from `min_brightness` to `max_brightness` over a configurable window, then hold at max through the day until the evening wind-down begins.

### 3.3 Conservative brightness range

Range: `min_brightness: 60` to `max_brightness: 95`.

The narrow range reflects two preferences:

- Never run lights at 100% (avoids glare and extends bulb life).
- The 60% floor is the *evening floor before sleep mode triggers*, not the night floor. Sleep mode drops brightness to 5% independently of this curve.

If 60% feels too active during the wind-down hour before sleep mode, drop toward 40–50%. The night experience is unaffected because sleep mode handles it.

### 3.4 Uniform color temperature range across all bulbs

All bulbs use the same color temperature range so behavior feels consistent across the house:

- `min_color_temp` (warmest) = `2000K`. Hue's standard warmest value.
- `max_color_temp` (coolest) = `5500K`. Below the typical 6500K maximum because 6500K reads as harsh blue-white in residential ceiling fixtures.
- `sleep_color_temp` = `2000K`. Matches `min_color_temp` — bulb sits at its warmest during sleep mode.

### 3.5 Sleep mode handled by automation, not schedule

Sleep mode is *not* tied to a fixed time. It is triggered explicitly by the "Everyone Sleeping" automation, which calls `switch.turn_on` on each AL switch's sleep mode helper. This decouples sleep behavior from the AL curve:

- Adult bedtime varies (later on weekends, later when daughter is not present)
- Sleep mode kicks in only when actually going to bed, not on a schedule guess

Sleep settings: `sleep_brightness: 5`, `sleep_color_temp: 2000`.

### 3.6 Separate AL switches per light

Each light has its own AL switch. This was chosen over a single shared switch covering multiple lights to allow:

- Per-light manual override without affecting other rooms (`take_over_control` is per-switch)
- Per-light disable/enable for troubleshooting
- Per-room overrides like Avery's earlier sunset clamp

Tradeoff: settings must be kept synchronized across configurations. The values in §4 are the canonical source.

### 3.7 Explicit commands win over adaptation

When a `light.turn_on` call specifies brightness or color explicitly (e.g., a scene activation, a voice command like "set to 70%", a button bound to a specific level), AL skips adaptation and marks the light as manually controlled. Only "bare" turn-ons — `light.turn_on` with no brightness or color — get adapted to the curve.

This is controlled by `adapt_only_on_bare_turn_on: true` and complements `take_over_control: true`. Together they implement: AL is the default behavior, but any explicit instruction wins.

The light returns to adaptive mode the next time it's turned off and bare-turned-on.

Apple Home turn-on via Matter Hub is compatible — Apple Home toggles arrive as bare `light.turn_on` and adapt as expected. Z2M Aqara button device triggers also send bare turn-ons unless explicitly bound to a brightness level.

### 3.8 Skip redundant commands — traffic reduction tradeoff

With `skip_redundant_commands: true`, AL compares the target value against HA's recorded state before sending a command. If they're already equal, the command is skipped entirely.

**Why enabled:** With multiple fixtures (~15 bulbs total) all running the same `interval: 90` cycle, redundant commands during flat parts of the curve (midday peak, overnight floor) generate meaningful Zigbee chatter. Skipping them reduces mesh traffic and improves responsiveness for real changes.

**The tradeoff:** All bulbs are paired to Z2M (Sonoff EFR32MG24 coordinator on channel 11). Z2M state sync is generally good, but a brief mesh hiccup or Z2M restart can leave HA's recorded state out of step with the bulb's actual state. In that window, AL would silently skip a command, leaving the bulb at the wrong value until the next interval where the curve target changes meaningfully.

**Why this is acceptable:** The failure mode is recoverable — the next sunrise or sunset transition forces fresh commands across the curve. A bulb may briefly look wrong, not stay wrong forever.

**Symptoms that would indicate disabling:**

- A bulb visibly at the wrong brightness/color while AL's UI says it adapted
- After a known mesh issue or Z2M restart, bulbs not catching up until next sunrise/sunset window
- Inconsistent brightness across bulbs in the same fixture (one stuck, others adapted)

### 3.9 MQTT pre-staging for off-state bulbs

AL only sends commands to bulbs that are on. Off bulbs catch up via `intercept: true` when HA processes a `light.turn_on` call — AL hooks the call and adds the current brightness/color to the service data before it reaches the bulb.

This is good but not perfect:

1. **Z2M command translation.** Even when the intercepted call carries brightness/color, Z2M may translate it into multiple Zigbee commands (on, then level, then color) — causing a brief flash at the bulb's previous on-state before new values land.
2. **Turn-on paths that bypass HA entirely.** Zigbee bindings, physical wall switches that cut power, or any other source that doesn't go through `light.turn_on`. Intercept can't help here.

The pre-staging approach addresses both by publishing the current AL target values directly to the bulb via MQTT *while the bulb is off*. Combined with `execute_if_off: true` set on the bulb, Z2M stores these values without turning the bulb on. When any turn-on event occurs, the bulb powers up at the pre-staged values immediately.

Bulbs that are currently on are left alone — AL continues to adapt them normally, preserving manual control detection and smooth transitions.

The pre-staging automation triggers only on `brightness_pct` attribute changes — not both `brightness_pct` and `color_temp_mired`. Both values change in the same AL recalculation cycle and the payload sends both regardless of which attribute triggered, so triggering on one is sufficient. Brightness is chosen because it's the more perceptually noticeable change and ramps monotonically; color temperature can stay flat for stretches near solar noon where brightness still drifts.

The implementation procedure is in §7. Deployment status per fixture is in §11.

---

## 4. Settings Reference

All switches share these values unless noted in [§5 Per-Room Overrides](#5-per-room-overrides).

### 4.1 Brightness

| Setting | Value | Rationale |
|---|---|---|
| `min_brightness` | `60` | Evening floor before sleep mode. Tune down if wind-down feels too active. |
| `max_brightness` | `95` | Daytime ceiling. Never run lights at 100%. |
| `sleep_brightness` | `5` | Used when "Everyone Sleeping" automation triggers sleep mode. |

### 4.2 Color Temperature

| Setting | Value | Rationale |
|---|---|---|
| `min_color_temp` | `2000` | Warmest acceptable for daytime use. Hue's standard warmest. |
| `max_color_temp` | `5500` | Coolest setting at solar noon. 6500K reads as harsh in residential ceiling fixtures. |
| `sleep_color_temp` | `2000` | Matches `min_color_temp` — bulb sits at its warmest during sleep mode. |

### 4.3 Curve Shape

| Setting | Value | Rationale |
|---|---|---|
| `brightness_mode` | `tanh` | Smooth S-curve. Decouples ramp shape from sun elevation. |
| `brightness_mode_time_dark` | `1800` | 30 min before clamped sunrise / after clamped sunset. Pre-ramp tail. |
| `brightness_mode_time_light` | `5400` | 90 min after clamped sunrise / before clamped sunset. Defines when max is reached / when wind-down begins. |
| `prefer_rgb_color` | `false` | All bulbs are color-temperature-tunable, no full RGB. |

### 4.4 Schedule Clamps

| Setting | Value | Rationale |
|---|---|---|
| `min_sunrise_time` | `06:30` | Earliest the morning ramp event can be anchored. Prevents 5am ramps in summer. |
| `max_sunrise_time` | `07:30` | Latest the morning ramp event can be anchored. Ensures ramp is underway by 7am wake-up in winter. |
| `min_sunset_time` | `20:00` | Earliest evening wind-down can begin its ramp event. Overridden for Avery's room — see §5. |
| `max_sunset_time` | `21:00` | Latest evening wind-down anchor. Ensures fully warm/dim by ~21:30 year-round. |

### 4.5 Behavior

| Setting | Value | Rationale |
|---|---|---|
| `interval` | `90` | Seconds between adaptation cycles. Reasonable middle ground for Zigbee. |
| `transition` | `45` | Seconds per adaptation step. Smooth fades on Hue bulbs. |
| `initial_transition` | `1` | Seconds on first turn-on. Near-instant when manually flipped on. |
| `take_over_control` | `true` | Manual brightness/color changes pause AL until light is off/on cycle. |
| `adapt_only_on_bare_turn_on` | `true` | If `light.turn_on` is called with brightness/color specified (e.g., a scene), AL skips adaptation and marks the light as manually controlled. Bare turn-ons still adapt normally. |
| `skip_redundant_commands` | `true` | Skips adaptation commands when target state already equals recorded state. Reduces Zigbee traffic. See §3.8 for the Z2M state-sync caveat. |
| `detect_non_ha_changes` | `false` | Reduces false-positive manual-control flags. |
| `only_once` | `false` | Continuous adaptation throughout the day, not just at turn-on. |

---

## 5. Per-Room Overrides

| Light | Override | Reason |
|---|---|---|
| `light.avery_room_ceiling` | `min_sunset_time: 19:30`, `max_sunset_time: 20:00` | Avery's bedtime is ~20:30 weekdays (reading from 20:30, asleep ~21:00). Lights should be fully warm/dim before reading begins. |

All other settings on Avery's switch match the baseline. The morning ramp is shared because Avery wakes on the same schedule as the household.

---

## 6. Resulting Behavior

### 6.1 Morning (all rooms)

- **6:00–6:30 AM:** Lights at min brightness, warmest color temp.
- **6:30–7:30 AM:** Sunrise event fires somewhere in this window depending on actual sun position. Brightness ramp begins ~30 min before. By 7:00 AM, ramp is underway.
- **8:00–9:00 AM:** Brightness reaches max, color temp continues warming toward 5500K through morning.
- **Solar noon:** Coolest color temp.

### 6.2 Evening (adult rooms — Living Room Fan, Master Bedroom Fan, Office Ceiling)

- **18:30–19:30:** Wind-down begins as evening ramp approaches. Brightness still near max but starting to descend.
- **20:00–21:00:** Sunset event fires depending on season. Wind-down accelerates.
- **~21:30 (summer) / ~20:30 (winter):** Lights fully warm and dim to 60%.
- **Sleep mode trigger** ("Everyone Sleeping" automation): brightness drops to 5%, color temp to 2000K.

### 6.3 Evening (Avery's Room)

- **18:00–18:30:** Wind-down begins as evening ramp approaches.
- **19:30–20:00:** Sunset event fires. Wind-down accelerates.
- **~20:30:** Lights fully warm and dim to 60% — ready for reading.

---

## 7. Pre-Staging Implementation Procedure

Use this procedure to enable pre-staging (§3.9) on a fixture. The procedure is fixture-agnostic.

### 7.1 Prerequisites

Before starting on a fixture, confirm:

| Item | Why |
|---|---|
| Bulbs are paired to Z2M | The pre-staging mechanism uses Z2M's MQTT interface. |
| Bulbs support `execute_if_off` | Hue bulbs (White Ambiance, Essentials) all do. Functional test in §7.5 confirms per-fixture. |
| Fixture has an AL switch already configured | Per §3–§5 of this document — including `intercept: true`, `take_over_control: true`, and a sensible curve. |
| Bulbs are named per the HA naming standard | Entity IDs follow `light.[area]_[fixture]_bulb_[n]`. |
| Z2M friendly names are known | The MQTT topic uses the Z2M friendly name verbatim, including spaces and case. |

### 7.2 Information to Provide

To generate the MQTT commands (§7.3) and the automation YAML (§7.6) for a given fixture, the following information is required. Collect all of it before requesting artifacts — partial information will produce incorrect output.

| # | Information | How to find | Example |
|---|---|---|---|
| 1 | AL switch entity ID | Developer Tools → States, search for the AL switch | `switch.adaptive_lighting_office_ceiling_lights` |
| 2 | AL switch exposes `brightness_pct` and `color_temp_mired` attributes | Developer Tools → States → view the switch's attributes | Confirm both exist; if not, the template needs different attribute names |
| 3 | Bulb entity IDs (all of them in the fixture) | Settings → Devices & Services → Z2M → Devices, or HA Lights list | `light.office_ceiling_bulb_1`, `light.office_ceiling_bulb_2` |
| 4 | Z2M friendly names per bulb (exact match including case and spaces) | Z2M frontend → Devices → friendly name field | `Office Ceiling Bulb 1`, `Office Ceiling Bulb 2` |
| 5 | Fixture's human-readable name | For automation alias and description | `Office Ceiling` |
| 6 | Fixture's area | For HA UI assignment after creating automation | `Office` |

**Critical verification before generating artifacts:** confirm input #2. If the AL switch does not expose `brightness_pct` and `color_temp_mired` as attributes, the templates below will not work as-is — the automation triggers and Jinja templates need to be adjusted to use whatever attributes are exposed (e.g., `color_temp_kelvin` with a mired conversion).

### 7.3 Configure `execute_if_off` on Each Bulb

For every bulb in the fixture, run this in Developer Tools → Actions (YAML mode), substituting the Z2M friendly name:

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

These settings are not exposed in the Z2M "Settings (specific)" tab UI, but they apply correctly via MQTT. Confirmation comes from §7.4.

### 7.4 Verify the Settings Applied

Open the Z2M frontend → Devices → click on one of the fixture's bulbs. The reported device state JSON should now include:

```json
{
  "color_options": { "execute_if_off": true },
  "level_config": { "execute_if_off": true },
  "power_on_behavior": "previous"
}
```

If these don't appear, the publish in §7.3 was not accepted. Common causes: wrong Z2M friendly name in the topic, missing quotes around topics with spaces, bulb offline.

### 7.5 Functional Test

This proves the bulbs actually honor `execute_if_off` before committing to the automation.

1. **Disable AL for this fixture.** Turn off the main AL switch. This prevents AL's intercept from interfering with the test.
2. **Turn all bulbs in the fixture off.**
3. **For one bulb, publish a deliberate dim/warm payload via Developer Tools → Actions:**

   ```yaml
   action: mqtt.publish
   data:
     topic: "zigbee2mqtt/<Z2M FRIENDLY NAME>/set"
     payload: '{"state": null, "brightness": 50, "color_temp": 400}'
   ```

4. **Confirm the Z2M state reports the new values while bulb is off.** In the Z2M frontend, the device's reported state should show `brightness: 50`, `color_temp: 400`, `state: "OFF"`.
5. **Turn the bulb on** by any method (HA, physical switch, Apple Home).
6. **Observe the bulb:**
   - Powers up at ~20% brightness (50/254) and ~2500K (400 mireds) → success
   - Powers up at previous brightness/color → `execute_if_off` not working, do not proceed; investigate Z2M version, bulb firmware, and whether the §7.3 publish was accepted
7. **Re-enable AL** for the fixture by turning the main AL switch back on.

### 7.6 Create the Pre-Staging Automation

Use the template below. Substitute every `<PLACEHOLDER>` with the values gathered in §7.2.

**For each additional bulb in the fixture beyond two, duplicate one of the per-bulb `if/then` blocks inside the `parallel:` action, incrementing the bulb number in the alias and substituting the appropriate entity ID and Z2M friendly name.**

```yaml
alias: "AL Pre-Stage — <FIXTURE FRIENDLY NAME>"
description: >-
  Keeps <FIXTURE FRIENDLY NAME> bulbs pre-loaded with the current Adaptive Lighting
  brightness and color temperature whenever they are off. With execute_if_off enabled
  on the bulbs (set via direct MQTT publish), Z2M stores the values on the bulb without
  turning it on — so the next turn-on, from any source, lands at the correct adapted
  state instead of the last-on values.


  Solves the "flash to previous brightness/color before AL catches up" problem for
  turn-on paths that bypass HA's light.turn_on service: Zigbee bindings, physical power
  cycles, and any other on-event AL's intercept doesn't see.


  Triggered on attribute change of <AL SWITCH ENTITY ID> (brightness_pct only).
  Both brightness and color temperature values are sent in each publish, so triggering
  on a single attribute is sufficient. Brightness is chosen because it ramps
  monotonically and is the more perceptually noticeable change. Only publishes to
  bulbs that are currently off — bulbs that are on continue to be handled by Adaptive
  Lighting normally, preserving its manual-control detection and smooth transitions.

mode: single
max_exceeded: silent

trigger:
  - id: brightness_changed
    alias: "AL recalculated brightness_pct"
    platform: state
    entity_id: <AL SWITCH ENTITY ID>
    attribute: brightness_pct

variables:
  al_switch: <AL SWITCH ENTITY ID>

action:
  - alias: "Pre-stage to all currently-off bulbs in parallel"
    parallel:

      - alias: "Bulb 1 — pre-stage if currently off"
        if:
          - alias: "Bulb 1 is off"
            condition: state
            entity_id: <BULB 1 ENTITY ID>
            state: "off"
        then:
          - alias: "Publish current AL curve values to Bulb 1"
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/<BULB 1 Z2M FRIENDLY NAME>/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }

      - alias: "Bulb 2 — pre-stage if currently off"
        if:
          - alias: "Bulb 2 is off"
            condition: state
            entity_id: <BULB 2 ENTITY ID>
            state: "off"
        then:
          - alias: "Publish current AL curve values to Bulb 2"
            action: mqtt.publish
            data:
              topic: "zigbee2mqtt/<BULB 2 Z2M FRIENDLY NAME>/set"
              payload: >-
                {
                  "state": null,
                  "brightness": {{ ((state_attr(al_switch, 'brightness_pct') / 100) * 254) | round(0) | int }},
                  "color_temp": {{ state_attr(al_switch, 'color_temp_mired') | int }}
                }
```

**Notes on the template:**

- **`action:` vs `service:`** — Current Home Assistant uses `action:` in automation YAML for service calls. Older HA versions used `service:`. Both work for now, but `action:` is the preferred modern form and is used throughout this template.
- **Single trigger on `brightness_pct`.** Both brightness and color_temp values are pushed in every publish, so triggering on one attribute is sufficient. Brightness is chosen because it ramps monotonically and the change is more perceptually disruptive than color temperature.
- **Brightness conversion:** AL exposes `brightness_pct` (0–100). Z2M expects `brightness` (0–254). The Jinja math is `(pct / 100) * 254`, rounded.
- **Color temp:** AL exposes both `color_temp_kelvin` and `color_temp_mired`. Z2M expects mireds, so use mireds directly — no conversion needed.
- **`state: null`** — tells Z2M to update brightness/color without changing the bulb's on/off state. Critical for the pre-stage approach.
- **Mode `single`** with `max_exceeded: silent` — if a second trigger fires before the first completes (unlikely with the single-attribute trigger but possible), the second is silently discarded. Idempotent so no harm done.
- **Topic quoting** — Z2M friendly names with spaces require the topic to be wrapped in double quotes in YAML. If the friendly name has no spaces, quoting is optional but harmless.

After creating the automation in Home Assistant, set the following via the automation editor UI (these don't transfer through YAML):

- **Area:** the fixture's area
- **Category:** Lighting

### 7.7 Validate the Automation

After enabling, verify it's working:

1. **Last Triggered timestamp advances.** During an AL ramp window (morning ~6:30–9:30am or evening ~7:30–9:30pm), the automation should fire roughly every 90 seconds.
2. **Z2M shows updates to off bulbs.** Open the Z2M frontend and watch the device state for one of the fixture's bulbs. While the bulb is reported off, you should see `brightness` and `color_temp` updating over time as the AL curve progresses.
3. **Real-world turn-on test.** Turn the bulbs off in the evening. The next morning, when the AL curve has advanced (e.g., 7:30am), turn the bulbs on. They should power up at the morning ramp values, not at the previous evening's warm/dim values.

After successful validation, update §11 with the fixture's pre-staging deployment status.

---

## 8. Sleep Mode Integration

The "Everyone Sleeping" automation must call `switch.turn_on` on these entities (and `switch.turn_off` at wake):

- `switch.adaptive_lighting_sleep_mode_living_room_fan`
- `switch.adaptive_lighting_sleep_mode_master_bedroom_fan`
- `switch.adaptive_lighting_sleep_mode_office_ceiling`
- `switch.adaptive_lighting_sleep_mode_avery_room_ceiling`

Actual entity IDs may differ if AL switch names diverged from the standard during initial setup (e.g., `switch.adaptive_lighting_sleep_mode_office_ceiling_lights`). Verify in Developer Tools → States before editing the automation.

---

## 9. Tuning & Monitoring

### 9.1 Observation Targets

| What to watch | If wrong, change |
|---|---|
| Mornings: lights still too dim when waking at 7am | Shift `min_sunrise_time` earlier (e.g., 06:00) |
| Mornings: lights at max too late in the day | Shorten `brightness_mode_time_light` (e.g., 3600 = 60 min) |
| Adult evenings: dimming starts too early during dinner | Lengthen `brightness_mode_time_light` toward 7200 (2 hr) |
| Avery's room: wind-down too early during summer playtime | Push `min_sunset_time` to 19:45 or 20:00 |
| Wind-down feels too active before sleep mode | Drop `min_brightness` to 50 or 40 |

### 9.2 Curve Visualization

The [Adaptive Lighting Simulator](https://basnijholt.github.io/adaptive-lighting/) accepts these settings and plots the resulting curve. Useful for previewing tuning changes before applying them in HA.

---

## 10. Troubleshooting

### 10.1 AL Configuration

| Symptom | Likely Cause | Fix |
|---|---|---|
| Inconsistent brightness across bulbs in the same fixture | One bulb is "manually controlled" while others are adapting | Toggle the bulb off/on, or call `adaptive_lighting.set_manual_control` to clear the flag |
| Lights stay bright/cool too late in the evening | `max_sunset_time` is later than intended, or `brightness_mode_time_light` is too short | Verify §4.3 and §4.4 against this doc |
| Lights warm/dim too early in the winter evening | `min_sunset_time` is too early | Push `min_sunset_time` later (e.g., 20:30) |
| Sleep mode not triggering | "Everyone Sleeping" automation references wrong entity IDs | Verify entity IDs in §8 against Developer Tools → States |
| Specific bulb visibly stuck at wrong brightness/color | `skip_redundant_commands` is skipping due to stale HA state | Disable `skip_redundant_commands` on that switch and re-enable when the Zigbee mesh issue is resolved |

### 10.2 Pre-Staging

| Symptom | Likely Cause | Fix |
|---|---|---|
| Functional test fails — bulb powers up at old values | Bulb didn't accept `execute_if_off`, or Z2M didn't pass it through | Re-run §7.3; verify the Z2M state response shows `execute_if_off: true` in both `color_options` and `level_config` |
| Automation never triggers | Wrong AL switch entity ID, or wrong attribute name | Open Developer Tools → States → AL switch; verify entity ID and `brightness_pct` attribute exist |
| Automation triggers but Z2M shows no publishes | Wrong topic (Z2M friendly name typo, missing quotes around topics with spaces) | Compare topic against Z2M frontend's exact friendly name; quote topics containing spaces |
| Bulb still flashes on turn-on after deployment | Pre-staged values are stale (e.g., AL was off during the last recalc) | Verify AL is enabled for this fixture; check Last Triggered on the automation |
| One bulb adapts correctly, another doesn't | Only one bulb has `execute_if_off` set | Re-run §7.3 for the affected bulb; verify via Z2M state |
| Pre-staging conflicts with manual control | Automation publishing to bulbs that are actually on | Check the `condition: state` for each bulb — should be `state: "off"`. The automation should never publish to on bulbs. |
| AL switch attributes are named differently than expected | Older AL version or custom config | Adjust trigger attribute name and the Jinja templates to use the actual attribute names exposed; convert units in the template if Kelvin is exposed instead of mired |

---

## 11. Quick Reference

| Light | min_sunset_time | max_sunset_time | Color temp range | Pre-Staging Deployed |
|---|---|---|---|---|
| `light.living_room_fan` | `20:00` | `21:00` | 2000–5500K | ⏳ Not yet |
| `light.master_bedroom_fan` | `20:00` | `21:00` | 2000–5500K | ⏳ Not yet |
| `light.office_ceiling` | `20:00` | `21:00` | 2000–5500K | ⏳ Trialing — automation deployed, observing |
| `light.avery_room_ceiling` | `19:30` | `20:00` | 2000–5500K | ⏳ Not yet |

All other settings on these switches match the baseline in §4. Update the "Pre-Staging Deployed" column as each fixture progresses through §7.

---

## 12. Related Documents

- `HA_Naming_Standard.md` — entity ID and friendly name conventions used throughout this document

---

## 13. Open Questions / Future Work

- **Color temperature curve shape under tanh mode.** The AL documentation is explicit about brightness curve shape under `tanh` but less clear about whether color temperature follows the same shape or its own. Worth observing whether the warming and dimming transitions feel synchronized in practice.
- **Weekend handling.** No weekend-specific schedule today. The 7am morning ramp applies all seven days. If 8:30am weekend wake feels jarring with lights already at max, consider an automation that adjusts `min_sunrise_time` / `max_sunrise_time` on weekends.
- **Other AL-managed lights.** This document covers the four fixtures listed in §1. Other AL-managed lights in the home are not currently covered. Worth either documenting them here or aligning them to this baseline.
- **Pre-staging network traffic at scale.** With N fixtures × M bulbs per fixture, pre-staging publishes N×M MQTT messages per AL recalc during ramp windows. Worth monitoring Z2M and Zigbee mesh health after each fixture is added in §7.
- **Whether pre-staging affects Hue bulb firmware update behavior.** Untested. Worth observing whether bulbs still accept OTA updates while pre-staged values are queued.
- **AL switch naming inconsistency.** The Office Ceiling AL switch is currently named `switch.adaptive_lighting_office_ceiling_lights` (friendly name "Office - Ceiling Lights"), which doesn't match the HA naming standard's drop-the-domain-suffix rule. Worth fixing along with any other inconsistent AL switch names.
