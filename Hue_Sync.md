# Hue Sync & TV Bias Lighting
*Version 1.0 — May 2026*

The canonical document for the Living Room TV bias lighting and Hue Sync Box automation system. Covers the design and rationale for how the system behaves, the components involved, and the operational concerns around running it day-to-day.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.0 | May 2026 | Initial document |

---

## 1. Purpose & Scope

This document defines the Hue Sync and TV bias lighting setup for the Living Room. It is intended as the single source of truth for:

1. **Design and configuration of the bias lighting system** — including the illuminance-driven on/off logic, the 6500K hardcoded white point, and the manual-on guard.
2. **Design and configuration of the Hue Sync Box integration** — including profile selection (video vs. game), input-driven and movie-mode-driven re-evaluation, and ceiling Adaptive Lighting adjustments.
3. **Cleanup behavior** — how the system returns to a clean state when the TV turns off or the PS5 powers down.

Audience: future-me and AI assistants helping future-me. The document is written to be self-contained for both: a fresh reader (human or AI) should be able to understand what is configured and why.

The hardware and entities currently covered by this configuration:

- LG 65" OLED TV (`media_player.living_room_tv`)
- Hue Sync Box (Gen 2) (`switch.living_room_sync_box_power`, `switch.living_room_sync_box_light_sync`, `select.living_room_sync_box_hdmi_input`)
- Hue gradient lightstrip behind TV (`light.living_room_tv_lights`)
- Apple TV 4K (Apple TV input)
- Sony PlayStation 5 (Playstation 5 input, `switch.living_room_ps5_power` via PS5-MQTT)
- Hue motion sensor in living room (`sensor.living_room_motion_illuminance`)
- Living Room ceiling fan lights with Adaptive Lighting (`switch.adaptive_lighting_living_room_ceiling_lights`)
- Living Room Sonos system (`switch.living_room_sonos_night_sound`, `switch.living_room_sonos_speech_enhancement`)
- Movie mode helper (`input_boolean.movie_mode`)

---

## 2. Goals

1. **Bias lighting that disappears when not needed.** Bias is on only during TV sessions, only when the room is dim, and only when not actively syncing. Bright rooms suppress it. The TV being off suppresses it. Sync running suppresses it.
2. **No auto-sync surprises during casual viewing.** Turning on the TV or switching inputs does not automatically start sync. The user opts in via the sync switch.
3. **Profile-appropriate sync behavior.** Video content gets smooth high-intensity sync at modest brightness; gaming gets rapid intense sync at high brightness; ceiling lights dim more aggressively for gaming than for video.
4. **Clean state transitions.** Turning the TV off resets the system to a known baseline. Each new TV session starts fresh.
5. **Robust to device-driven state changes.** PS5 power state, HDMI input changes, and LG WebOS network behavior are all signals the system understands.
6. **Single ownership of contested entities.** The bias light has exactly one automation that controls it during TV sessions. No two automations fight.

---

## 3. Core Design Decisions

### 3.1 Single-owner state-converger for bias light

The bias light is owned by exactly one automation — the **Bias Light Controller**. Rather than reacting to "what just happened" with imperative steps, the controller reacts to "something changed that might affect the answer" and re-evaluates the full condition every time.

The invariant it maintains:

> Bias is **on** if and only if **TV is on** AND **light sync is off** AND **room is dim**.

Any trigger that affects any input to this invariant causes the controller to re-evaluate and converge to the correct state. This eliminates the previous design's failure mode where three different automations all reached into the bias light from different angles and could race or contradict each other.

This is why the controller uses `mode: restart` — if multiple state changes fire in quick succession (TV on → room sensor flips → sync starts), each new trigger immediately re-evaluates from current state instead of queuing or dropping.

### 3.2 Sync switch as the intent surface

