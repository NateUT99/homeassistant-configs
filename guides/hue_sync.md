# Hue Sync & TV Bias Lighting
*Last updated: May 2026*

The canonical document for the Living Room TV bias lighting and Hue Sync Box automation system.

---

## Overview

This document defines the TV bias lighting and Hue Sync Box automation system for the Living Room: five automations and two scripts that manage a Hue gradient lightstrip behind the LG OLED TV, control sync box profile selection (video vs. game) based on HDMI input and movie mode, and perform cleanup when the TV powers off. The system is designed around a single-owner state-converger for the bias light — eliminating multi-automation race conditions — with user-intent-driven sync activation and robust handling of LG WebOS's `unavailable` power-off state.

---

## Architecture

```
LG OLED TV ──────────────────────────────► TV Power Handler
                                             ├── powers Hue Sync Box on/off
                                             └── cleanup on TV-off

Hue Sync Box (light_sync) ───────────────► Bias Light Controller
Hue motion sensor ───────────────────────►   └── Hue gradient lightstrip
Hue Sync Box (light_sync) ───────────────► Mode Configurator
HDMI input ──────────────────────────────►   ├── Living Room Hue Sync (Video)
movie_mode helper ───────────────────────►   └── Living Room Hue Sync (Game)

light.living_room_tv_lights ─────────────► Bias Light Off-TV Guard

PS5 (PS5-MQTT) ──────────────────────────► PS5 Power Off Handler
```

### Component summary

| Component | Type | Responsibility | Mode |
|---|---|---|---|
| Living Room TV Power Handler | Automation | TV on/off transitions; cleanup on off | single |
| Living Room TV Bias Light Controller | Automation | Sole owner of the bias light during TV sessions | restart |
| Living Room Hue Sync Mode Configurator | Automation | Picks video/game profile; adjusts ceiling AL | restart |
| Living Room TV Bias Light Off-TV Guard | Automation | Catches manual bias turn-ons while TV is off | single |
| Living Room Hue Sync Stop on PS5 Power Off | Automation | Stops sync when PS5 powers off while syncing to PS5 | single |
| Living Room Hue Sync (Video) | Script | Configures sync box for video content | — |
| Living Room Hue Sync (Game) | Script | Configures sync box for game content | — |

### Trigger coverage matrix

| Trigger | TV Power Handler | Bias Controller | Mode Configurator | Off-TV Guard | PS5 Off Handler |
|---|---|---|---|---|---|
| `media_player.living_room_tv` → on/off | ✓ | ✓ | | | |
| `switch.living_room_sync_box_light_sync` on/off | | ✓ | ✓ | | |
| `select.living_room_sync_box_hdmi_input` change | | | ✓ | | |
| `input_boolean.movie_mode` change | | | ✓ | | |
| `sensor.living_room_motion_illuminance` threshold | | ✓ | | | |
| `light.living_room_tv_lights` → on | | | | ✓ | |
| `switch.living_room_ps5_power` → off | | | | | ✓ |

### Design decisions

#### 1. Single-owner state-converger for bias light

The bias light is owned by exactly one automation — the Bias Light Controller. Rather than reacting to "what just happened" with imperative steps, the controller reacts to "something changed that might affect the answer" and re-evaluates the full condition every time.

The invariant it maintains:

> Bias is **on** if and only if **TV is on** AND **light sync is off** AND **room is dim**.

Any trigger that affects any input to this invariant causes the controller to re-evaluate and converge to the correct state. This eliminates the failure mode where multiple automations reach into the bias light from different angles and race or contradict each other.

This is why the controller uses `mode: restart` — if multiple state changes fire in quick succession, each new trigger immediately re-evaluates from current state instead of queuing or dropping.

#### 2. Sync switch as the intent surface

