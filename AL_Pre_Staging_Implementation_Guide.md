# Adaptive Lighting Pre-Staging — Implementation Guide
*Version 1.1 — May 2026*

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.1 | May 2026 | Added §4.1 information-to-provide checklist. Expanded §4.5 automation template to show explicit multi-bulb example. Noted `action:` vs `service:` terminology. Removed status tracker (not part of the generic procedure). |
| 1.0 | May 2026 | Initial release — procedure for enabling pre-staging on additional AL fixtures |

---

## 1. Purpose

This guide documents the procedure for enabling Adaptive Lighting (AL) pre-staging on a fixture. Pre-staging eliminates the "flash to previous brightness/color" that occurs when a bulb is turned on before AL has a chance to adapt it.

It is a companion to the `Adaptive_Lighting_Primary_Bulbs.md` design doc, which covers the AL configuration itself.

This document is written to be self-contained: given the inputs listed in §4.1, the MQTT commands in §4.2 and the automation YAML in §4.5 can be generated mechanically without additional context.

---

## 2. How It Works

Adaptive Lighting maintains a continuously-updating set of target brightness and color temperature values on its switch entity (`brightness_pct`, `color_temp_mired`) — even when the lights it controls are off. AL itself only sends commands to lights that are on; off lights catch up via `intercept: true` when the next `light.turn_on` call is processed by Home Assistant.

The flash problem occurs in two scenarios:

1. **HA-mediated turn-on with `intercept`** — The intercepted call carries the right brightness/color, but Z2M may translate this into multiple Zigbee commands (on, then level, then color), causing a brief flash at the bulb's previous on-state before the new values land.
2. **Turn-on paths that bypass HA entirely** — Zigbee bindings between switches and bulbs, physical wall switches that cut power, or any other source that doesn't go through `light.turn_on`. AL's intercept can't help here.

The pre-staging approach addresses both by publishing the current AL target values directly to the bulb via MQTT *while the bulb is off*. Combined with the bulb's `execute_if_off: true` flag, Z2M stores these values on the bulb without turning it on. When any turn-on event occurs, the bulb powers up at the pre-staged values immediately.

Bulbs that are currently on are left alone — AL continues to adapt them normally, preserving its `take_over_control`, `adapt_only_on_bare_turn_on`, and smooth transition behaviors.

---

## 3. Prerequisites

Before starting on a fixture, confirm:

| Item | Why |
|---|---|
| Bulbs are paired to Z2M (not Hue bridge) | The pre-staging mechanism uses Z2M's MQTT interface. Hue-bridge-paired bulbs would need a different approach. |
| Bulbs support `execute_if_off` | Hue bulbs (White Ambiance, Essentials) all do. Functional test in §4.4 confirms per-fixture. |
| Fixture has an AL switch already configured | Per the AL primary bulbs design doc — including `intercept: true`, `take_over_control: true`, and a sensible curve. |
| Bulbs are named per the HA naming standard | Entity IDs follow `light.[area]_[fixture]_bulb_[n]`. |
| Z2M friendly names are known | The MQTT topic uses the Z2M friendly name verbatim, including spaces and case. Verify in the Z2M frontend before building the automation. |

---

## 4. Implementation Procedure

For each fixture you want to enable pre-staging on, work through §4.1 through §4.6 in order.

### 4.1 Information to Provide

To generate the MQTT commands (§4.2) and the automation YAML (§4.5) for a given fixture, the following information is required. Collect all of it before requesting artifacts — partial information will produce incorrect output.

| # | Information | How to find | Example |
|---|---|---|---|
| 1 | AL switch entity ID | Developer Tools → States, search for the AL switch | `switch.adaptive_lighting_office_ceiling_lights` |
| 2 | AL switch exposes `brightness_pct` and `color_temp_mired` attributes | Developer Tools → States → view the switch's attributes | Confirm both exist; if not, the template needs different attribute names |
| 3 | Bulb entity IDs (all of them in the fixture) | Settings → Devices & Services → Z2M → Devices, or HA Lights list | `light.office_ceiling_bulb_1`, `light.office_ceiling_bulb_2` |
| 4 | Z2M friendly names per bulb (exact match including case and spaces) | Z2M frontend → Devices → friendly name field | `Office Ceiling Bulb 1`, `Office Ceiling Bulb 2` |
| 5 | Fixture's human-readable name | For automation alias and description | `Office Ceiling` |
| 6 | Fixture's area | For HA UI assignment after creating automation | `Office` |

**Critical verification before generating artifacts:** confirm input #2. If the AL switch does not expose `brightness_pct` and `color_temp_mired` as attributes, the templates below will not work as-is and the automation triggers and templates need to be adjusted to use whatever attributes are exposed (e.g., `color_temp_kelvin` with a mired conversion in the Jinja template).

### 4.2 Configure `execute_if_off` on Each Bulb

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

These settings are not exposed in the Z2M "Settings (specific)" tab UI, but they apply correctly via MQTT. Confirmation comes from the functional test in §4.4.

### 4.3 Verify the Settings Applied

Open the Z2M frontend → Devices → click on one of the fixture's bulbs. The reported device state JSON should now include:

