# Inovelli Switches

*Last updated: September 2026*

## Overview

This guide covers Inovelli switches in this house, all Matter-over-Thread and all
commissioned to Home Assistant. It has two parts:

- **[Shared: LED Bar](#shared-led-bar)** — the notification-LED pattern used by every
  Inovelli switch that has one, regardless of what the switch actually controls. Any future
  Inovelli switch with an LED bar follows this section.
- **[Device pattern: Ceiling Fan Canopy](#device-pattern-ceiling-fan-canopy)** — the specific
  hardware pairing (VTM36 canopy + VTM30-SN wall switch) used to drive a ceiling fan and
  light from a switch with no Load wired to it. This is the only device pattern built so far;
  it consumes the Shared LED Bar section rather than duplicating it. A future device pattern
  (e.g. a standalone Inovelli switch with no canopy) would get its own section below,
  reusing the same shared LED logic.

## Shared: LED Bar

Applies to any Inovelli switch's notification LED bar in this house — the three currently
built (Avery's Room, Master Bedroom, Office) are all paired with a Ceiling Fan Canopy, but
nothing about this section depends on that pairing.

### Channel

Each switch exposes its LED bar as four native parameters, plus a separate RGB notification
light entity that this design does **not** use:

| Entity | Role |
|---|---|
| `select.<prefix>_..._led_color` | 13 named colours (Red, Orange, … Blue, Violet, … White) |
| `select.<prefix>_..._led_intensity_on` | Brightness step (`0,1,3,5,8,…,100`) applied while the switch's internal relay reads on |
| `select.<prefix>_..._led_intensity_off` | Same step list, applied while the relay reads off |
| `select.<prefix>_..._led_effect` | Animation list (`Solid`, `Fast Falling`, `Fast Rising`, …) |
| `light.<prefix>_..._led` (unused) | RGB notification channel — deprecated, left hidden |

**Native `LED Color` + `LED Intensity`, not the RGB light entity.** The RGB notification
channel's `hs_color` silently drops white and low-saturation values while reporting success
(`LESSONS.md`) — a channel-specific quirk. The native `LED Color` select has no such gap: it's
the vendor's own named-colour parameter, so this design uses it and retires the quirk rather
than working around it. The RGB entity is left in place, hidden, as a fallback if this ever
needs revisiting.

**`LED Effect` always stays `Solid`.** Nothing in this design plays an animation. Every write
to it is guarded to skip when it's already `Solid`, since a same-value write can still
trigger the switch's own transition ramp and costs a Matter round-trip for nothing (see
[Known hardware quirk](#known-hardware-quirk) below).

**`LED Intensity(On)` and `(Off)` are always written together, to the same value.** The
switch's internal relay flips on every paddle press (this is what fires the Matter binding —
see the canopy pattern's Step 3) and the bar tracks whichever of the two matches the current
relay state. Writing them in lockstep is what keeps the bar from blinking every time the
paddle is pressed.

### Presence gates on/off; sleep only dims

**Every switch shows something whenever someone is home — day or night.** Sleep never turns
the bar off; it only picks a dimmer intensity. This applies identically to every switch in
the house — Office, Master Bedroom, and Avery's Room all follow the exact same rule, with no
per-room classification to get right at install time:

| Condition | Colour | Intensity |
|---|---|---|
| Someone home, switch "active" | device-pattern-defined (e.g. fan speed colour) | `26` by day, `3` at night |
| Someone home, switch idle | `White` (locator glow) | `3`, day or night |
| Nobody home | — | `0` (dark) |

Night intensity (`3`) is the same value as the idle locator glow's constant `3` — one number to
remember, not two. The locator glow itself doesn't need a day/night split at all: `3` is already
faint enough by day and visible enough by night. "Idle" is device-pattern-defined the same way
"active" is — see [What's device-pattern-specific](#whats-device-pattern-specific).

**Day vs. night is `input_boolean.everyone_sleeping`, plus any person-specific sleep flag
layered on for that switch.** A person-specific flag makes the switch dim as soon as *that
person* goes to bed, without waiting for the whole household — Avery's Room ORs in
`input_boolean.avery_sleeping` for exactly this reason (see
[Replicating for another room](#replicating-for-another-room)). A person-specific flag only
ever picks between two *dim* values here, never between lit and dark, so a stale flag (that
person away for days, nobody home to clear it) costs nothing worse than the wrong shade of
dim while everyone else is home and awake. No `binary_sensor.<person>_home_today` style
staleness guard is needed, since presence (`zone.home`) alone is what decides dark vs. lit.

### Resting-state script pattern

One script per switch, `script.<prefix>_..._led_state`, `mode: restart`, taking no
parameters — everything is read from live state. Fully idempotent: recomputed from scratch on
every call, so there is no snapshot and none of the `scene.create` failure modes a
snapshot/restore approach would carry (captured mid-transition, or suppressing the next
colour command — `LESSONS.md`). Every `select.select_option` call is guarded to skip when the
target already holds the desired value, both to avoid a wasted Matter round-trip and to dodge
a possible spurious transition flicker on a no-op recompute.

A **household gating automation** (`automation.household_ceiling_fan_switch_led_locator` for
the current canopy-paired switches) reacts to presence and sleep-boolean changes and calls
`led_state` for each affected switch. Household-wide triggers (presence,
`everyone_sleeping`) recompute every switch; a person-specific sleep flag recomputes only the
switch(es) that flag applies to. There is no branching decision to make here — no flash, no
"is this switch currently active" check — every trigger is just "recompute now," which is
also why the household automation carries no bug surface: the whole thing is idempotent
recomputation, nothing timing-sensitive.

### What's device-pattern-specific

This section deliberately says nothing about *what* the "active" colour is or what makes a
switch "active" vs. "idle" — that's supplied by whatever the switch controls. The Ceiling Fan
Canopy pattern's addition is exactly one thing: map the fan's current speed onto a colour, and
call the switch "active" while the fan runs. A future canopy-less switch would have no
"active" state at all — just the locator glow while home, and dark while away.

### Known hardware quirk

Paddle-driven changes on a canopy-paired switch show a brief (~1s) downward-wipe visual on
the bar, independent of any `LED Effect`/`LED Color`/`LED Intensity` value HA sets — confirmed
by entity history showing `LED Effect` never leaving `Solid` through the transition. Traced to
the switch's own local acknowledgment of the physical paddle press (the one path where its
internal relay flips), not anything commanded from HA. Tracked in GitHub issue #2 for
re-testing after a firmware update; not fixable from this side today.

## Device pattern: Ceiling Fan Canopy

A ceiling fan is driven by an Inovelli White Series **VTM36 LightFan canopy
module** in the fan housing, paired with an Inovelli White Series **VTM30-SN
on/off switch** at the wall. Both are Matter-over-Thread devices commissioned to
Home Assistant.

This is a per-room pattern. Avery's Room is the first instance and is used as the
worked example throughout; the Master Bedroom is the second. See
[Replicating for another room](#replicating-for-another-room) for what stays
identical and what changes per room.

The ceiling is wired permanently hot — line and load are bonded in the wall box
and the switch's Load terminal is empty. The wall switch therefore controls
nothing electrically; it is a button. The physical retrofit (removing a Harbor
Breeze 40837 RF receiver, bonding line/load, swapping the switch) is documented
separately in the "Harbor Breeze to Inovelli" work order; this guide covers only
the Home Assistant side once both devices are paired.

### Architecture

Six mechanisms connect the wall switch to the fan/light:

| Function | Mechanism | Works with HA down? |
|---|---|---|
| Paddle tap up/down → light on/off | Matter binding, cluster 6 (switch → canopy) | Yes |
| Paddle hold up/down → light dim up/down | Matter binding, cluster 8 (switch → canopy) | Yes |
| Paddle double-tap down → fan + light off; double-tap up → fan on (last speed) + light on | HA automation | No |
| Config button taps → fan speed (1 tap cycle, 2 taps off, 3 taps peek) | HA automation | No |
| Fan/light state change → switch LED bar update | HA automation ([Shared: LED Bar](#shared-led-bar)) | No |
| Paddle hold release, any observed light turn-off, or any observed light turn-on → Adaptive Lighting manual-control handoff / correction | HA automation ([Step 6](#step-6--ha-automation), `guides/adaptive_lighting.md`) | No |

The whole-room off/on gesture is a paddle **double-tap** (`multi_press_2` on the
up/down paddle event entity), handled by the HA automation. Tap → light and
hold → light are Matter bindings and are independent of it.

```
                       Avery's Room ceiling
                       ┌───────────────────────────┐
                       │  VTM36 canopy (node 10)   │
                       │   endpoint 1: light  ──────┼──► light.averys_room_ceiling_fan_light
                       │   endpoint 2: fan    ──────┼──► fan.averys_room_ceiling_fan
                       └────────▲─────────▲─────────┘
                                │         │
          Matter bindings       │         │   Matter (HA-issued commands)
   (On/Off cl. 6, Level cl. 8)  │         │
                                │         │
                       ┌────────┴─────────┴─────────┐
    wall paddle  ──────► VTM30-SN switch (node 11)  │
    config button ─────► endpoint 2: Binding cluster│
                       │  event.*_button_down/up    │──► automation: double-tap → fan/light off / on
                       │  event.*_button_config     │──► automation: Ceiling Fan Wall Control
                       │  light.*_switch_led (unused)│
                       │  select.*_switch_led_*      │◄── script.<prefix>_ceiling_fan_led_state
                       └────────────────────────────┘     (Shared: LED Bar)

  automation.<prefix>_ceiling_fan_wall_control   (one automation, five triggers)
      event.*_button_config        ──►  fan.set_percentage / fan.turn_off   (1 / 2 taps)
                                   └─►  script.<prefix>_ceiling_fan_led_state (3 taps: peek)
      event.*_button_down (multi_press_2) ─►  fan.turn_off + light.turn_off
      event.*_button_up   (multi_press_2) ─►  fan.set_percentage (last speed) + light.turn_on
      event.*_button_up/down (long_release) ─►  adaptive_lighting.set_manual_control (true)
      fan.<prefix>_ceiling_fan      ──►  input_select.<prefix>_ceiling_fan_last_speed
                                   └─►  script.<prefix>_ceiling_fan_led_state
      light.<prefix>_ceiling_fan_light ─►  script.<prefix>_ceiling_fan_led_state
                                   ├─►  adaptive_lighting.set_manual_control (false, when → off)
                                   └─►  adaptive_lighting.apply, 2s (when → on, not manual)
```

### Key design decisions

- **The light is bound; the fan is not.** Matter binding writes the paddle → light
  relationship into the switch's firmware, so it survives HA being offline and has
  no round-trip lag. An on/off switch has no bindable Matter cluster for Fan
  Control (0x0202), so the config button drives the fan through an HA automation.
  The split is deliberate: the everyday interaction is resilient; the fan, used
  less often, accepts the HA dependency.

- **Two bindings: On/Off (cluster 6) and Level Control (cluster 8).** Cluster 6 is
  paddle tap → light on/off; cluster 8 is paddle press-and-hold → smooth local dim,
  release stops the ramp. Cluster 8 only emits Move/Step while `Dimming Speed
  (Simulated)` is a non-`Instant` duration — [Step 3](#step-3--switch-vtm30-sn-parameters)
  sets the value; `LESSONS.md` has the values tried and rejected.

- **Paddle double-tap → whole-room off/on (HA automation).** `multi_press_2` on
  `event.<prefix>_ceiling_fan_switch_button_down` turns fan and light off;
  `multi_press_2` on `…_button_up` sets the fan to the remembered speed and turns
  the light on. Each branch gates on `event_type` being `multi_press_2`, so a
  single tap or a hold does not match — which is what leaves the cluster 8
  hold-to-dim binding free. The switch's `300ms` Button Delay already covers
  multi-tap detection, so the double-tap costs no extra latency.

- **Binding fires on physical presses only.** A command sent to the switch from HA
  or Apple Home does not propagate over the binding, and bound state does not
  report back — the LED bar will not track software light changes over the binding
  itself. This doesn't matter here: the LED bar is driven independently by the
  automation described in [Shared: LED Bar](#shared-led-bar), reacting to the
  light entity's actual state regardless of what changed it.

- **Config button: taps only, never holds.** Holding the config button opens the
  VTM30-SN's local programming menu, so only `multi_press_*` events are mapped:
  `multi_press_1` cycles the speed (or resumes from off), `multi_press_2` turns the
  fan off, `multi_press_3` is a read-only peek that updates the LED bar without
  touching the fan. The button-press-delay window aggregates a multi-tap into one
  event, so a triple tap emits `multi_press_3` alone.

- **Speed memory lives in a helper.** When the Matter fan is off, HA retains no
  memory of its prior speed (`percentage` reads 0, `preset_mode` null).
  `input_select.<prefix>_ceiling_fan_last_speed` records the running speed so a
  config-button tap from off can resume it.

- **One automation per room.** `automation.<prefix>_ceiling_fan_wall_control`
  carries the non-binding links (config button gestures, down/up paddle
  double-taps, fan/light → LED dispatch) on five triggers with a top-level
  `choose` on `condition: trigger id`. `mode: queued` (max 10) so runs process in
  order. This keeps each room a single reviewable unit with identical behaviour.

- **The LED bar's "active" colour maps the fan's current speed — nothing else about
  the bar is canopy-specific.** Everything else (the resting-state script pattern,
  the presence/day-night rule, the household dispatch automation) is the
  [Shared: LED Bar](#shared-led-bar) pattern, unmodified.

- **The LED bar reacts to settled state, not button presses.** With no per-change
  animation to time precisely, dispatching from the button-gesture branches ahead
  of the fan's own Matter round-trip would only add complexity for no visible
  benefit. Every LED update comes from the `fan.percentage` and
  `light.<prefix>_ceiling_fan_light` state triggers alone, reacting within the
  fan's normal ~0.3–0.6s settle time. The button-gesture branches contain no LED
  code at all.

- **Adaptive Lighting owns steady-state ceiling brightness.** The three fan lights
  are enrolled in Adaptive Lighting (`guides/adaptive_lighting.md`); `On level`
  (Step 2) is written by its pre-stage automation, not set here. A paddle hold
  dims locally over the cluster 8 binding, and on `long_release` this automation
  pins that level against AL's curve; any turn-off HA observes hands brightness
  back to AL, and any turn-on HA observes gets a fast 2s snap to the curve since
  pre-staging alone is not reliably honored on every turn-on path.

## Prerequisites

- Home Assistant with the Matter integration and a matter.js-based Matter
  Server (the binding UI is a standard, non-beta feature there)
- A Thread border router HA can see; both devices on the same Thread network
  (verify `sensor.*_thread_network_name` matches on both)
- Both devices commissioned to the Home Assistant Matter fabric (not only Apple
  Home) — binding must be written by an admin on the fabric, and Apple Home
  exposes no binding interface
- VTM36 canopy firmware **1.0.1r1 or later**, VTM30-SN switch firmware updated to
  latest. The entity IDs and the minimum-dim control in this guide assume VTM36
  `1.0.1r1`, which moves the per-endpoint config parameters onto standard Matter
  Mode Select endpoints (EP20–EP26). Updating an already-paired canopy to
  `1.0.1r1` leaves stale entities and can break the binding — see
  [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).
- The physical install complete: ceiling permanently hot, switch Load terminal
  empty, pull chains set to fan HIGH / light ON

## Step 1 — Device and entity naming

Both devices land with poor default names. Rename the devices, then rename the
entities the automations reference (HA does not re-slug existing entity IDs on a
device rename):

| Device default name | Renamed to |
|---|---|
| `White Series LightFan Module` | `Ceiling Fan` |
| `Matter Thread On Off Switch VTM30-SN` | `Ceiling Fan Switch` |

Entities renamed to purpose-based IDs (see `standards/naming.md`):

| Entity | Purpose |
|---|---|
| `light.averys_room_ceiling_fan_light` | Fan light (canopy endpoint 1) |
| `fan.averys_room_ceiling_fan` | Fan motor (canopy endpoint 2) |
| `event.averys_room_ceiling_fan_switch_button_up` / `_down` / `_config` | Paddle and config button events |
| `sensor.averys_room_ceiling_fan_switch_humidity` / `_temperature` | Switch's built-in sensors |
| `light.averys_room_ceiling_fan_switch_led_bar` | RGB indicator bar (unused - see Shared: LED Bar) |
| `switch.averys_room_ceiling_fan_switch_load_control` | Empty Load relay — see Step 5 |

> HA's slugifier turns "Avery's" into `avery_s`, not `averys`. Every entity and
> helper created from an "Avery's Room …" name needs its ID corrected to
> `averys_room_*` afterward to match the naming standard.

**Duplicate config entities.** A firmware change that moves config parameters onto
spec-compliant Mode Select endpoints leaves the pre-change entities behind as dead
duplicates: they read `unavailable` (`restored`) after an HA restart and a fresh
entity (often `…_2`-suffixed) carries the live value. On the VTM36 this is
firmware `1.0.1r1`; on the VTM30-SN it came with the matter.js Matter Server.
On both devices, delete the dead originals and rename the surviving `…_2` entity
back to the clean slug:

- Canopy: `select.<prefix>_ceiling_fan_light_mode`, `_fan_mode`, and
  `number.<prefix>_ceiling_fan_on_off_transition_time` — per
  [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).
- VTM30-SN: `select.<prefix>_ceiling_fan_switch_smart_bulb_mode`, `…_led_color`,
  `…_led_effect`, and the `light.<prefix>_ceiling_fan_switch_led_bar` bar.

Only the `select.<prefix>_ceiling_fan_switch_led_*` entities (colour, intensity
on/off, effect) are referenced by config — the LED script drives them, see
[Shared: LED Bar](#shared-led-bar) — so if any of their slugs change, update
`script.<prefix>_ceiling_fan_led_state` and its `ha/` mirror in the same pass.
The rest are config entities nothing depends on, so those
renames are safe on their own.

**Incomplete device rename leaves stale prefixes, not duplicates.** Renaming
a device in the HA UI does not re-slug its existing entity_ids — only newly
discovered entities pick up the new device name (`standards/naming.md` §4.4).
The Office switch was renamed to "Ceiling Fan Switch" after some of its
entities already existed, so 26 of them were stuck under two older
generations of prefix (`select.office_matter_thread_on_off_switch_vtm30_sn_*`
and, for nine Thread-diagnostics sensors, `sensor.inovelli_on_off_switch_*`).
Nothing referenced either prefix, so all 26 were renamed to the clean
`office_ceiling_fan_switch_*` slug. Confirm nothing in a device's entity
list still carries an old device name or platform-default prefix after a
rename; it isn't a genuine duplicate endpoint, just an unfinished one.

The nine Thread-diagnostics sensors (`_thread_channel`, `_thread_routing_role`,
`_thread_network_name`, `_reboot_count`, `_uptime`, `_boot_reason`, and the
three `_current_switch_position_*`) come `disabled_by: integration` from the
Matter integration on **all three** switches, Office included — this is the
integration's own default for that entity category, not leftover config from
the rename. HA also refuses to rename an entity that's disabled by its
integration, so renaming them required enabling them first; they were
disabled again immediately after to keep parity with Master Bedroom and
Avery's Room.

## Step 2 — Canopy module (VTM36) parameters

Set on the canopy device page (entity IDs assume the `1.0.1r1` layout and the
post-update rename — see [Step 1](#step-1--device-and-entity-naming)):

| Setting | Entity | Value | Why |
|---|---|---|---|
| Light Mode | `select.averys_room_ceiling_fan_light_mode` | `Trailing Dimmer` | The integrated LED driver cuts out at ~20% on leading edge; trailing (reverse phase) drops that to ~10%, and Minimum dim level (below) then pins a clean floor. |
| Fan Mode | `select.averys_room_ceiling_fan_fan_mode` | `Ceiling (3 Speed)` | Matches the fan; gives HA a 3-speed `fan` entity (low 33 / medium 66 / high 100). |
| Minimum dim level | `select.averys_room_ceiling_fan_ligh_min_level` | `13%` | Lowest step that holds without the driver dropping the light; `1%` on the HA brightness slider maps to this floor. (Friendly name reads "Ligh Min Level" — an Inovelli typo.) |
| Maximum dim level | `select.averys_room_ceiling_fan_ligh_max_level` | `70%` | The light kit attached to the fan plateaus well below full phase-cut — above ~70% it is already at maximum output, so the top third of the HA brightness slider produces no visible change. Capping here maps the slider's full travel onto the range the eye can actually see. Mirror of the Minimum dim level floor at the other end. This is a property of the fixture, not the VTM36 — retest if a fan's light kit is ever changed. `70%` is the tested value; all rooms use identical fixtures, so it is uniform. The options list is coarse (`60/65/70/75/80…`). (Friendly name reads "Ligh Max Level" — an Inovelli typo.) |
| On level (endpoint 1, light) | `number.averys_room_ceiling_fan_on_level_1` | Adaptive Lighting-managed | `255` is the "restore previous brightness" sentinel; `254` forces every On to 100%. This value is not set by hand: `automation.adaptive_lighting_pre_stage` writes the current Adaptive Lighting brightness target here while the light is off, so a binding-driven paddle-up comes on near the adapted level (`guides/adaptive_lighting.md`). Set it to `254` only if Adaptive Lighting is removed. |
| Power-on behavior (both endpoints) | `select.averys_room_ceiling_fan_power_on_behavior_1` / `_2` | `previous` (default) | After a breaker/mains restore, fan and light return to their prior state. The breaker is now the only disconnect for the ceiling, so this is worth setting deliberately. |
| Fan Min / Max Speed | `select.averys_room_ceiling_fan_fan_min_speed` / `_fan_max_speed` | `Low` / `High` (default) | Full range; leave unless a fan needs a narrower band. |
| Light transition time (On / Off / On-Off) | `number.averys_room_ceiling_fan_on_transition_time`, `…_off_transition_time`, `…_on_off_transition_time` | `0.5` s (all three) | Factory default is 2.5 s — a slow mood-fade that feels wrong on a bedroom light next to the ~0.4–1 s fade of the Hue / IKEA bulbs elsewhere. Set all three: HA on/off and some command paths read the combined `On/Off` value; the split `On` / `Off` pair covers the rest and takes precedence when set. Because `light.turn_off` drops any `transition:` HA passes (see `LESSONS.md`), these numbers are what actually control the fade. |

Leave `Fan Breeze Mode` (`Off`) and `FanQuick Start` (`Quick Start Disable`) at
their defaults.

> **Coordinated change:** `On level` (endpoint 1) is written by
> `automation.adaptive_lighting_pre_stage` — see `guides/adaptive_lighting.md`. If
> Adaptive Lighting is removed, set it back to `254`. If Minimum / Maximum dim
> level change, re-check the brightness → `OnLevel` scale in that guide, which
> assumes the ~13–70% window those two values define.

### Config parameters over Matter

On `1.0.1r1` the canopy exposes its Inovelli parameters as standard Mode Select
endpoints (EP20–EP26), which HA surfaces as the `select` entities above — Light
Mode, Fan Mode, min/max dim level, min/max fan speed, breeze mode, quick start.
`Power-on behavior` comes from `StartUpOnOff`; `On level` from Level Control
`OnLevel`.

On stock `1.0.0` only Light Mode and Fan Mode were Mode Select clusters and the
minimum-dim parameter was unreachable — the legacy Inovelli vendor cluster
(`0x122FFC31`) has no matter.js schema, so a write fails with `error_code 8`, and
Level Control `MinLevel` is read-only per spec. `1.0.1r1` is what makes the dim
floor settable. `scripts/matter_write_attribute.py` (`--dump-node`) still reads
the vendor cluster for discovery.

## Step 3 — Switch (VTM30-SN) parameters

Set physically during the install (paddle + config taps) and confirmed in HA:

| Setting | Value | Why |
|---|---|---|
| Switch mode | Single-pole | No traveler; single-location install. Set physically; the live readout in HA is `select.*_switch_type` = `Single-Pole` (the older `Switch Mode` select reads `unavailable`). |
| Smart Bulb Mode | Enabled | Keeps the load permanently powered so the paddle emits Matter commands (events / bindings) instead of chasing the empty local relay. Required for the binding to fire. Live entity: `select.*_ceiling_fan_switch_smart_bulb_mode` = `Smart Bulb Enable`. |
| Control of switch load | `Remote & paddle control` (default — **do not** change) | On the White series the outgoing On/Off binding is triggered by the paddle's local load action. Setting this to `Remote control only` (to stop the phantom `switch.*_ceiling_fan_switch_load_control` toggle) also kills the paddle → light binding, even with Smart Bulb Mode on. Leave it and accept the internal-relay toggle as the cost of a working binding. See `LESSONS.md`. Live entity: `select.*_ceiling_fan_switch_control_of_switch_load`. |
| Dimming Speed (Simulated) | `2s` | End-to-end ramp time for a paddle press-and-hold over the cluster 8 (Level Control) binding — see [Step 4](#step-4--matter-binding-paddle--light). At `Instant` (default) a paddle hold emits no Move/Step and cluster 8 dimming does nothing. `2s` is the tested value on both rooms; see `LESSONS.md` for values tried and rejected. Live entity: `select.*_ceiling_fan_switch_dimming_speed_simulated`. |
| `LED Color`, `LED Intensity(On)` / `(Off)`, `LED Effect` | Automation-managed — see [Shared: LED Bar](#shared-led-bar) | Not set once and left; `script.<prefix>_ceiling_fan_led_state` writes these continuously in response to fan/light/presence/sleep state. Nothing about them is a fixed installer setting on this device. |

## Step 4 — Matter binding: paddle → light

Done in the Matter Server Web UI.

1. Open node **11** (Ceiling Fan Switch). Node IDs come from the Matter
   identifier on the device page (`deviceid_…-00000000000000NN-…`, hex).
2. Find the endpoint exposing the **Binding** cluster — **endpoint 2** on the
   VTM30-SN (endpoint 1 is the dead Load relay).
3. Add two binding targets, both to node **10** (Ceiling Fan canopy),
   **endpoint 1** (the Dimmable Light — *not* endpoint 2, the fan):
   - cluster **6 (On/Off)** — paddle tap → light on/off
   - cluster **8 (Level Control)** — paddle press-and-hold → dim up/down
4. If the UI has a separate ACL step, add an entry on node 10 granting node 11
   operate access. Most binding UIs write the ACL automatically.
5. Set `Dimming Speed (Simulated)` = `2s` ([Step 3](#step-3--switch-vtm30-sn-parameters)).
   Without a non-`Instant` value the cluster 8 bind emits nothing on a paddle
   hold and the dim half of this step will look broken.
6. Test at the wall: tap up → light on (at the `On level` — pre-staged by
   Adaptive Lighting, or 100% if `number.*_on_level_1` is `254`), tap down →
   light off; hold up → smooth ramp up, hold down → ramp down, release → stop
   mid-ramp. Confirm all of it still works with Home Assistant stopped.

The paddle **double-tap** (whole-room off/on) is not bound — it is an HA
automation ([Step 6](#step-6--ha-automation)), independent of these bindings.

> **Rebuild the binding after a canopy firmware update.** VTM36 `1.0.1r1`
> reworked the binding implementation; per Inovelli's advisory, bindings created
> before the update may silently stop firing. If the paddle goes dead after an
> update: delete **both** bindings (cluster 6 and 8) on the switch and the
> canopy, power-cycle both (breaker off ~10 s), then recreate them with the steps
> above. See [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).

## Step 5 — Hide the phantom load switch

`switch.averys_room_ceiling_fan_switch_load_control` is the switch's internal
On/Off relay. The Load terminal is empty, so this entity controls nothing —
toggling it does not touch the light (which responds to the paddle via the
binding, or to `light.averys_room_ceiling_fan_light` directly). Its state still
flips on every paddle press — that internal-relay toggle is what fires the
outgoing binding on the White series, so it has to stay that way (see the
`Control of switch load` row in Step 3). Hide it from the dashboards so nobody
taps it and concludes the install is broken, and give it the display name
"Ceiling Fan Switch Load Control" (Settings → Entities → this entity → Name)
so it reads the same across rooms — Matter's default name is the generic
"Switch (Load Control)".

## Step 6 — HA automation

One automation per room — `automation.averys_room_ceiling_fan_wall_control`
(category Climate, labels `int_inovelli_fan_canopy` + `int_inovelli_led_bar` +
`int_adaptive_lighting`). YAML lives in the `ha/` mirror. Five triggers, top-level
`choose` on which one fired:

**Config button** (`event.*_button_config`) — guarded to skip the ~8 ms
duplicate event (see design decisions), then branches on `event_type`:

| Config gesture | Fan state | Result |
|---|---|---|
| Single tap (`multi_press_1`) | off | Resume `input_select.averys_room_ceiling_fan_last_speed` |
| Single tap (`multi_press_1`) | on | Advance low → medium → high → low |
| Double tap (`multi_press_2`) | any | Off |
| Triple tap (`multi_press_3`) | any | Peek: recompute the LED bar without touching the fan |

**Paddle gestures** (`event.*_button_down` / `event.*_button_up`, trigger ids
`down_paddle` / `up_paddle`) — each branch gates on the `event_type` attribute, so
a single tap (cluster 6 binding) and a hold ramp (cluster 8 binding) fall through
to the firmware without matching an automation branch:

| Paddle gesture | Result |
|---|---|
| Double-tap down (`multi_press_2`) | `fan.turn_off` + `light.turn_off` |
| Double-tap up (`multi_press_2`) | `fan.set_percentage` to the remembered speed + `light.turn_on` (comes on at the `On level`, which Adaptive Lighting pre-stages — `guides/adaptive_lighting.md`) |
| Hold release, either paddle (`long_release`) | `adaptive_lighting.set_manual_control(true)` for the ceiling light — pins the wall-set dim level against AL's curve until the light next turns off or the 30-minute autoreset fires |

Gated on `trigger.to_state.attributes.event_type == 'long_release'`, which reads
the triggering entity, so the other paddle's stale attribute cannot match. No
de-dup guard on the double-tap branches: `mode: queued` plus idempotent actions
make a repeat `multi_press_2` a no-op.

**Fan `percentage` attribute change** (the value is already settled — no delay
needed):

1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to `input_select.*_ceiling_fan_last_speed`
   (skipped when off, so the memory survives an off/on cycle).
3. Call `script.*_ceiling_fan_led_state` to recompute the bar. See
   [Shared: LED Bar](#shared-led-bar).

**Ceiling light state change** — any change to `light.*_ceiling_fan_light`
(including one driven by the paddle binding, which HA still observes) recomputes
the LED bar via `script.*_ceiling_fan_led_state`, then:

- if the light is now **off**, calls `adaptive_lighting.set_manual_control(false)`
  to hand its brightness back to Adaptive Lighting. A single paddle down-tap turns
  the light off through the cluster 6 binding — a state change, not a
  `light.turn_off` service call — so AL's own turn-off listener never sees it;
  without this step a ceiling that was dimmed at the wall would stay manually
  controlled through an off/on.
- if the light is now **on** and not manually controlled, calls
  `adaptive_lighting.apply` with a 2s transition to snap it to the curve.
  `OnLevel` pre-staging is not reliably honored on every turn-on path, so this is
  a fast backstop rather than a redundant check — see `guides/adaptive_lighting.md`
  Step 5.

See `guides/adaptive_lighting.md` and `LESSONS.md`.

**Triple-tap peek** calls the same script, without touching the fan — a way to
force a resync on demand (normally a no-op, since the bar already reflects
current state continuously).

All five triggers carry `not_from: [unavailable, unknown]` (the `event.*` ones
also keep `not_to`). A Matter Server reconnect restores every entity on the
switch from `unavailable` to its last-held value; without the `not_from` guard
that restore transition replays the last button gesture and drives the fan. See
`LESSONS.md` → "`event` entities re-fire their trigger on every HA restart or
integration reload."

`mode: queued`, `max: 10` — runs process in order.

## Scale reference

Fan speed (VTM36 3-speed): `1–33% = low`, `34–66% = medium`, `67–100% = high`.
The automations use 33 / 66 / 100, with `< 45` / `< 78` band edges to absorb the
Matter fan's percentage rounding.

| Speed | `LED Color` |
|---|---|
| low | `Cyan` |
| medium | `Blue` |
| high | `Violet` |

Intensity levels are the [Shared: LED Bar](#shared-led-bar) pattern's, unchanged
by this device pattern: `26` by day / `3` at night while the fan is running, `3`
(day or night) for the resting locator glow, `0` dark when nobody's home.

## Replicating for another room

This setup is a per-room pattern. Avery's Room is the first instance, the
Master Bedroom the second, and the Office the third; Living Room is planned and
uses the same build. Every room is configured identically apart from the
substitutions below. To add a room, work through Steps 1–6 with these
substitutions.

**Per-room substitutions:**

| Placeholder | Avery's Room | Master Bedroom | Living Room | Office |
|---|---|---|---|---|
| Area / entity prefix | `averys_room` | `master_bedroom` | `living_room` | `office` |
| Canopy device name | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` |
| Switch device name | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` |
| Canopy Matter node | 10 | 12 | TBD | 15 |
| Switch Matter node | 11 | 13 | TBD | 16 |
| Extra day/night gate ([Shared: LED Bar](#shared-led-bar)) | `input_boolean.avery_sleeping` ORed in | none | none (assumed) | none |

Every switch uses the same presence-gates-on/off, sleep-only-dims rule — there is
no bedroom/non-bedroom classification to decide at install time any more. Only
Avery's Room ORs in a person-specific flag on top of the household
`input_boolean.everyone_sleeping`, and only because she's a child with her own
bedroom whose bedtime doesn't line up with the rest of the household's; the other
rooms use just the household boolean. A person-specific flag only ever picks
between two *dim* values (never lit vs. dark), so there's no stale-flag trap to
guard against here — no `binary_sensor.<person>_home_today` involvement needed.

**Everything else is identical across rooms** — every parameter value in Steps
2–3, the two bindings, the automation shape (one
`automation.<prefix>_ceiling_fan_wall_control`, category Climate, labels
`int_inovelli_fan_canopy` + `int_inovelli_led_bar` + `int_adaptive_lighting`,
`mode: queued` max 10, five triggers), the LED script
(`script.<prefix>_ceiling_fan_led_state`,
`mode: restart`), and the speed bands. One value is easy to get wrong and worth
re-checking per room: `Control of switch load` left at `Remote & paddle control`.

Each room gets its own copies with the prefix and any extra day/night gate
substituted:

- `automation.<prefix>_ceiling_fan_wall_control`
- `script.<prefix>_ceiling_fan_led_state`
- `input_select.<prefix>_ceiling_fan_last_speed`

`automation.household_ceiling_fan_switch_led_locator` is **shared**, not
per-room — adding a room means adding that room's presence/sleep triggers and a
dispatch branch to it, not creating a new copy. The `int_inovelli_fan_canopy` and
`int_inovelli_led_bar` labels and this guide are shared.

**Parity check.** The per-room automation and script copies must differ *only* by
the entity prefix, any extra day/night gate, the automation `id`, and the
friendly-name prefix in `alias` / `description`. After editing any room, `diff`
its `ha/` mirror against another room's to confirm nothing else diverged — any
other difference is a bug.

Per-room copies, not a blueprint: a templated `target.entity_id` in a shared
automation leaves the GUI editor showing only an inputs form, and the
household automation already covers the one piece that's genuinely shared
(presence/sleep dispatch).

## Updating the canopy firmware (1.0.1r1)

`1.0.1r1` moves the canopy's config parameters onto spec-compliant Mode Select
endpoints and reworks the Matter binding stack. Updating an already-paired canopy
leaves dead entities behind and can stop the paddle binding from firing. Per
Inovelli's update advisory (linked under [Related documents](#related-documents)),
a factory reset and re-commission are **not** required — this cleanup is enough.

1. **Back up** — Settings → System → Backups.
2. **Flash** the canopy (`update.<prefix>_ceiling_fan_firmware`); wait for it to
   reboot and settle (~2–3 min — the uptime / reboot-count sensors confirm).
3. **Restart HA** so the superseded entities re-register as `unavailable`
   ("Not provided").
4. **Delete the dead entities.** Settings → Devices & Services → Entities,
   filter Integration = Matter, search `ceiling_fan`. Remove the greyed-out
   rows — on the canopy that is the un-suffixed
   `select.<prefix>_ceiling_fan_light_mode`, `…_fan_mode`, and
   `number.<prefix>_ceiling_fan_on_off_transition_time_1`. If a row refuses to
   delete it is not actually dead — leave it. (Alt method if the filter view is
   unclear: stop the Matter Server from its add-on Web UI, restart HA, then
   delete the still-unavailable entities from the canopy's device page.)
5. **Rename the survivors** back to the clean slug —
   `select.<prefix>_ceiling_fan_light_mode_2` → `…_light_mode`,
   `…_fan_mode_2` → `…_fan_mode`, and
   `number.<prefix>_ceiling_fan_on_off_transition_time_2` →
   `…_on_off_transition_time`. Nothing in the automations references these, so
   the rename is safe.
6. **Rebuild the binding** — test the paddle first; if it does not switch the
   light cleanly, follow the rebuild callout in
   [Step 4](#step-4--matter-binding-paddle--light).
7. **Re-apply the parameters that reset.** The flash reverts Light Mode, Fan
   Mode, On level, Minimum dim level, and power-on behavior to defaults — set
   them again per [Step 2](#step-2--canopy-module-vtm36-parameters). Re-check the
   light transition-time numbers too and reset them to `0.5` s if the flash
   returned them to `2.5`.
8. **Verify**: paddle on/off; config-button speed cycle (1 tap) — the LED bar
   shows the speed's colour at day intensity (`26`) almost immediately; a config
   double-tap off returns the bar to the locator glow; the triple-tap peek
   re-asserts the current LED state without moving the fan; toggling the room's
   day/night gate drops the running-fan colour to intensity `3` (the locator
   glow is already `3` at all times); and the light riding down to `1%` on the
   HA slider without cutting out.

## Security summary

| Control | Detail |
|---|---|
| Fabric membership | Canopy (light + fan): commissioned to the Home Assistant Matter fabric; exposed to Apple Home only through the Home-Assistant-Matter-Hub add-on's bridge, so Apple commands reach it via HA's own service layer, never directly. A residual Apple Keychain fabric grant from the canopy's original direct commissioning persists in `node_diagnostics.active_fabrics` on all three rooms' canopies — Apple's Home app no longer references it (its `RemoveFabric` handshake did not complete when the direct accessory was removed), but the credential itself was never revoked and could still command the device if it were ever reused. Treated as a low-risk residual, not pursued further, since eliminating it would require a factory reset that also wipes the paddle→canopy bindings. Wall switch: unchanged — still directly commissioned to both the Home Assistant and Apple Home fabrics (multi-admin); the binding is written by HA as a fabric admin. |
| Binding scope | The paddle → light bindings are node 11 → node 10 endpoint 1 only: On/Off (cluster 6) and Level Control (cluster 8). The corresponding ACL entry on the canopy grants the switch operate (not administer) access. |
| Blast radius if the switch were compromised | It can turn the fan light on and off, change its brightness, and set the notification LED bar's colour/intensity. It has no Load, no access to other devices, and no administer rights on the canopy. |
| Local control | The switch's config-button programming menu is reachable by anyone physically present (config-button hold). This is Inovelli firmware behaviour and is not exposed over the network. |

## Related HA config

| Friendly name | Entity ID | Type |
|---|---|---|
| Avery's Room: Ceiling Fan Wall Control | `automation.averys_room_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar` + `int_adaptive_lighting`) |
| Master Bedroom: Ceiling Fan Wall Control | `automation.master_bedroom_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar` + `int_adaptive_lighting`) |
| Office: Ceiling Fan Wall Control | `automation.office_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar` + `int_adaptive_lighting`) |
| Household: Ceiling Fan Switch LED Locator | `automation.household_ceiling_fan_switch_led_locator` | Automation (Lighting, `int_inovelli_led_bar`, `scope_multi_area`, `presence`) |
| Avery's Room: Ceiling Fan LED State | `script.averys_room_ceiling_fan_led_state` | Script (`mode: restart`) |
| Master Bedroom: Ceiling Fan LED State | `script.master_bedroom_ceiling_fan_led_state` | Script (`mode: restart`) |
| Office: Ceiling Fan LED State | `script.office_ceiling_fan_led_state` | Script (`mode: restart`) |
| Avery's Room Ceiling Fan Last Speed | `input_select.averys_room_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Master Bedroom Ceiling Fan Last Speed | `input_select.master_bedroom_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Office Ceiling Fan Last Speed | `input_select.office_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Ceiling Fan | `fan.averys_room_ceiling_fan` / `light.averys_room_ceiling_fan_light` | Matter device (VTM36) |
| Ceiling Fan Switch | `event.averys_room_ceiling_fan_switch_button_config` et al. | Matter device (VTM30-SN) |

## Related files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.averys_room_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Avery's Room wall-control automation |
| `ha/automations/automation.master_bedroom_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Master Bedroom wall-control automation |
| `ha/automations/automation.office_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Office wall-control automation |
| `ha/automations/automation.household_ceiling_fan_switch_led_locator.yaml` | HA automation registry | Mirror — shared presence/sleep LED dispatch |
| `ha/scripts/script.averys_room_ceiling_fan_led_state.yaml` | HA script registry | Mirror — Avery's Room LED script |
| `ha/scripts/script.master_bedroom_ceiling_fan_led_state.yaml` | HA script registry | Mirror — Master Bedroom LED script |
| `ha/scripts/script.office_ceiling_fan_led_state.yaml` | HA script registry | Mirror — Office LED script |
| `scripts/matter_write_attribute.py` | run from a LAN machine (Mac Mini) | Reads vendor-cluster attributes HA doesn't expose; `--dump-node` / `--dump-modes` for discovery |

## Related documents

- `standards/automations.md` — automation naming, category, and label rules
- `standards/naming.md` — entity/device naming (the `avery_s` slug gotcha)
- `guides/adaptive_lighting.md` — the three ceiling fan lights' brightness curve, and the
  `On level` pre-staging that this guide's `long_release` and turn-off branches coordinate with
- `LESSONS.md` — Matter binding and VTM3x parameter gotchas (dimming speed values,
  `scene.create` inside a restart script, `light.turn_off` dropping `transition`,
  the RGB-channel colour-rendering quirk this design retired)
- "Harbor Breeze to Inovelli" work order (Claude artifact) — the physical
  retrofit and wiring
- Inovelli, "VTM35-SN & VTM36 Firmware 1.0.1r1+ Update Advisory" —
  <https://help.inovelli.com/en/articles/15454545-vtm35-sn-vtm36-firmware-1-0-1r1-update-advisory>
  (stale-entity cleanup and binding-rebuild steps)
- GitHub issue #2 — the paddle-driven LED transition flicker, tracked for
  re-testing after a firmware update

## Troubleshooting

**Paddle turns the light on at an unexpected brightness.** `On level`
(`number.*_ceiling_fan_on_level_1`) is what a binding turn-on uses.
`automation.adaptive_lighting_pre_stage` keeps it at the current Adaptive Lighting
target while the light is off (`guides/adaptive_lighting.md`); `255` is the
restore-previous sentinel and `254` is a fixed 100%. If it is stuck at the wrong
value, check that automation's last run and that the light's AL instance switch
reports a `brightness_pct` attribute. Any change takes effect on the next
off → on cycle.

**A wall-dimmed ceiling won't go back to adapting.** A binding-driven paddle off
never reaches AL as a `light.turn_off` service call, so AL's own listener can't
clear manual control from it — only this automation's "Ceiling light state
change" branch (which reacts to the light's observed state, not the call), the
30-minute autoreset, or an explicit `adaptive_lighting.set_manual_control(false)`
does. `LESSONS.md` has the mechanism.

**Paddle tap works but paddle hold doesn't dim.** Two things must both be in
place: a cluster 8 (Level Control) binding on the switch → canopy light endpoint
1 ([Step 4](#step-4--matter-binding-paddle--light)), and `Dimming Speed
(Simulated)` (`select.*_ceiling_fan_switch_dimming_speed_simulated`) set to `2s`,
not `Instant`. See `LESSONS.md`.

**Paddle double-tap does nothing (whole-room off/on).** The double-tap is an HA
automation — it does nothing with HA stopped or the automation disabled. When HA
is up, watch `event.*_ceiling_fan_switch_button_down` / `_up` in Developer Tools
while double-tapping: the `event_type` must land on `multi_press_2`. If it
reports `multi_press_1` twice instead, raise `Button Delay`
(`select.*_ceiling_fan_switch_button_delay`) to `300ms` or more.

**One config tap advances two speeds, or the resumed speed is wrong.** The
config button emits its event twice per tap; the config branch's guard condition
(`< 0.3 s since the previous config event → skip`) must be present to drop the
duplicate. If the resumed speed lands one step low, confirm the fan trigger is on
the `percentage` **attribute**, not a bare `state` trigger.

**LED bar shows the wrong colour, doesn't update, or stays dark with someone
home.** Confirm the room's day/night gate matches the per-room table under
[Replicating for another room](#replicating-for-another-room) — a room missing
`everyone_sleeping` from its `led_state` script, or Avery's Room missing the OR
against `avery_sleeping`, is the most common cause. Also check for `condition:
not` wrapping more than one sub-condition anywhere in the automation without an
explicit `and` nested inside it — that's a NOR, not a negated AND, and fails
silently (`LESSONS.md`). A brief downward-wipe visual specifically on a
**paddle** press is the known hardware quirk — see
[Known hardware quirk](#known-hardware-quirk).

**Paddle does nothing after a firmware update.** Two causes. (1) Smart Bulb Mode
reset — confirm `select.*_ceiling_fan_switch_smart_bulb_mode` still reads
`Smart Bulb Enable`; without it the paddle drives the (empty) local relay instead
of emitting the bound command. (2) The binding stopped firing — delete the
binding on both the switch and the canopy, power-cycle both, and recreate it per
[Step 4](#step-4--matter-binding-paddle--light).

**Duplicate or greyed-out config entities after a canopy firmware update.**
Expected on `1.0.1r1` — the config parameters moved to new Mode Select endpoints
and the originals are now dead. Clean them up per
[Updating the canopy firmware](#updating-the-canopy-firmware-101r1).

**Entities read `unavailable` after a Thread blip.** Power-cycle the canopy once
(breaker off ~2s, on) and wait a minute. Do not cycle repeatedly — the repeated
on/off pattern is the VTM36's factory-reset sequence and will wipe its Matter
commissioning.