`switch.living_room_sync_box_light_sync` (the sync box's native sync toggle) is the user's intent signal:

- **Sync off** = "I'm just watching, no sync." Bias light operates normally based on room illuminance.
- **Sync on** = "Sync this content." The Mode Configurator picks the right profile based on input + movie_mode and applies it.

Using the existing switch as the intent surface (rather than a new `input_boolean`) means there's only one control. Toggles from the Hue app, HA, voice, or the Mode Configurator's actions all flow through the same state and trigger the same logic. There is no parallel "wants sync" flag to keep in sync with reality.

### 3.3 Dual-threshold illuminance with hysteresis

"Room is dim" comes from `sensor.living_room_motion_illuminance` (the Hue motion sensor's lux reading) using dual thresholds:

- Below **15 lux** → room is dim, bias turns on
- Above **25 lux** → room is lit, bias turns off
- Between 15-25 lux (deadband) → bias holds its current state

The deadband prevents flapping when the sensor sits near a single threshold. With a single threshold and the bias strip itself elevating the room's lux reading, the system would oscillate: bias on → room reads above threshold → bias off → room reads below threshold → bias on.

Thresholds may need tuning based on actual readings in the room. For reference, with all lights off and some ambient daylight from the office sliding door, the room reads ~2-4 lux as a baseline. Ceiling lights on bring it to ~44 lux.

### 3.4 6500K hardcoded white point for bias lighting

The bias strip is always 6500K when on. This is not a configurable variable and is not subject to Adaptive Lighting.

6500K matches the D65 white point that TVs are calibrated to. Bias lighting works by giving your eyes a neutral reference behind the screen so on-screen colors look accurate. Warming the strip in the evening (as AL would do) would make the TV's whites read as bluer by contrast and would shift color perception of content — defeating the purpose.

Brightness on the bias strip is a separate matter: currently 40% (tuned May 2026). Brightness adaptation by time of day could be added later if needed — dimmer late at night, brighter during evening viewing — but the color temperature should stay fixed.

### 3.5 Movie mode as profile override

`input_boolean.movie_mode` is a manually-toggled override that forces the video profile regardless of HDMI input. The PS5 is used for both gaming and 4K Blu-ray movies, so input alone is an ambiguous signal. Movie mode resolves the ambiguity:

1. If `input_boolean.movie_mode` is on → **video profile** (overrides input)
2. Else if HDMI input is **Apple TV** → video profile
3. Else if HDMI input is **Playstation 5** → game profile

Movie mode also has uses beyond the TV system (it's referenced by other lighting and device automations in the home), so it's a general-purpose intent flag rather than a TV-specific helper.

Movie mode is cleared automatically when the TV turns off — each session starts clean.

### 3.6 Mode Configurator re-evaluates on three event types

The Mode Configurator runs in three situations:

- **Sync just turned on** → apply profile based on current state
- **Input changed while sync is on** → re-apply profile for the new input
- **Movie mode changed while sync is on** → re-apply profile

The third case enables "switch profile mid-session" — for example, gaming on PS5 (game profile applied), then deciding to watch a 4K Blu-ray, enabling movie_mode, and the configurator re-picks and applies the video profile without needing to toggle sync off and back on.

Input change while sync is on similarly handles the case of switching from Apple TV to PS5 (or vice versa) mid-session.

When sync is off, none of these events do anything — there's no profile to re-apply, and the user hasn't expressed intent for sync. This is what keeps casual Apple TV viewing free of unwanted sync behavior.

### 3.7 Separate off-TV bias guard

The Bias Light Off-TV Guard is a small, single-purpose automation that turns the bias light back off if it's turned on while the TV is off. This catches accidental manual turn-ons (Hue app, voice command, etc.).

This is deliberately *not* part of the main Bias Light Controller. An earlier design had this logic in the controller as a `manual_on_guard` trigger, but that created a feedback loop: the bias strip illuminating the motion sensor caused brief illuminance spikes above the threshold, which the controller (re-evaluating because of its own action) interpreted as "room is now lit, turn bias off." Splitting the guard out eliminates the loop because the guard only acts when the TV is off, which is never true during a TV session.

### 3.8 PS5 power state as auxiliary signal

`switch.living_room_ps5_power` (via the PS5-MQTT integration) exposes the PS5's actual power state. This is used by the PS5 Power Off Handler: when the PS5 turns off while sync is active and the PS5 is the selected input, sync is stopped automatically. Without this, sync would keep running pointing at a black HDMI signal until manually stopped or until the TV turns off.

This is conceptually similar to what the old "stop sync on input change" automation did — using a real device-state signal instead of relying on side effects of HDMI input switching.

### 3.9 LG WebOS state handling

LG WebOS TVs report `unavailable` rather than `off` when powered off — the network interface drops with power, and the integration loses contact. Any condition or trigger that checks "is the TV off" needs to handle both states.

The TV Power Handler triggers on transitions `on → off | unavailable`, and the Off-TV Guard's condition accepts both states. Future automations that need to know "is the TV off" should use the same pattern.

### 3.10 Sync release timing delay

The Bias Light Controller's "ON" branch includes a 1-second delay before turning the strip on. This handles the brief window after sync stops where the Hue Sync Box is releasing control of the strip. Without the delay, `light.turn_on` could land before or during the sync box's release sequence and get overridden by the sync box.

This is the only delay in the system. Other transitions (TV-on, illuminance changes) don't have this race and act immediately.

### 3.11 Restrictive triggers on the Bias Light Controller

The Bias Light Controller's triggers fire only on actual `on` state transitions (`from: "on"` or `to: "on"` rather than any state change), not on attribute updates. `media_player` entities update attributes frequently (volume, currently playing track, source, etc.) and would otherwise trigger the controller on every minor state change. Filtering to actual on/off transitions keeps the controller idle most of the time.

---

## 4. Component Architecture

Five automations and two scripts. Each component has a single, clear responsibility.

| Component | Type | Responsibility | Mode |
|---|---|---|---|
| Living Room TV Power Handler | Automation | TV on/off transitions; cleanup on off | single |
| Living Room TV Bias Light Controller | Automation | Sole owner of the bias light during TV sessions | restart |
| Living Room Hue Sync Mode Configurator | Automation | Picks video/game profile; adjusts ceiling AL | restart |
| Living Room TV Bias Light Off-TV Guard | Automation | Catches manual bias turn-ons while TV is off | single |
| Living Room Hue Sync Stop on PS5 Power Off | Automation | Stops sync when PS5 powers off while syncing to PS5 | single |
| Living Room Hue Sync (Video) | Script | Configures sync box for video content | — |
| Living Room Hue Sync (Game) | Script | Configures sync box for game content | — |

### 4.1 Trigger Coverage Matrix

| Trigger | TV Power Handler | Bias Controller | Mode Configurator | Off-TV Guard | PS5 Off Handler |
|---|---|---|---|---|---|
| `media_player.living_room_tv` → on/off | ✓ | ✓ | | | |
| `switch.living_room_sync_box_light_sync` on/off | | ✓ | ✓ | | |
| `select.living_room_sync_box_hdmi_input` change | | | ✓ | | |
| `input_boolean.movie_mode` change | | | ✓ | | |
| `sensor.living_room_motion_illuminance` threshold | | ✓ | | | |
| `light.living_room_tv_lights` → on | | | | ✓ | |
| `switch.living_room_ps5_power` → off | | | | | ✓ |

---

## 5. Settings Reference

### 5.1 Bias Light

| Setting | Value | Rationale |
|---|---|---|
| `brightness_pct` | `40` | Tuned May 2026. 25% was too subtle; 40% is visible without being distracting during dark scenes. |
| `color_temp_kelvin` | `6500` | D65 white point. Matches TV calibration. Not subject to AL. |

### 5.2 Illuminance Thresholds

| Setting | Value | Rationale |
|---|---|---|
| Dim threshold | `< 15 lux` | Below this, bias turns on. |
| Lit threshold | `> 25 lux` | Above this, bias turns off. |
| Deadband | `15-25 lux` | Bias holds current state. Prevents flapping. |

### 5.3 Video Profile

Used for Apple TV input, or any input when `movie_mode` is on.

| Setting | Value | Rationale |
|---|---|---|
| Sync box `brightness` | `50` | Conservative — bright enough to be visible, low enough not to distract during dark scenes. |
| Sync box `intensity` | `high` | Smooth transitions appropriate to film. |
| Sync box `mode` | `video` | Sync box's video processing mode. |
| Ceiling AL `min_brightness` | `25` | Low floor for evening viewing. |
| Ceiling AL `max_brightness` | `50` | Caps ceiling brightness so it doesn't compete with content. |

### 5.4 Game Profile

Used for PS5 input when `movie_mode` is off.

| Setting | Value | Rationale |
|---|---|---|
| Sync box `brightness` | `85` | Punchy — matches the dynamic content of action games. |
| Sync box `intensity` | `intense` | Rapid, saturated shifts for gaming responsiveness. |
| Sync box `mode` | `game` | Sync box's low-latency game processing mode. |
| Ceiling AL `min_brightness` | `5` | Deep dimming for immersive gaming. |
| Ceiling AL `max_brightness` | `10` | Very low ceiling to keep room dark. |

### 5.5 Ceiling AL Restoration (sync off)

| Setting | Value | Rationale |
|---|---|---|
| `min_brightness` | `50` | AL baseline (mirrors `Adaptive_Lighting.md` §4.1 wind-down floor). |
| `max_brightness` | `100` | Full AL range. |

These are passed to `adaptive_lighting.change_switch_settings` with `use_defaults: current` so other AL settings (color temp, schedule, curve) are preserved.

---

## 6. Profile Selection Logic

When the Mode Configurator runs (sync started, input changed, or movie_mode changed — and sync is on), it picks a profile using these rules in order:

```
if input_boolean.movie_mode == on:
    profile = video
elif HDMI input == Apple TV:
    profile = video
elif HDMI input == Playstation 5:
    profile = game
else:
    no action  # unknown input
```

The "no action" case is intentional. If a future input (other than Apple TV or PS5) is added without updating this logic, the configurator silently does nothing on that input rather than picking the wrong profile.

---

## 7. Resulting Behavior

### 7.1 TV Power Transitions

**TV turns on (cold start):**
- Hue Sync Box powers on
- Bias Light Controller evaluates invariant; if room is dim, bias turns on at 40% / 6500K (after 1s delay)
- Sync stays off — user opts in if desired

**TV turns off:**
- Sync switch turned off (cleanup; also frees ceiling AL)
- Hue Sync Box powered off
- `input_boolean.movie_mode` cleared
- Sonos Night Sound and Speech Enhancement turned off (idempotent — no-op if already off)
- Bias Light Controller sees TV state change, turns bias off

### 7.2 Sync Activation (Apple TV)

1. User enables sync via switch
2. Bias Light Controller sees sync_on; condition fails (sync now on); bias turns off
3. Mode Configurator picks video profile (Apple TV → video)
4. Video script applied to sync box; ceiling AL limits set to 25-50%

### 7.3 Sync Activation (PS5 gaming)

1. User enables sync via switch (with PS5 input, movie_mode off)
2. Bias Light Controller turns bias off
3. Mode Configurator picks game profile
4. Game script applied; ceiling AL limits set to 5-10%

### 7.4 Sync Activation (PS5 4K Blu-ray)

1. User enables `input_boolean.movie_mode` (any time before or during)
2. User enables sync via switch
3. Mode Configurator picks video profile (movie_mode override)
4. Video script applied; ceiling AL limits set to 25-50%

### 7.5 Profile Switch Mid-Session

**Gaming → movie on PS5:**
1. User enables `input_boolean.movie_mode`
2. Mode Configurator fires on movie_mode change; sync is on; re-evaluates
3. Profile switches from game to video; ceiling AL limits widen from 5-10% to 25-50%

**Apple TV → PS5 game:**
1. User switches HDMI input
2. Mode Configurator fires on input change; sync is on; re-evaluates
3. Profile switches from video to game; ceiling AL limits narrow from 25-50% to 5-10%

### 7.6 Sync Deactivation

1. User turns off sync (or PS5 power off triggers it, or TV off triggers it)
2. Mode Configurator restores ceiling AL to 50-100%
3. Bias Light Controller fires on sync_off; evaluates invariant; if TV on and room dim, bias turns on after 1s delay

### 7.7 PS5 Power Off (sync running)

1. PS5 shuts down (controller menu, idle timeout, etc.)
2. PS5-MQTT reports `switch.living_room_ps5_power` → off
3. PS5 Power Off Handler fires; conditions match (sync on, input is PS5); turns off sync switch
4. Standard sync-off cleanup runs (see 7.6)

### 7.8 Off-TV Bias Turn-On

1. User opens Hue app while TV is off; turns on the gradient strip
2. Off-TV Guard fires; condition matches (TV is off/unavailable); turns the strip off

---

## 8. LG WebOS State Quirk

LG WebOS TVs do not behave like normal smart-home devices when powered off. The network interface drops with the power, so the WebOS integration loses contact and reports the entity as `unavailable` rather than `off`.

Implications:

- **TV-off triggers must accept both states.** Triggers should be `from: "on", to: ["off", "unavailable"]` rather than just `to: "off"`.
- **TV-off conditions must accept both states.** Use `state: ["off", "unavailable"]` lists.
- **Brief network blips can cause `unavailable` flickers.** If false cleanups become a problem, a `for: "00:00:NN"` debounce can be added to the off-trigger — but this delays legitimate cleanup by the same duration, so tune carefully.
- **TV-on triggers should also include `from: "unavailable"`.** When the TV powers back on, it comes back from `unavailable`, not `off`.

The TV Power Handler triggers on both `from: "off"` and `from: "unavailable"` for TV-on. The Off-TV Guard accepts both states in its condition.

A future automation that needs to know "is the TV off" should use the same pattern. This is documented because it's a non-obvious gotcha that bit during initial testing.

---

## 9. Tuning & Monitoring

### 9.1 Bias Brightness

| Symptom | Adjustment |
|---|---|
| Bias barely visible during normal content | Push `brightness_pct` higher (45-55) |
| Bias distracting during dark scenes | Drop `brightness_pct` lower (30-35) |
| Bias seems fine for shows but too much for movies | Consider movie_mode-based brightness override (not currently implemented) |

### 9.2 Illuminance Thresholds

The thresholds depend on:

- The motion sensor's exact placement and orientation
- How much daylight typically reaches the room
- Ceiling fixture output levels
- Whether the bias strip itself contributes to the reading

| Symptom | Adjustment |
|---|---|
| Bias doesn't come on when expected | Raise dim threshold (try 20 lux) |
| Bias stays on with too much ambient light | Lower lit threshold (try 20 lux) |
| Bias flickers near boundary | Widen deadband (e.g., 10/30) |
| Bias never comes on, even in dark room | Sensor placement issue — check actual reading in Developer Tools |

### 9.3 Profile Settings

Sync box brightness and intensity are highly subjective. Worth testing during representative content (a dark movie scene, an action game, a brightly-lit show) before committing to changes.

For ceiling AL limits, the goal is "dim enough to not compete with screen, but not so dim that the room becomes a cave." 25-50% works well for video; 5-10% is appropriate for gaming where the goal is full immersion.

### 9.4 Sonos Cleanup

Sonos Night Sound and Speech Enhancement are turned off unconditionally on TV-off. `switch.turn_off` is idempotent, so this works even if they were already off. If additional Sonos features get added later, they should be cleaned up the same way.

---

## 10. Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Bias doesn't turn on after sync stops | Sync release timing race | Verify 1s delay is in Bias Light Controller's ON branch |
| Bias turns on then immediately off | Feedback loop from `manual_on_guard` trigger | Verify Bias Light Controller does NOT trigger on `light.living_room_tv_lights` state changes (this trigger should only exist in the Off-TV Guard) |
| Ceiling lights brighten unexpectedly mid-session | HDMI handshake from PS5 caused brief sync-off | Known issue (§13). Current behavior is to react to the sync-off; future fix may add a PS5-aware suppression. |
| Sync stays on after PS5 powers off | PS5-MQTT integration not reporting state correctly | Verify `switch.living_room_ps5_power` in Developer Tools → States; check PS5-MQTT addon logs |
| TV-off cleanup doesn't fire | TV went to `unavailable` instead of `off`, or trigger doesn't accept both | Verify TV Power Handler's `tv_off` trigger includes both states (§8) |
| Bias light turns on briefly when TV turns off | Race between TV-off cleanup turning off sync, and Bias Controller seeing sync-off | Acceptable — bias is briefly turned on then immediately off when TV state propagates. Could be tuned by adjusting order of operations in TV Power Handler. |
| Profile doesn't switch when toggling movie_mode mid-session | Sync is off | Mode Configurator only acts on movie_mode change when sync is on — by design |
| Game profile applied when watching PS5 movie | Forgot to enable `input_boolean.movie_mode` | Enable movie_mode; Mode Configurator will switch profile |
| Sync auto-starts when changing inputs | The user is recalling an earlier design that auto-started sync | This was reverted — sync is intent-driven now (§3.2). User must opt in. |

---

## 11. Test Cases

These cover the major behaviors. Run after any architectural change.

1. **TV on, room dim (<15 lux), sync off** → bias comes on at 40% / 6500K after 1s
2. **Bias on, then enable sync (Apple TV input)** → bias turns off, video profile applied
3. **Disable sync while TV still on, room still dim** → bias returns, ceiling AL restored
4. **Sync on for PS5 game, then enable movie_mode** → profile switches from game to video
5. **Sync on for Apple TV, then switch input to PS5** → profile switches from video to game (movie_mode off)
6. **Sync on, change input to PS5, enable movie_mode** → video profile applied (movie_mode wins)
7. **Manual bias turn-on from Hue app while TV is off** → snaps back off
8. **TV off** → sync, sync box, movie_mode, Sonos toggles all clean up
9. **Room illuminance crosses 25 lux while bias on** → bias turns off
10. **Room illuminance hovers at 18-22 lux** → bias holds current state (deadband)
11. **Sync on with PS5 input, PS5 powers off** → sync stops, ceiling AL restored, bias returns if room is dim

---

## 12. Implementation

This section contains the complete YAML for every automation and script in the system. To rebuild from scratch, follow §12.1 for setup prerequisites, then create the automations in §12.2 and scripts in §12.3.

### 12.1 Prerequisites

Before creating the automations, verify all of the following exist and are correctly named:

| Item | Notes |
|---|---|
| LG WebOS integration installed and `media_player.living_room_tv` exists | Default integration; configured via Settings → Devices & Services |
| Philips Hue Play HDMI Sync Box integration installed | Provides `switch.living_room_sync_box_power`, `switch.living_room_sync_box_light_sync`, `select.living_room_sync_box_hdmi_input` |
| `light.living_room_tv_lights` exists | Hue gradient lightstrip, exposed via Hue integration (not via the sync box) |
| Hue motion sensor exists with illuminance entity | `sensor.living_room_motion_illuminance` |
| Adaptive Lighting installed and configured for living room ceiling | `switch.adaptive_lighting_living_room_ceiling_lights` — see `Adaptive_Lighting.md` |
| PS5-MQTT integration installed | Provides `switch.living_room_ps5_power`. If not yet installed, automation #5 can be skipped initially. |
| `input_boolean.movie_mode` helper exists | Created via Settings → Devices & Services → Helpers → Toggle |
| Sonos integration with Night Sound and Speech Enhancement switches | `switch.living_room_sonos_night_sound`, `switch.living_room_sonos_speech_enhancement` |
| HDMI input names match exactly | The Mode Configurator's choose block references `Apple TV` and `Playstation 5` as strings. Verify in `select.living_room_sync_box_hdmi_input` attributes. |
| Hue Sync Box device ID known | Required by the video and game scripts. Find in Settings → Devices & Services → Hue Play HDMI Sync Box → click the device → `device_id` in the URL or via Developer Tools → Devices. Current value: `a99ddac081e83072ec97e2d8b8d3c6ba` |

### 12.2 Automations

Each automation below is paste-ready into the HA automation editor (YAML mode). After creating, set the following via the UI:

- **Area:** Living Room
- **Category:** Lighting (or whatever category covers the system in the home's organization)

#### 12.2.1 Living Room TV Power Handler

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

#### 12.2.2 Living Room TV Bias Light Controller

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

#### 12.2.3 Living Room Hue Sync Mode Configurator

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
          - alias: Restore ceiling AL limits (50-100%)
            action: adaptive_lighting.change_switch_settings
            data:
              use_defaults: current
              entity_id: switch.adaptive_lighting_living_room_ceiling_lights
              min_brightness: 50
              max_brightness: 100
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
                      entity_id: switch.adaptive_lighting_living_room_ceiling_lights
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
                      entity_id: switch.adaptive_lighting_living_room_ceiling_lights
                      min_brightness: 5
                      max_brightness: 10
mode: restart
```

#### 12.2.4 Living Room TV Bias Light Off-TV Guard

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

#### 12.2.5 Living Room Hue Sync Stop on PS5 Power Off

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

### 12.3 Scripts

Both scripts call `huesyncbox.set_sync_state`. The `device_id` must match the actual device ID of the Hue Sync Box — find this in Settings → Devices & Services → Hue Play HDMI Sync Box. Replace the value below if rebuilding.

#### 12.3.1 Living Room Hue Sync (Video)

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

#### 12.3.2 Living Room Hue Sync (Game)

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

### 12.4 Deployment Order

When standing up the system from scratch, enable in this order to make troubleshooting easier:

1. Both scripts first (no triggers, safe to have idle)
2. Living Room TV Power Handler — verify TV on/off cleanup works
3. Living Room TV Bias Light Controller — verify bias responds to TV state and room dimness
4. Living Room TV Bias Light Off-TV Guard — verify off-TV protection works
5. Living Room Hue Sync Mode Configurator — verify sync profile selection works
6. Living Room Hue Sync Stop on PS5 Power Off — verify PS5 off triggers sync stop (requires PS5-MQTT)

After all are enabled, run through the test cases in §11.

---



## 13. Related Documents

- `HA_Naming_Standard.md` — entity ID and friendly name conventions used throughout this document
- `Adaptive_Lighting.md` — the AL configuration this system manipulates via `adaptive_lighting.change_switch_settings`. The 50-100% ceiling restoration value in §5.5 should track AL's baseline (currently aligned).

---

## 14. Open Questions / Future Work

- **HDMI signal renegotiation handling.** When the PS5 changes video signal mid-session (HDR enable, refresh rate change), the HDMI link drops briefly. The sync box loses signal and internally disables sync, which currently causes a visible lighting disruption (ceiling brightens, bias may flicker on, sync stays off). Three potential fixes have been discussed: (a) suppress Mode Configurator reaction when PS5 is on with PS5 input selected, (b) same as (a) plus auto-resume sync after a short delay, (c) combination with smart user-intent detection via context. No fix is currently implemented; observation period needed to determine how often this actually happens and how disruptive it really is.
- **Auto-disable sync when PS5 is in standby but appears as "on".** PS5 rest mode behavior in PS5-MQTT may report standby as on or off depending on configuration. Worth verifying behavior matches expectations.
- **Bias brightness adaptation by time of day.** Could vary bias brightness (not color temp) based on time — dimmer late at night, brighter during evening. Currently hardcoded at 40%. Defer unless visibility becomes an actual problem.
- **Apple Arcade gaming.** No way to force game profile when input is Apple TV. Not currently needed — Apple Arcade is not used. If it becomes a use case, would need an additional override mechanism distinct from movie_mode.
- **Music sync mode.** The sync box also supports a music sync mode for audio-reactive lighting. Not currently used — could be added if music listening via the TV becomes common.
- **Other inputs.** Currently only Apple TV and Playstation 5 are handled by the Mode Configurator. Adding a third input (e.g., a different gaming console, or a streaming stick) would require updating the profile selection logic in §6 and the Mode Configurator's choose block.
- **Movie mode as a more general intent flag.** `input_boolean.movie_mode` is used by other automations beyond this system. Worth ensuring those other uses don't conflict with the TV system's usage pattern (cleared on TV-off, set manually).
- **PS5-MQTT app detection for auto-movie-mode.** PS5-MQTT may expose the currently-running app/game. In theory, detecting a media app like the Blu-ray player or YouTube on PS5 could auto-enable movie_mode. Not currently feasible — the home setup only uses PS5 for gaming and 4K Blu-ray, and the Blu-ray player doesn't have a clean detectable signal.