```json
{
  "color_options": { "execute_if_off": true },
  "level_config": { "execute_if_off": true },
  "power_on_behavior": "previous"
}
```

If these don't appear, the publish in §4.2 was not accepted. Common causes: wrong Z2M friendly name in the topic, missing quotes around topics with spaces, bulb offline.

### 4.4 Functional Test

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
   - Powers up at previous brightness/color → `execute_if_off` not working, do not proceed; investigate Z2M version, bulb firmware, and whether the §4.2 publish was accepted
7. **Re-enable AL** for the fixture by turning the main AL switch back on.

### 4.5 Create the Pre-Staging Automation

Use the template below. Substitute every `<PLACEHOLDER>` with the values gathered in §4.1.

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


  Triggered on attribute change of <AL SWITCH ENTITY ID>
  (brightness_pct, color_temp_mired). Only publishes to bulbs that are currently off —
  bulbs that are on continue to be handled by Adaptive Lighting normally, preserving
  its manual-control detection and smooth transitions.

mode: single
max_exceeded: silent

trigger:
  - id: brightness_changed
    alias: "AL recalculated brightness_pct"
    platform: state
    entity_id: <AL SWITCH ENTITY ID>
    attribute: brightness_pct
  - id: color_temp_changed
    alias: "AL recalculated color_temp_mired"
    platform: state
    entity_id: <AL SWITCH ENTITY ID>
    attribute: color_temp_mired

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
- **Brightness conversion:** AL exposes `brightness_pct` (0–100). Z2M expects `brightness` (0–254). The Jinja math is `(pct / 100) * 254`, rounded.
- **Color temp:** AL exposes both `color_temp_kelvin` and `color_temp_mired`. Z2M expects mireds, so use mireds directly — no conversion needed.
- **`state: null`** — tells Z2M to update brightness/color without changing the bulb's on/off state. Critical for the pre-stage approach.
- **Mode `single`** with `max_exceeded: silent` — if both triggers fire near-simultaneously (brightness and color changed in the same AL recalc), the second is silently discarded. Idempotent so no harm done.
- **Topic quoting** — Z2M friendly names with spaces require the topic to be wrapped in double quotes in YAML. If the friendly name has no spaces, quoting is optional but harmless.

After creating the automation in Home Assistant, set the following via the automation editor UI (these don't transfer through YAML):

- **Area:** the fixture's area
- **Category:** Lighting

### 4.6 Validate the Automation

After enabling, verify it's working:

1. **Last Triggered timestamp advances.** During an AL ramp window (morning ~6:30–9:30am or evening ~7:30–9:30pm), the automation should fire roughly every 90 seconds.
2. **Z2M shows updates to off bulbs.** Open the Z2M frontend and watch the device state for one of the fixture's bulbs. While the bulb is reported off, you should see `brightness` and `color_temp` updating over time as the AL curve progresses.
3. **Real-world turn-on test.** Turn the bulbs off in the evening. The next morning, when the AL curve has advanced (e.g., 7:30am), turn the bulbs on. They should power up at the morning ramp values, not at the previous evening's warm/dim values.

---

## 5. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Functional test fails — bulb powers up at old values | Bulb didn't accept `execute_if_off`, or Z2M didn't pass it through | Re-run §4.2; verify the Z2M state response shows `execute_if_off: true` in `color_options` and `level_config` |
| Automation never triggers | Wrong AL switch entity ID, or wrong attribute names | Open Developer Tools → States → AL switch; verify entity ID and attribute names match the trigger config |
| Automation triggers but Z2M shows no publishes | Wrong topic (Z2M friendly name typo, missing quotes around topics with spaces) | Compare topic against Z2M frontend's exact friendly name; quote topics containing spaces |
| Bulb still flashes on turn-on after deployment | Pre-staged values are stale (e.g., AL was off during the last recalc) | Verify AL is enabled for this fixture; check Last Triggered on the automation |
| One bulb adapts correctly, another doesn't | Only one bulb has `execute_if_off` set | Re-run §4.2 for the affected bulb; verify via Z2M state |
| Pre-staging conflicts with manual control | Automation publishing to bulbs that are actually on | Check the `condition: state` for each bulb — should be `state: "off"`. The automation should never publish to on bulbs. |
| AL switch attributes are named differently than expected | Older AL version or custom config | Adjust trigger attribute names and the Jinja templates to use the actual attribute names exposed; convert units in the template if Kelvin is exposed instead of mired |

---

## 6. Related Documents

- `Adaptive_Lighting_Primary_Bulbs.md` — AL configuration design and rationale for the four primary fixtures
- `HA_Naming_Standard.md` — entity ID and friendly name conventions

---

## 7. Open Questions / Future Work

- **Whether to enable for non-primary AL fixtures.** This guide is fixture-agnostic but the AL primary bulbs design doc only covers the four primary fixtures. Non-primary AL-managed lights would benefit from a similar evaluation before enabling.
- **Network traffic at scale.** At N fixtures × M bulbs per fixture, the automation publishes N×M MQTT messages per AL recalc during ramp windows. Worth monitoring Z2M and Zigbee mesh health after each fixture is added.
- **Whether pre-staging affects Hue bulb firmware update behavior.** Untested. Worth observing whether bulbs still accept OTA updates while pre-staged values are queued.
