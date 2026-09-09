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

### Bedroom vs. non-bedroom classification

**A per-switch decision made at install time: does anyone sleep in this room?** It changes
what the resting state depends on.

| | Bedroom | Non-bedroom |
|---|---|---|
| Gate | Presence **and** awake | Presence only |
| Example | Master Bedroom, Avery's Room | Office |
| Rationale | A persistent glow next to someone trying to sleep is worse than the brief flash it replaces — the fan is often left running overnight for white noise | Nobody sleeps here; someone up at night benefits from the glow, and there's no one to disturb |

A bedroom switch may also carry a **person-specific** sleep flag layered on top of the
household one — see Avery's Room in the per-room table under
[Replicating for another room](#replicating-for-another-room) for the worked example,
including the stale-flag trap: a personal sleep boolean must be ignored once that person
hasn't been home for a while, via a paired `binary_sensor.<person>_home_today`, or it holds
the room dark indefinitely while they're away. That sensor flips at the calendar-day
boundary, not at the moment the person actually leaves, so gate on it having read `off` for a
**minimum duration** (`for: "08:00:00"` for Avery, matched to her routine — everyone in the
house is up by ~7-8am on any day she's here) rather than instantaneously — otherwise a
midnight rollover neutralizes the flag while she's still asleep, and someone else waking
early enough to clear the household sleep boolean would light her room to full brightness.

### Resting-state script pattern

Two scripts per switch, both `mode: restart`, neither taking any parameters — everything is
read from live state:

- **`script.<prefix>_..._led_state`** — idempotent. Recomputed from scratch on every call, so
  there is no snapshot and none of the `scene.create` failure modes a snapshot/restore
  approach would carry (captured mid-transition, or suppressing the next colour command —
  `LESSONS.md`). Resolves to one of: an "active" colour at a device-pattern-defined
  intensity while home-awake, a locator glow (`White` @ intensity `3`) while home-awake and
  otherwise idle, or dark. Every `select.select_option` call is guarded to skip when the
  target already holds the desired value.
- **`script.<prefix>_..._led_blip_dim`** — the one genuinely transient piece: a ~2s flash at
  intensity `8` when something changes while the switch is *not* home-awake, then dark. No
  animation, no "last value" memory — it reads current state and flashes that.

A **household gating automation** (`automation.household_ceiling_fan_switch_led_locator` for
the current canopy-paired switches) reacts to presence and sleep-boolean changes and calls
`led_state` for each affected switch — or `led_blip_dim` instead, when a change that newly
makes a switch not-home-awake fires while that switch's "active" condition is already true
(one flash to acknowledge, then dark, rather than an abrupt silent cut). Which switches a
given trigger affects depends on their bedroom/non-bedroom classification — a household sleep
boolean never touches a non-bedroom switch's dispatch at all.

### What's device-pattern-specific

This section deliberately says nothing about *what* the "active" colour is or what makes a
switch "active" — that's supplied by whatever the switch controls. The Ceiling Fan Canopy
pattern's addition is exactly one thing: map the fan's current speed onto a colour. A future
canopy-less switch would have no "active" branch at all — just the locator glow and dark.

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

Five mechanisms connect the wall switch to the fan/light:

| Function | Mechanism | Works with HA down? |
|---|---|---|
| Paddle tap up/down → light on/off | Matter binding, cluster 6 (switch → canopy) | Yes |
| Paddle hold up/down → light dim up/down | Matter binding, cluster 8 (switch → canopy) | Yes |
| Paddle double-tap down → fan + light off; double-tap up → fan on (last speed) + light on | HA automation | No |
| Config button taps → fan speed (1 tap cycle, 2 taps off, 3 taps peek) | HA automation | No |
| Fan/light state change → switch LED bar update | HA automation ([Shared: LED Bar](#shared-led-bar)) | No |

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
                       │  select.*_switch_led_*      │◄── script.<prefix>_ceiling_fan_led_state /
                       └────────────────────────────┘     _led_blip_dim (Shared: LED Bar)

  automation.<prefix>_ceiling_fan_wall_control   (one automation, five triggers)
      event.*_button_config        ──►  fan.set_percentage / fan.turn_off   (1 / 2 taps)
                                   └─►  LED dispatch                        (3 taps: peek)
      event.*_button_down (multi_press_2) ─►  fan.turn_off + light.turn_off
      event.*_button_up   (multi_press_2) ─►  fan.set_percentage (last speed) + light.turn_on
      fan.<prefix>_ceiling_fan      ──►  input_select.<prefix>_ceiling_fan_last_speed
                                   └─►  LED dispatch (script.<prefix>_ceiling_fan_led_state
                                        or _led_blip_dim, by home-awake gate)
      light.<prefix>_ceiling_fan_light ─► LED dispatch (script.<prefix>_ceiling_fan_led_state)
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
  the bar is canopy-specific.** Everything else (the resting-state/blip-dim script
  pattern, the bedroom/non-bedroom gate, the household dispatch automation) is
  the [Shared: LED Bar](#shared-led-bar) pattern, unmodified.

- **The LED bar reacts to settled state, not button presses.** With no per-change
  animation to time precisely, dispatching from the button-gesture branches ahead
  of the fan's own Matter round-trip would only add complexity for no visible
  benefit. Every LED update comes from the `fan.percentage` and
  `light.<prefix>_ceiling_fan_light` state triggers alone, reacting within the
  fan's normal ~0.3–0.6s settle time. The button-gesture branches contain no LED
  code at all.

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
| `light.averys_room_ceiling_fan_switch_led` | RGB indicator bar (unused - see Shared: LED Bar) |
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
  `…_led_effect`, and the `light.<prefix>_ceiling_fan_switch_led` bar.

Only the `select.<prefix>_ceiling_fan_switch_led_*` entities (colour, intensity
on/off, effect) are referenced by config — the LED scripts drive them, see
[Shared: LED Bar](#shared-led-bar) — so if any of their slugs change, update
`script.<prefix>_ceiling_fan_led_state` / `_led_blip_dim` and their `ha/` mirrors
in the same pass. The rest are config entities nothing depends on, so those
renames are safe on their own. The Office device carries a **stale duplicate**
entity set at a different Matter endpoint (`select.office_matter_thread_on_off_switch_vtm30_sn_*`)
left over from before its clean rename — nothing references it, but don't
mistake it for the canonical one when troubleshooting.

## Step 2 — Canopy module (VTM36) parameters

Set on the canopy device page (entity IDs assume the `1.0.1r1` layout and the
post-update rename — see [Step 1](#step-1--device-and-entity-naming)):

| Setting | Entity | Value | Why |
|---|---|---|---|
| Light Mode | `select.averys_room_ceiling_fan_light_mode` | `Trailing Dimmer` | The integrated LED driver cuts out at ~20% on leading edge; trailing (reverse phase) drops that to ~10%, and Minimum dim level (below) then pins a clean floor. |
| Fan Mode | `select.averys_room_ceiling_fan_fan_mode` | `Ceiling (3 Speed)` | Matches the fan; gives HA a 3-speed `fan` entity (low 33 / medium 66 / high 100). |
| Minimum dim level | `select.averys_room_ceiling_fan_ligh_min_level` | `13%` | Lowest step that holds without the driver dropping the light; `1%` on the HA brightness slider maps to this floor. (Friendly name reads "Ligh Min Level" — an Inovelli typo.) |
| Maximum dim level | `select.averys_room_ceiling_fan_ligh_max_level` | `100%` (default) | Leave at 100 unless a fixture needs a cap. |
| On level (endpoint 1, light) | `number.averys_room_ceiling_fan_on_level_1` | `254` | `255` is the "restore previous brightness" sentinel — an On command (paddle *or* HA) returns to the last level. `254` forces every On to 100%. The binding sends a plain On, so this is what makes paddle-up give full brightness. Trade-off: all On commands go to 100%; an explicit brightness from HA is not remembered as the on-level. |
| Power-on behavior (both endpoints) | `select.averys_room_ceiling_fan_power_on_behavior_1` / `_2` | `previous` (default) | After a breaker/mains restore, fan and light return to their prior state. The breaker is now the only disconnect for the ceiling, so this is worth setting deliberately. |
| Fan Min / Max Speed | `select.averys_room_ceiling_fan_fan_min_speed` / `_fan_max_speed` | `Low` / `High` (default) | Full range; leave unless a fan needs a narrower band. |
| Light transition time (On / Off / On-Off) | `number.averys_room_ceiling_fan_on_transition_time`, `…_off_transition_time`, `…_on_off_transition_time` | `0.5` s (all three) | Factory default is 2.5 s — a slow mood-fade that feels wrong on a bedroom light next to the ~0.4–1 s fade of the Hue / IKEA bulbs elsewhere. Set all three: HA on/off and some command paths read the combined `On/Off` value; the split `On` / `Off` pair covers the rest and takes precedence when set. Because `light.turn_off` drops any `transition:` HA passes (see `LESSONS.md`), these numbers are what actually control the fade. |

Leave `Fan Breeze Mode` (`Off`) and `FanQuick Start` (`Quick Start Disable`) at
their defaults.

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
| `LED Color`, `LED Intensity(On)` / `(Off)`, `LED Effect` | Automation-managed — see [Shared: LED Bar](#shared-led-bar) | Not set once and left; `script.<prefix>_ceiling_fan_led_state` / `_led_blip_dim` write these continuously in response to fan/light/presence/sleep state. Nothing about them is a fixed installer setting on this device. |

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
6. Test at the wall: tap up → light on (full, per the On level parameter), tap
   down → light off; hold up → smooth ramp up, hold down → ramp down, release →
   stop mid-ramp. Confirm all of it still works with Home Assistant stopped.

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
taps it and concludes the install is broken.

## Step 6 — HA automation

One automation per room — `automation.averys_room_ceiling_fan_wall_control`
(category Climate, labels `int_inovelli_fan_canopy` + `int_inovelli_led_bar`).
YAML lives in the `ha/` mirror. Five triggers, top-level `choose` on which one
fired:

**Config button** (`event.*_button_config`) — guarded to skip the ~8 ms
duplicate event (see design decisions), then branches on `event_type`:

| Config gesture | Fan state | Result |
|---|---|---|
| Single tap (`multi_press_1`) | off | Resume `input_select.averys_room_ceiling_fan_last_speed` |
| Single tap (`multi_press_1`) | on | Advance low → medium → high → low |
| Double tap (`multi_press_2`) | any | Off |
| Triple tap (`multi_press_3`) | any | Peek: dispatch an LED update without touching the fan |

**Paddle double-tap** (`event.*_button_down` / `event.*_button_up`) — each branch
fires on the entity changing and gates on its `event_type` attribute being
`multi_press_2`, so a single tap (cluster 6 binding) or a hold (cluster 8
binding) on the same paddle doesn't match:

| Paddle gesture | Result |
|---|---|
| Double-tap down (`multi_press_2`) | `fan.turn_off` + `light.turn_off` |
| Double-tap up (`multi_press_2`) | `fan.set_percentage` to the remembered speed + `light.turn_on` (full, per On level 254) |

No de-dup guard: `mode: queued` plus idempotent actions make a repeat
`multi_press_2` a no-op.

**Fan `percentage` attribute change** (the value is already settled — no delay
needed):

1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to `input_select.*_ceiling_fan_last_speed`
   (skipped when off, so the memory survives an off/on cycle).
3. Dispatch the LED update: if the fan is on and the switch is not currently
   home-awake, call `script.*_ceiling_fan_led_blip_dim`; otherwise call
   `script.*_ceiling_fan_led_state`. See [Shared: LED Bar](#shared-led-bar).

**Ceiling light state change** — any change to `light.*_ceiling_fan_light`
(including one driven by the paddle binding, which HA still observes) calls
`script.*_ceiling_fan_led_state` to recompute the bar.

**Triple-tap peek** dispatches the same way as the fan-settled branch, without
touching the fan — a way to check the bar's state on demand.

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
by this device pattern: `50` while home-awake and the fan is running, `3` for the
resting locator glow, `8` for the away/asleep acknowledgement flash, `0` dark.

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
| Room classification ([Shared: LED Bar](#shared-led-bar)) | Bedroom | Bedroom | Bedroom (assumed) | Non-bedroom |
| Sleep gate | `input_boolean.everyone_sleeping` **and** `input_boolean.avery_sleeping` (ignored once `binary_sensor.avery_home_today` has read off for 8+ continuous hours) | `input_boolean.everyone_sleeping` | `input_boolean.everyone_sleeping` (assumed) | none |

Only Avery's Room has a person-specific sleep toggle, and only because she's a
child with her own bedroom; the other bedrooms use just the household
`input_boolean.everyone_sleeping`. The stale-flag trap her room works around —
a personal sleep boolean holding a room dark on a day that person isn't home —
only applies to a person-specific gate, not the household one.

**Everything else is identical across rooms** — every parameter value in Steps
2–3, the two bindings, the automation shape (one
`automation.<prefix>_ceiling_fan_wall_control`, category Climate, labels
`int_inovelli_fan_canopy` + `int_inovelli_led_bar`, `mode: queued` max 10, five
triggers), the two LED scripts (`script.<prefix>_ceiling_fan_led_state`,
`_led_blip_dim`, both `mode: restart`), and the speed bands. Two values are easy
to get wrong and worth re-checking per room: `Control of switch load` left at
`Remote & paddle control`, and the room's classification (bedroom vs.
non-bedroom) decided *before* writing the LED scripts, since it changes which
conditions their `choose` blocks carry.

Each room gets its own copies with the prefix, sleep gate, and classification
substituted:

- `automation.<prefix>_ceiling_fan_wall_control`
- `script.<prefix>_ceiling_fan_led_state`
- `script.<prefix>_ceiling_fan_led_blip_dim`
- `input_select.<prefix>_ceiling_fan_last_speed`

`automation.household_ceiling_fan_switch_led_locator` is **shared**, not
per-room — adding a room means adding that room's triggers and dispatch branch
to it, not creating a new copy. The `int_inovelli_fan_canopy` and
`int_inovelli_led_bar` labels and this guide are shared.

**Parity check.** The per-room automation and script copies must differ *only* by
the entity prefix, the sleep gate, the room classification, the automation `id`,
and the friendly-name prefix in `alias` / `description`. After editing any room,
`diff` its `ha/` mirror against another room's to confirm nothing else diverged
— any other difference is a bug.

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
   shows the speed's colour at full (home-awake) intensity almost immediately;
   a config double-tap off returns the bar to its resting state; the triple-tap
   peek re-asserts the current LED state without moving the fan; a change made
   while the room's sleep gate is active shows the dim (intensity 8)
   acknowledgement instead; and the light riding down to `1%` on the HA slider
   without cutting out.

## Security summary

| Control | Detail |
|---|---|
| Fabric membership | Both devices are commissioned to the Home Assistant Matter fabric and the Apple Home fabric (multi-admin). The binding is written by HA as a fabric admin. |
| Binding scope | The paddle → light bindings are node 11 → node 10 endpoint 1 only: On/Off (cluster 6) and Level Control (cluster 8). The corresponding ACL entry on the canopy grants the switch operate (not administer) access. |
| Blast radius if the switch were compromised | It can turn the fan light on and off, change its brightness, and set the notification LED bar's colour/intensity. It has no Load, no access to other devices, and no administer rights on the canopy. |
| Local control | The switch's config-button programming menu is reachable by anyone physically present (config-button hold). This is Inovelli firmware behaviour and is not exposed over the network. |

## Related HA config

| Friendly name | Entity ID | Type |
|---|---|---|
| Avery's Room: Ceiling Fan Wall Control | `automation.averys_room_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar`) |
| Master Bedroom: Ceiling Fan Wall Control | `automation.master_bedroom_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar`) |
| Office: Ceiling Fan Wall Control | `automation.office_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy` + `int_inovelli_led_bar`) |
| Household: Ceiling Fan Switch LED Locator | `automation.household_ceiling_fan_switch_led_locator` | Automation (Lighting, `int_inovelli_led_bar`, `scope_multi_area`, `presence`) |
| Avery's Room: Ceiling Fan LED State / LED Blip (dim) | `script.averys_room_ceiling_fan_led_state` / `_led_blip_dim` | Scripts (`mode: restart`) |
| Master Bedroom: Ceiling Fan LED State / LED Blip (dim) | `script.master_bedroom_ceiling_fan_led_state` / `_led_blip_dim` | Scripts (`mode: restart`) |
| Office: Ceiling Fan LED State / LED Blip (dim) | `script.office_ceiling_fan_led_state` / `_led_blip_dim` | Scripts (`mode: restart`) |
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
| `ha/scripts/script.averys_room_ceiling_fan_led_state.yaml` / `_led_blip_dim.yaml` | HA script registry | Mirror — Avery's Room LED scripts |
| `ha/scripts/script.master_bedroom_ceiling_fan_led_state.yaml` / `_led_blip_dim.yaml` | HA script registry | Mirror — Master Bedroom LED scripts |
| `ha/scripts/script.office_ceiling_fan_led_state.yaml` / `_led_blip_dim.yaml` | HA script registry | Mirror — Office LED scripts |
| `scripts/matter_write_attribute.py` | run from a LAN machine (Mac Mini) | Reads vendor-cluster attributes HA doesn't expose; `--dump-node` / `--dump-modes` for discovery |

## Related documents

- `standards/automations.md` — automation naming, category, and label rules
- `standards/naming.md` — entity/device naming (the `avery_s` slug gotcha)
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

**Paddle turns the light on at the last brightness instead of full.**
`number.averys_room_ceiling_fan_on_level_1` is at `255` (the restore-previous
sentinel). Set it to `254`. The change takes effect on the next off → on cycle.

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

**LED bar shows the wrong colour, doesn't update, or won't go dark.** Confirm
the room's classification and sleep gate match what [Shared: LED Bar](#shared-led-bar)
and the per-room table under [Replicating for another room](#replicating-for-another-room)
say they should be — a bedroom room accidentally missing its sleep condition (or
a non-bedroom room carrying one it shouldn't) is the most common cause. If the
bar is stuck at intensity 8 or mid-transition, the blip-dim script was
restarted and killed before its tail — clear it by hand:
`select.select_option` both intensity entities to `0`; the next fan or light
change corrects it. A brief downward-wipe visual specifically on a **paddle**
press is the known hardware quirk — see [Known hardware quirk](#known-hardware-quirk).

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