`switch.living_room_sync_box_light_sync` (the sync box's native sync toggle) is the user's intent signal:

- **Sync off** = "I'm just watching, no sync." Bias light operates normally based on room illuminance.
- **Sync on** = "Sync this content." The Mode Configurator picks the right profile based on input and `movie_mode` and applies it.

Using the existing switch as the intent surface (rather than a new `input_boolean`) means there's only one control. Toggles from the Hue app, HA, voice, or the Mode Configurator's actions all flow through the same state and trigger the same logic.

#### 3. Dual-threshold illuminance with hysteresis

"Room is dim" comes from `sensor.living_room_motion_illuminance` (the Hue motion sensor's lux reading) using dual thresholds:

- Below **15 lux** → room is dim, bias turns on
- Above **25 lux** → room is lit, bias turns off
- Between 15–25 lux (deadband) → bias holds its current state

The deadband prevents flapping. With a single threshold and the bias strip itself elevating the room's lux reading, the system would oscillate: bias on → room reads above threshold → bias off → room reads below threshold → bias on.

#### 4. 6500K hardcoded white point for bias lighting

The bias strip is always 6500K when on. 6500K matches the D65 white point that TVs are calibrated to. Bias lighting works by giving the eyes a neutral reference behind the screen so on-screen colors look accurate. Warming the strip in the evening (as AL would do) would shift color perception of content — defeating the purpose.

Brightness is a separate matter: currently 40% (tuned May 2026). Brightness adaptation by time of day could be added if needed, but color temperature stays fixed.

#### 5. Movie mode as profile override

`input_boolean.movie_mode` is a manually-toggled override that forces the video profile regardless of HDMI input. The PS5 is used for both gaming and 4K Blu-ray movies, so input alone is an ambiguous signal:

1. If `input_boolean.movie_mode` is on → **video profile** (overrides input)
2. Else if HDMI input is **Apple TV** → video profile
3. Else if HDMI input is **Playstation 5** → game profile

Movie mode is also referenced by other automations in the home, so it's a general-purpose intent flag rather than a TV-specific helper. It is cleared automatically when the TV turns off.

#### 6. Mode Configurator re-evaluates on three event types

The Mode Configurator runs when:

- **Sync just turned on** → apply profile based on current state
- **Input changed while sync is on** → re-apply profile for the new input
- **Movie mode changed while sync is on** → re-apply profile

This enables "switch profile mid-session" — for example, gaming on PS5 (game profile applied), then deciding to watch a 4K Blu-ray, enabling `movie_mode`, and the configurator re-picks and applies the video profile without needing to toggle sync off and back on. When sync is off, none of these events do anything — the user hasn't expressed intent for sync.

#### 7. Separate off-TV bias guard

The Bias Light Off-TV Guard is a small, single-purpose automation that turns the bias light back off if it's turned on while the TV is off. This catches accidental manual turn-ons (Hue app, voice command, etc.).

This is deliberately *not* part of the main Bias Light Controller. An earlier design had this logic in the controller as a `manual_on_guard` trigger, but that created a feedback loop: the bias strip illuminating the motion sensor caused brief illuminance spikes above the threshold, which the controller (re-evaluating because of its own action) interpreted as "room is now lit, turn bias off." Splitting the guard out eliminates the loop because the guard only acts when the TV is off, which is never true during a TV session.

#### 8. PS5 power state as auxiliary signal

`switch.living_room_ps5_power` (via the PS5-MQTT integration) exposes the PS5's actual power state. When the PS5 turns off while sync is active and the PS5 is the selected input, sync is stopped automatically. Without this, sync would keep running pointing at a black HDMI signal until manually stopped or until the TV turns off.

#### 9. LG WebOS state handling

LG WebOS TVs report `unavailable` rather than `off` when powered off — the network interface drops with power and the integration loses contact. Any condition or trigger that checks "is the TV off" must handle both states:

- **Triggers:** use `to: ["off", "unavailable"]` or `from: "on"` rather than just `to: "off"`
- **Conditions:** use `state: ["off", "unavailable"]` lists

The TV Power Handler triggers on both `from: "off"` and `from: "unavailable"` for TV-on. The Off-TV Guard accepts both states in its condition. Future automations that need to know "is the TV off" should use the same pattern.

#### 10. Sync release timing delay

The Bias Light Controller's "ON" branch includes a 1-second delay before turning the strip on. This handles the brief window after sync stops where the Hue Sync Box is releasing control of the strip. Without the delay, `light.turn_on` could land before or during the sync box's release sequence and get overridden.

#### 11. Restrictive triggers on the Bias Light Controller

The Bias Light Controller's triggers fire only on actual `on` state transitions (`from: "on"` or `to: "on"`), not on attribute updates. `media_player` entities update attributes frequently (volume, currently playing track, source, etc.) and would otherwise trigger the controller on every minor state change. Filtering to actual on/off transitions keeps the controller idle most of the time.

### Configuration Reference

#### Bias Light

| Setting | Value | Rationale |
|---|---|---|
| `brightness_pct` | `40` | Tuned May 2026. 25% was too subtle; 40% is visible without being distracting during dark scenes. |
| `color_temp_kelvin` | `6500` | D65 white point. Matches TV calibration. Not subject to AL. |

#### Illuminance Thresholds

| Setting | Value | Rationale |
|---|---|---|
| Dim threshold | `< 15 lux` | Below this, bias turns on. |
| Lit threshold | `> 25 lux` | Above this, bias turns off. |
| Deadband | `15–25 lux` | Bias holds current state. Prevents flapping. |

#### Video Profile

Used for Apple TV input, or any input when `movie_mode` is on.

| Setting | Value | Rationale |
|---|---|---|
| Sync box `brightness` | `50` | Conservative — bright enough to be visible, low enough not to distract during dark scenes. |
| Sync box `intensity` | `high` | Smooth transitions appropriate to film. |
| Sync box `mode` | `video` | Sync box's video processing mode. |
| Ceiling AL `min_brightness` | `25` | Low floor for evening viewing. |
| Ceiling AL `max_brightness` | `50` | Caps ceiling brightness so it doesn't compete with content. |

#### Game Profile

Used for PS5 input when `movie_mode` is off.

| Setting | Value | Rationale |
|---|---|---|
| Sync box `brightness` | `85` | Punchy — matches the dynamic content of action games. |
| Sync box `intensity` | `intense` | Rapid, saturated shifts for gaming responsiveness. |
| Sync box `mode` | `game` | Sync box's low-latency game processing mode. |
| Ceiling AL `min_brightness` | `5` | Deep dimming for immersive gaming. |
| Ceiling AL `max_brightness` | `10` | Very low ceiling to keep room dark. |

#### Ceiling AL Restoration (sync off)

| Setting | Value | Rationale |
|---|---|---|
| `min_brightness` | `60` | Matches the `switch.adaptive_lighting_standard` baseline. |
| `max_brightness` | `95` | Matches the `switch.adaptive_lighting_standard` baseline. |

These are passed to `adaptive_lighting.change_switch_settings` with `use_defaults: current` so other AL settings (color temp, schedule, curve) are preserved.

> **Coordinated change:** The `min_brightness` (60) and `max_brightness` (95) values mirror the baseline configuration of `switch.adaptive_lighting_standard` (**Settings → Devices & Services → Adaptive Lighting → Standard → Configure**). If that baseline changes, update both values here and in the Mode Configurator YAML below.

### Profile selection logic

When the Mode Configurator runs (sync started, input changed, or `movie_mode` changed — and sync is on), it picks a profile:

```
if input_boolean.movie_mode == on:
    profile = video
elif HDMI input == Apple TV:
    profile = video
elif HDMI input == Playstation 5:
    profile = game
else:
    no action  # unknown input — do nothing rather than pick the wrong profile
```

---

## Prerequisites

Before creating the automations, verify all of the following exist and are correctly named:

| Item | Notes |
|---|---|
| LG WebOS integration installed and `media_player.living_room_tv` exists | Default integration; configured via **Settings → Devices & Services** |
| Philips Hue Play HDMI Sync Box integration installed | Provides `switch.living_room_sync_box_power`, `switch.living_room_sync_box_light_sync`, `select.living_room_sync_box_hdmi_input` |
| `light.living_room_tv_lights` exists | Hue gradient lightstrip, exposed via the Hue integration (not via the sync box) |
| Hue motion sensor exists with illuminance entity | `sensor.living_room_motion_illuminance` |
| Adaptive Lighting installed and Standard switch exists | `switch.adaptive_lighting_standard` — see `guides/adaptive_lighting.md` |
| PS5-MQTT integration installed | Provides `switch.living_room_ps5_power`. If not yet installed, automation #5 can be skipped initially. |
| `input_boolean.movie_mode` helper exists | Created via **Settings → Devices & Services → Helpers → Toggle** |
| Sonos integration with Night Sound and Speech Enhancement switches | `switch.living_room_sonos_night_sound`, `switch.living_room_sonos_speech_enhancement` |
| HDMI input names match exactly | The Mode Configurator references `Apple TV` and `Playstation 5` as strings. Verify in `select.living_room_sync_box_hdmi_input` attributes. |
| Hue Sync Box device ID known | Required by the video and game scripts. Find in **Settings → Devices & Services → Hue Play HDMI Sync Box → device** (visible in the URL or via Developer Tools → Devices). Current value: `a99ddac081e83072ec97e2d8b8d3c6ba` |

---

## Implementation Steps

Each automation below is paste-ready into the HA automation editor (YAML mode). After creating, set the following via the UI:

- **Area:** Living Room
- **Category:** Lighting

Enable in this order to make troubleshooting easier:

1. Both scripts first (no triggers, safe to have idle)
2. Living Room TV Power Handler — verify TV on/off cleanup works
3. Living Room TV Bias Light Controller — verify bias responds to TV state and room dimness
4. Living Room TV Bias Light Off-TV Guard — verify off-TV protection works
5. Living Room Hue Sync Mode Configurator — verify sync profile selection works
6. Living Room Hue Sync Stop on PS5 Power Off — verify PS5 off triggers sync stop (requires PS5-MQTT)

### Automation 1: Living Room TV Power Handler

```yaml
alias: Living Room TV Power Handler
description: >-
  Owns TV power transitions. On TV-on, powers up the Hue Sync Box. On TV-off,
  cleans up: powers down the sync box, turns off light sync, clears
  movie_mode, and disables Sonos Night Sound / Speech Enhancement if active.
  Bias lighting is handled by the Bias Light Controller automation, not here.

  LG WebOS TVs report "unavailable" rather than "off" when powered off
  (the network interface drops with power), so both states are treated
  as "TV is off."
triggers:
  - trigger: state
    entity_id: media_player.living_room_tv
    from: "off"
    to: "on"
    id: tv_on
  - trigger: state
    entity_id: media_player.living_room_tv
    from: "unavailable"
    to: "on"
    id: tv_on
  - trigger: state
    entity_id: media_player.living_room_tv
    from: "on"
    to:
      - "off"
      - "unavailable"
    id: tv_off
conditions: []
actions:
  - choose:
      - alias: TV turned on
        conditions:
          - condition: trigger
            id: tv_on
        sequence:
          - alias: Power on the Hue Sync Box
            action: switch.turn_on
            target:
              entity_id: switch.living_room_sync_box_power
      - alias: TV turned off
        conditions:
          - condition: trigger
            id: tv_off
        sequence:
          - alias: Turn off light sync (resets intent for next session)
            action: switch.turn_off
            target:
              entity_id: switch.living_room_sync_box_light_sync
          - alias: Power off the Hue Sync Box
            action: switch.turn_off
            target:
              entity_id: switch.living_room_sync_box_power
          - alias: Clear movie mode
            action: input_boolean.turn_off
            target:
              entity_id: input_boolean.movie_mode
          - alias: Disable Sonos Night Sound and Speech Enhancement
            action: switch.turn_off
            target:
              entity_id:
                - switch.living_room_sonos_night_sound
                - switch.living_room_sonos_speech_enhancement
mode: single
```

### Automation 2: Living Room TV Bias Light Controller

```yaml
alias: Living Room TV Bias Light Controller
description: >-
  Sole owner of light.living_room_tv_lights during TV sessions. Maintains the
  invariant: bias is ON only when (TV is on) AND (Hue Sync light sync is off)
  AND (room is dim per sensor.living_room_motion_illuminance).

  Triggers on any input that affects this invariant and re-evaluates the
  whole condition every time, so it converges to the correct state regardless
  of which input changed.

  Room brightness uses dual thresholds for hysteresis: bias considers the
  room "dim" when illuminance is below 15 lux, and "lit" when above 25 lux.
  The 10-lux deadband prevents flapping when the sensor sits near a single
  threshold.

  A 1-second delay before turning bias on covers the brief window when the
  Hue Sync Box is releasing control of the strip after sync stops.

  Bias settings are inlined here: 40% brightness, 6500K (D65 white point to
  match TV reference white).

  Off-TV protection (catching manual bias turn-ons while TV is off) is
  handled by a separate automation, not this one. This avoids a feedback
  loop where the bias light's own state change re-triggers this controller
  and a brief illuminance spike from the strip itself causes a false
  "should be off" decision.
triggers:
  - trigger: state
    entity_id: media_player.living_room_tv
    from: "on"
    id: tv_off
  - trigger: state
    entity_id: media_player.living_room_tv
    to: "on"
    id: tv_on
  - trigger: state
    entity_id: switch.living_room_sync_box_light_sync
    from: "on"
    id: sync_off
  - trigger: state
    entity_id: switch.living_room_sync_box_light_sync
    to: "on"
    id: sync_on
  - trigger: numeric_state
    entity_id: sensor.living_room_motion_illuminance
    below: 15
    id: room_dim
  - trigger: numeric_state
    entity_id: sensor.living_room_motion_illuminance
    above: 25
    id: room_lit
conditions: []
actions:
  - choose:
      - alias: Bias should be ON (TV on, sync off, room dim)
        conditions:
          - condition: state
            entity_id: media_player.living_room_tv
            state: "on"
          - condition: state
            entity_id: switch.living_room_sync_box_light_sync
            state: "off"
          - condition: numeric_state
            entity_id: sensor.living_room_motion_illuminance
            below: 15
        sequence:
          - delay:
              seconds: 1
          - alias: Set bias light to 40% / 6500K
            action: light.turn_on
            target:
              entity_id: light.living_room_tv_lights
            data:
              brightness_pct: 40
              color_temp_kelvin: 6500
      - alias: Bias stays ON in deadband (already on, illuminance between 15 and 25)
        conditions:
          - condition: state
            entity_id: media_player.living_room_tv
            state: "on"
          - condition: state
            entity_id: switch.living_room_sync_box_light_sync
            state: "off"
          - condition: state
            entity_id: light.living_room_tv_lights
            state: "on"
          - condition: numeric_state
            entity_id: sensor.living_room_motion_illuminance
            below: 25
        sequence: []
    default:
      - alias: Bias should be OFF
        action: light.turn_off
        target:
          entity_id: light.living_room_tv_lights
mode: restart
```

### Automation 3: Living Room Hue Sync Mode Configurator

```yaml
alias: Living Room Hue Sync Mode Configurator
description: >-
  Configures the Hue Sync Box profile and ceiling Adaptive Lighting limits
  based on the current input and movie_mode flag. The sync switch itself is
  the user's intent signal: turning it on means "sync this content," and
  this automation picks the right profile.

  Triggers:
    - Sync switch turning on  -> apply profile, start syncing
    - Sync switch turning off -> restore ceiling AL limits
    - Input change (only if sync is on)  -> re-apply profile for new input
    - Movie mode change (only if sync is on) -> re-apply profile

  Profile selection rule:
    1. movie_mode on  -> video profile (overrides input)
    2. Apple TV input -> video profile
    3. PS5 input      -> game profile

  Profiles:
    - Video: brightness 50, intensity high, ceiling AL 25-50%
    - Game:  brightness 85, intensity intense, ceiling AL 5-10%

  This automation does NOT touch the bias light directly; the Bias Light
  Controller handles that via its sync switch trigger.
triggers:
  - trigger: state
    entity_id: switch.living_room_sync_box_light_sync
    from: "off"
    to: "on"
    id: sync_start
  - trigger: state
    entity_id: switch.living_room_sync_box_light_sync
    from: "on"
    to: "off"
    id: sync_stop
  - trigger: state
    entity_id: select.living_room_sync_box_hdmi_input
    id: input_change
  - trigger: state
    entity_id: input_boolean.movie_mode
    id: movie_mode_change
conditions: []
actions:
  - choose:
      - alias: Sync stopped - restore ceiling AL limits
        conditions:
          - condition: trigger
            id: sync_stop
        sequence:
          - alias: Restore ceiling AL limits for Standard (60-95%)
            action: adaptive_lighting.change_switch_settings
            data:
              use_defaults: current
              entity_id: switch.adaptive_lighting_standard
              min_brightness: 60
              max_brightness: 95
      - alias: Reconfigure profile (sync_start, or input/movie_mode change while sync is on)
        conditions:
          - condition: or
            conditions:
              - condition: trigger
                id: sync_start
              - and:
                  - condition: or
                    conditions:
                      - condition: trigger
                        id: input_change
                      - condition: trigger
                        id: movie_mode_change
                  - condition: state
                    entity_id: switch.living_room_sync_box_light_sync
                    state: "on"
        sequence:
          - choose:
              - alias: Movie mode on OR Apple TV input -> video profile
                conditions:
                  - condition: or
                    conditions:
                      - condition: state
                        entity_id: input_boolean.movie_mode
                        state: "on"
                      - condition: state
                        entity_id: select.living_room_sync_box_hdmi_input
                        state: Apple TV
                sequence:
                  - action: script.living_room_hue_sync_video
                  - alias: Ceiling AL limits for video (25-50%)
                    action: adaptive_lighting.change_switch_settings
                    data:
                      use_defaults: current
                      entity_id: switch.adaptive_lighting_standard
                      min_brightness: 25
                      max_brightness: 50
              - alias: PS5 input (movie_mode off) -> game profile
                conditions:
                  - condition: state
                    entity_id: select.living_room_sync_box_hdmi_input
                    state: Playstation 5
                sequence:
                  - action: script.living_room_hue_sync_game
                  - alias: Ceiling AL limits for game (5-10%)
                    action: adaptive_lighting.change_switch_settings
                    data:
                      use_defaults: current
                      entity_id: switch.adaptive_lighting_standard
                      min_brightness: 5
                      max_brightness: 10
mode: restart
```

### Automation 4: Living Room TV Bias Light Off-TV Guard

```yaml
alias: Living Room TV Bias Light Off-TV Guard
description: >-
  If the bias light turns on while the TV is off (or unavailable), turn it
  back off. Bias lighting has no off-TV use case, so this catches accidental
  manual turn-ons (Hue app, voice command, etc.) without involving the main
  Bias Light Controller.

  LG WebOS TVs report "unavailable" rather than "off" when powered off,
  so both states count as "TV is off" here.

  This is intentionally a separate automation from the Bias Light Controller
  so it cannot create a feedback loop with the controller's own actions.
  It only acts when the TV is off, so it never fires during TV sessions.
triggers:
  - trigger: state
    entity_id: light.living_room_tv_lights
    to: "on"
conditions:
  - condition: state
    entity_id: media_player.living_room_tv
    state:
      - "off"
      - "unavailable"
actions:
  - action: light.turn_off
    target:
      entity_id: light.living_room_tv_lights
mode: single
```

### Automation 5: Living Room Hue Sync Stop on PS5 Power Off

```yaml
alias: Living Room Hue Sync Stop on PS5 Power Off
description: >-
  When the PS5 powers off while sync is active and PS5 is the selected
  HDMI input, stop sync. Without this, sync keeps running pointing at a
  black HDMI signal until the user manually stops it or the TV turns off.

  Conditions ensure this only fires when sync is actually running against
  the PS5 - if the user is on Apple TV with sync on while the PS5 happens
  to power off in the background, this does nothing.
triggers:
  - trigger: state
    entity_id: switch.living_room_ps5_power
    from: "on"
    to: "off"
conditions:
  - condition: state
    entity_id: switch.living_room_sync_box_light_sync
    state: "on"
  - condition: state
    entity_id: select.living_room_sync_box_hdmi_input
    state: Playstation 5
actions:
  - action: switch.turn_off
    target:
      entity_id: switch.living_room_sync_box_light_sync
mode: single
```

### Script 1: Living Room Hue Sync (Video)

Both scripts call `huesyncbox.set_sync_state`. The `device_id` must match the actual device ID of the Hue Sync Box — find this in **Settings → Devices & Services → Hue Play HDMI Sync Box**. Replace the value below if rebuilding.

```yaml
alias: Living Room Hue Sync (Video)
description: >-
  Configures the Hue Sync Box for video content. Brightness 50, intensity
  high - smooth transitions suitable for film and TV. Used for Apple TV and
  for PS5 when input_boolean.movie_mode is on.
icon: mdi:movie-open
sequence:
  - action: huesyncbox.set_sync_state
    data:
      device_id: a99ddac081e83072ec97e2d8b8d3c6ba
      power: true
      sync: true
      mode: video
      intensity: high
      brightness: 50
```

### Script 2: Living Room Hue Sync (Game)

```yaml
alias: Living Room Hue Sync (Game)
description: >-
  Configures the Hue Sync Box for game content. Brightness 85, intensity
  intense - rapid, saturated color shifts for gaming responsiveness. Used
  for PS5 when input_boolean.movie_mode is off.
icon: mdi:controller
sequence:
  - action: huesyncbox.set_sync_state
    data:
      device_id: a99ddac081e83072ec97e2d8b8d3c6ba
      power: true
      sync: true
      mode: game
      intensity: intense
      brightness: 85
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bias doesn't turn on after sync stops | Sync release timing race — Hue Sync Box still releasing control of the strip | Verify the 1-second delay is present in the Bias Light Controller's "ON" branch |
| Bias turns on then immediately off | Feedback loop from `light.living_room_tv_lights` trigger placed in the wrong automation | Verify the Bias Light Controller does **not** trigger on `light.living_room_tv_lights` state changes — that trigger belongs only in the Off-TV Guard |
| Ceiling lights brighten unexpectedly mid-session | PS5 HDMI handshake drop briefly disabling sync, triggering the Mode Configurator's sync-off branch | Known issue — no fix currently implemented; observe frequency before deciding whether to suppress |
| Sync stays on after PS5 powers off | PS5-MQTT integration not reporting state correctly | Verify `switch.living_room_ps5_power` in Developer Tools → States; check PS5-MQTT addon logs |
| TV-off cleanup doesn't fire | TV went to `unavailable` instead of `off`, and the trigger doesn't accept both | Verify TV Power Handler's `tv_off` trigger includes both `"off"` and `"unavailable"` in the `to:` list |
| Bias light turns on briefly when TV turns off | Race: TV-off cleanup turns off sync, Bias Controller sees sync-off and briefly turns bias on before TV state propagates | Acceptable — bias is on for under a second. Could be tuned by reordering actions in TV Power Handler. |
| Profile doesn't switch when toggling `movie_mode` mid-session | Sync is off — Mode Configurator only acts on `movie_mode` change when sync is on | Enable sync first, then toggle `movie_mode` |
| Game profile applies when watching a PS5 movie | `input_boolean.movie_mode` was not enabled | Enable `movie_mode`; Mode Configurator will switch profile immediately |
| Sync auto-starts when changing inputs | Expectation from a previous version of this system that auto-started sync on input change | This was reverted — sync is intent-driven now. The user must opt in via the sync switch. |

---

## Related HA Config

| Artifact | Entity ID | Type |
|---|---|---|
| Living Room TV Power Handler | `automation.living_room_tv_power_handler` | Automation |
| Living Room TV Bias Light Controller | `automation.living_room_tv_bias_light_controller` | Automation |
| Living Room Hue Sync Mode Configurator | `automation.living_room_hue_sync_mode_configurator` | Automation |
| Living Room TV Bias Light Off-TV Guard | `automation.living_room_tv_bias_light_off_tv_guard` | Automation |
| Living Room Hue Sync Stop on PS5 Power Off | `automation.living_room_hue_sync_stop_on_ps5_power_off` | Automation |
| Living Room Hue Sync (Video) | `script.living_room_hue_sync_video` | Script |
| Living Room Hue Sync (Game) | `script.living_room_hue_sync_game` | Script |

---

## Related Files

No on-disk files are created or modified by this integration. All artifacts live in HA.

---

## Related Documents

- `standards/naming.md` — entity ID and friendly name conventions used throughout this document
- `guides/adaptive_lighting.md` — the AL configuration this system manipulates via `adaptive_lighting.change_switch_settings`; the 60–95% ceiling restoration values must track AL Standard's baseline
