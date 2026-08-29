# Inovelli Fan Canopy

*Last updated: August 2026*

## Overview

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

Three mechanisms connect the wall switch to the fan/light:

| Function | Mechanism | Works with HA down? |
|---|---|---|
| Paddle up/down → light on/off | Matter binding (switch → canopy) | Yes |
| Config button taps → fan speed | HA automation | No |
| Fan speed → switch LED bar + speed memory | HA automation | No |

## Architecture

```
                       Avery's Room ceiling
                       ┌───────────────────────────┐
                       │  VTM36 canopy (node 10)   │
                       │   endpoint 1: light  ──────┼──► light.averys_room_ceiling_fan_light
                       │   endpoint 2: fan    ──────┼──► fan.averys_room_ceiling_fan
                       └────────▲─────────▲─────────┘
                                │         │
              Matter binding    │         │   Matter (HA-issued commands)
       (On/Off, cluster 6)      │         │
                                │         │
                       ┌────────┴─────────┴─────────┐
    wall paddle  ──────► VTM30-SN switch (node 11)  │
    config button ─────► endpoint 2: Binding cluster│
                       │  event.*_button_up/down    │──► (HA sees paddle events too, unused)
                       │  event.*_button_config     │──► automation: Ceiling Fan Speed Control
                       │  light.*_switch_led        │◄── automation: Ceiling Fan Speed Indicator
                       └────────────────────────────┘

  automation.averys_room_ceiling_fan_speed_control
      event.*_button_config  ──►  fan.set_percentage / fan.turn_off

  automation.averys_room_ceiling_fan_speed_indicator
      fan.averys_room_ceiling_fan changes  ──►  input_select.averys_room_ceiling_fan_last_speed
                                           └─►  light.averys_room_ceiling_fan_switch_led
```

**Key design decisions:**

- **The light is bound; the fan is not.** Matter binding writes the
  relationship into the switch's firmware, so paddle → light survives HA being
  offline and has no round-trip lag. Fan control has no bindable Matter cluster
  on an on/off switch (Fan Control is cluster 0x0202, which an on/off switch's
  client clusters don't map onto), so the config button must go through an HA
  automation. This split is deliberate: the everyday interaction (light on/off)
  is resilient; the fan, used less often, accepts the HA dependency.
- **Binding is On/Off only, not Level Control.** A cluster 8 (Level Control)
  binding for paddle press-and-hold dimming was tested and does not currently
  work — the paddle hold does not emit a bound Move/Step command. It was removed
  rather than left in place, because a non-functional binding could start
  behaving unpredictably after a firmware update. Dimming is HA-only for now
  (app, dashboards, automations). Revisit a Level Control binding when Inovelli
  and the matter.js server support paddle-hold dimming and it can be
  bench-verified.
- **Binding fires on physical presses only.** A command sent to the switch from
  HA or Apple Home does not propagate over the binding to the light, and bound
  state does not report back — the switch LED bar will not track light changes
  made in software. Neither matters here: the light is controlled directly via
  `light.averys_room_ceiling_fan_light`, and the LED bar is repurposed as a fan
  indicator (below).
- **Config button: taps only, never holds.** Holding the config button puts the
  VTM30-SN into its own local programming menu. An automation on the config
  button's `long_press` event would fire *and* open programming mode at the same
  time. Only `multi_press_*` events are mapped.
- **Speed memory lives in a helper, not the fan entity.** When the Matter fan is
  off, HA retains no memory of its prior speed (`percentage` reads 0,
  `preset_mode` null). `input_select.averys_room_ceiling_fan_last_speed` records
  the running speed so a config-button tap from off can resume it.
- **The LED bar is driven via its light entity, and it holds.** Setting
  `light.averys_room_ceiling_fan_switch_led` (brightness + `hs_color`) persists —
  the switch does not snap it back to a default indicator after a few seconds.
  This was verified before relying on it. If a future firmware changes that, the
  fallback is the native `LED Intensity(Off)` select plus the `LED Color`
  parameter.
- **Speed is shown by colour, not a segment fill.** Over Matter the bar is one
  RGB light — no per-segment / level-meter control (unlike the Zigbee White
  series). So the Speed Indicator automation encodes speed as hue (teal low /
  blue medium/off / violet high) and uses brightness only for the day-vs-night
  level: full when awake, dim when `input_boolean.avery_sleeping` is on. A true
  segment fill would require putting the switch in Dimmer mode and driving an
  internal level — not worth the mode change for a cosmetic gain.
- **The config button emits its event twice per physical tap** (~8 ms apart, on
  this VTM30-SN firmware / matter.js server). `automation.averys_room_ceiling_fan_speed_control`
  runs `mode: single` with `max_exceeded: silent` so the duplicate is dropped —
  otherwise one tap would advance two speed steps. Genuine separate taps are
  gated by the switch's button-press-delay window and land far enough apart to
  each get their own run.
- **The Matter fan reports `state: on` before `percentage` populates.** On the
  off → on edge, `fan.averys_room_ceiling_fan` briefly reads `percentage: 0` /
  `preset_mode: null`. `automation.averys_room_ceiling_fan_speed_indicator`
  therefore waits 1 s before reading speed, and runs `mode: restart` so only the
  settled value is stored and painted. Speed bands are widened (`< 45` = low,
  `< 78` = medium, else high) to absorb the fan's percentage rounding around
  33 / 66 / 100.

## Prerequisites

- Home Assistant with the Matter integration and a matter.js-based Matter
  Server (binding UI is standard, not beta, since the June 2026 rebuild)
- A Thread border router HA can see; both devices on the same Thread network
  (verify `sensor.*_thread_network_name` matches on both)
- Both devices commissioned to the Home Assistant Matter fabric (not only Apple
  Home) — binding must be written by an admin on the fabric, and Apple Home
  exposes no binding interface
- VTM36 firmware and VTM30-SN firmware updated to latest
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
| `light.averys_room_ceiling_fan_switch_led` | RGB indicator bar |
| `switch.averys_room_ceiling_fan_switch_load_control` | Empty Load relay — see Step 5 |

> HA's slugifier turns "Avery's" into `avery_s`, not `averys`. Every entity and
> helper created from an "Avery's Room …" name needs its ID corrected to
> `averys_room_*` afterward to match the naming standard.

The ~30 remaining VTM30-SN config selects (duplicated `_2` variants included —
an artifact of the firmware update creating a second endpoint's worth of
entities) are left with their long default IDs; nothing references them.

## Step 2 — Canopy module (VTM36) parameters

Set on the canopy device page:

| Setting | Entity | Value | Why |
|---|---|---|---|
| Light Mode | `select.averys_room_ceiling_fan_light_mode` | `Dimmer+Trailing` | The integrated LED driver cuts out at ~20% on leading edge; trailing (reverse phase) drops that to ~10%. There is no minimum-dim-level entity over Matter — ~10% is the practical floor. |
| Fan Mode | `select.averys_room_ceiling_fan_fan_mode` | `Ceiling (3 Speed)` | Matches the fan; gives HA a 3-speed `fan` entity (low 33 / medium 66 / high 100). |
| On level (endpoint 1, light) | `number.averys_room_ceiling_fan_on_level_1` | `254` | `255` is the "restore previous brightness" sentinel — an On command (paddle *or* HA) returns to the last level. `254` forces every On to 100%. The binding sends a plain On, so this is what makes paddle-up give full brightness. Trade-off: all On commands go to 100%; an explicit brightness from HA is not remembered as the on-level. |
| Power-on behavior (both endpoints) | `select.averys_room_ceiling_fan_power_on_behavior_1` / `_2` | `previous` (default) | After a breaker/mains restore, fan and light return to their prior state. The breaker is now the only disconnect for the ceiling, so this is worth setting deliberately. |
| Minimum dim level (Inovelli param 24) | *not settable on current firmware* | — | The light rides the LED driver's ~10% hardware floor. Param 24 would raise the software floor but there's no way to write it (below). |

### Inovelli parameter clusters — what's reachable

Parameters Inovelli has moved to standard Matter **Mode Select** clusters appear
in HA as `select` entities and are set normally — that covers `Light Mode`
(param 27), `Fan Mode`, and `Power-on behavior`.

The rest still live only on Inovelli's **legacy vendor cluster**
`InovelliCluster 0x122FFC31`, endpoint 1, where attribute `0x122F00NN` maps to
parameter `NN` (hex) — e.g. `0x122F0018` = parameter 24 (minimum dim).
`scripts/matter_write_attribute.py` can **read** these over the Matter Server
WebSocket API (port 5580 — expose it in the add-on's Network config first), but
**writes fail**: `write_attribute` needs a cluster schema to encode the value
and matter.js has none for this vendor cluster (`error_code 8, attribute …
unknown`). Inovelli considers the custom cluster deprecated for exactly this
lack of support.

Net effect: **minimum dim stays at the ~10% floor.** Revisit if a firmware or HA
release exposes param 24 as a Mode Select / entity. The script is kept for
reading vendor-cluster values and for any parameter Inovelli later makes
writable through a standard cluster.

## Step 3 — Switch (VTM30-SN) parameters

Set physically during the install (paddle + config taps) and confirmed in HA:

| Setting | Value | Why |
|---|---|---|
| Switch mode | Single-pole | No traveler; single-location install. (HA's `Switch Mode` select may read `unavailable` — a stale entity from a prior firmware. The physical setting stands.) |
| Smart Bulb Mode | Enabled | Keeps the switch from chasing its empty local relay — the paddle emits Matter commands (events / bindings) instead. Required for the binding to fire. `select.*_smart_bulb_mode` reads `Smart Bulb Enable`; the duplicate `_2` select is on the other endpoint and can be ignored. |
| LED bar color | Blue | Bedroom indicator. The Speed Indicator automation drives it via the light entity; the `LED Color` parameter is the fallback if the light-entity route ever stops holding. |

## Step 4 — Matter binding: paddle → light

Done in the Matter Server Web UI.

1. Open node **11** (Ceiling Fan Switch). Node IDs come from the Matter
   identifier on the device page (`deviceid_…-00000000000000NN-…`, hex).
2. Find the endpoint exposing the **Binding** cluster — **endpoint 2** on the
   VTM30-SN (endpoint 1 is the dead Load relay).
3. Add a binding target: node **10** (Ceiling Fan canopy), **endpoint 1** (the
   Dimmable Light — *not* endpoint 2, the fan), cluster **6 (On/Off)**.
4. If the UI has a separate ACL step, add an entry on node 10 granting node 11
   operate access. Most binding UIs write the ACL automatically.
5. Test at the wall: tap up → light on (full, per the On level parameter), tap
   down → light off. Confirm it still works with Home Assistant stopped.

## Step 5 — Hide the phantom load switch

`switch.averys_room_ceiling_fan_switch_load_control` is the switch's internal
On/Off relay. The Load terminal is empty, so this entity controls nothing —
toggling it does not touch the light (which responds to the paddle via the
binding, or to `light.averys_room_ceiling_fan_light` directly). Hide it from the
dashboards so nobody taps it and concludes the install is broken.

## Step 6 — HA automations

Two automations, both category Climate, both labelled `int_inovelli_fan_canopy`.
YAML lives in the `ha/` mirror; behaviour summary:

### Ceiling Fan Speed Control (`automation.averys_room_ceiling_fan_speed_control`)

Trigger: any change on `event.averys_room_ceiling_fan_switch_button_config`
(guarded against `unavailable`/`unknown`). Branches on the `event_type`
attribute:

| Config gesture | Fan state | Result |
|---|---|---|
| Single tap (`multi_press_1`) | off | Resume `input_select.averys_room_ceiling_fan_last_speed` |
| Single tap (`multi_press_1`) | on | Advance low → medium → high → low |
| Double tap (`multi_press_2`) | any | Off |

`mode: single`, `max_exceeded: silent` — drops the duplicate event the config
button emits per tap (see design decisions).

### Ceiling Fan Speed Indicator (`automation.averys_room_ceiling_fan_speed_indicator`)

Triggers: any change on `fan.averys_room_ceiling_fan`, or on
`input_boolean.avery_sleeping` (so the bar re-dims at bedtime). Actions:

0. Wait 1 s for the Matter fan to settle (`percentage` lags `state`).
1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to
   `input_select.averys_room_ceiling_fan_last_speed`. Skipped when off, so the
   memory survives an off/on cycle.
3. Paint `light.averys_room_ceiling_fan_switch_led`: hue by speed, brightness by
   time of day (see Scale reference).

`mode: restart` — a rapid sequence of changes resets the settle wait and only
the final value is stored and painted.

## Scale reference

Fan speed (VTM36 3-speed): `1–33% = low`, `34–66% = medium`, `67–100% = high`.
The automations use 33 / 66 / 100, with `< 45` / `< 78` band edges to absorb the
Matter fan's percentage rounding.

LED bar — hue carries the speed, brightness carries day vs. night (starting
points, tune against the dark room):

| Fan speed | Hue (`hs_color`) |
|---|---|
| off | 220 (blue) |
| low | 175 (teal) |
| medium | 220 (blue) |
| high | 265 (violet) |

| `input_boolean.avery_sleeping` | Fan off | Fan on |
|---|---|---|
| off (awake) | 12% | 55% |
| on (sleeping) | 5% | 20% |

## Replicating for another room

This setup is a per-room pattern. Avery's Room is the first instance; the Master
Bedroom is the second, and both are meant to be configured identically. To add a
room, work through Steps 1–6 with these substitutions and keep every parameter
value the same.

**Per-room substitutions:**

| Placeholder | Avery's Room | Master Bedroom |
|---|---|---|
| Area / entity prefix | `averys_room` | `master_bedroom` |
| Canopy device name | `Ceiling Fan` | `Ceiling Fan` |
| Switch device name | `Ceiling Fan Switch` | `Ceiling Fan Switch` |
| Canopy Matter node | 10 | *(read from device page)* |
| Switch Matter node | 11 | *(read from device page)* |
| Sleep boolean (Indicator trigger + night dim) | `input_boolean.avery_sleeping` | `input_boolean.everyone_sleeping` (no MBR-specific toggle; household sleep ≈ parents in bed) |

**Identical across every room — do not vary:**

- Canopy: `Light Mode` = `Dimmer+Trailing`; `Fan Mode` = `Ceiling (3 Speed)`;
  `On level` (light endpoint) = `254`; power-on behaviour = `previous`
  (minimum dim / param 24 is not settable — see above)
- Switch: Single-pole; Smart Bulb Mode enabled; LED colour Blue
- Binding: switch Binding endpoint → canopy light endpoint, cluster **6 only**
  (no cluster 8 — paddle-hold dimming is left out until it works)
- Both automations: category Climate, label `int_inovelli_fan_canopy`,
  `mode: single` (Speed Control) / `mode: restart` (Speed Indicator)
- Speed bands 33 / 66 / 100 with `< 45` / `< 78` edges; LED hues 175 / 220 / 265;
  brightness 12/55 awake, 5/20 sleeping

Each room gets its own helper (`input_select.<prefix>_ceiling_fan_last_speed`)
and its own copy of both automations with the prefix substituted. The
`int_inovelli_fan_canopy` label and this guide are shared.

## Security summary

| Control | Detail |
|---|---|
| Fabric membership | Both devices are commissioned to the Home Assistant Matter fabric and the Apple Home fabric (multi-admin). The binding is written by HA as a fabric admin. |
| Binding scope | The paddle → light binding is a single On/Off relationship, node 11 → node 10 endpoint 1. The corresponding ACL entry on the canopy grants the switch operate (not administer) access. |
| Blast radius if the switch were compromised | It can turn the fan light on and off. It has no Load, no access to other devices, and no administer rights on the canopy. |
| Local control | The switch's config-button programming menu is reachable by anyone physically present (config-button hold). This is Inovelli firmware behaviour and is not exposed over the network. |

## Related HA config

| Friendly name | Entity ID | Type |
|---|---|---|
| Avery's Room: Ceiling Fan Speed Control | `automation.averys_room_ceiling_fan_speed_control` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Avery's Room: Ceiling Fan Speed Indicator | `automation.averys_room_ceiling_fan_speed_indicator` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Avery's Room Ceiling Fan Last Speed | `input_select.averys_room_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Ceiling Fan | `fan.averys_room_ceiling_fan` / `light.averys_room_ceiling_fan_light` | Matter device (VTM36) |
| Ceiling Fan Switch | `event.averys_room_ceiling_fan_switch_button_config` et al. | Matter device (VTM30-SN) |

## Related files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.averys_room_ceiling_fan_speed_control.yaml` | HA automation registry | Mirror of the config-button automation |
| `ha/automations/automation.averys_room_ceiling_fan_speed_indicator.yaml` | HA automation registry | Mirror of the LED / speed-memory automation |
| `scripts/matter_write_attribute.py` | run from a LAN machine (Mac Mini) | Writes vendor-cluster attributes HA doesn't expose — used for the canopy minimum-dim parameter |

## Related documents

- `standards/automations.md` — automation naming, category, and label rules
- `standards/naming.md` — entity/device naming (the `avery_s` slug gotcha)
- `LESSONS.md` — Matter binding and VTM3x parameter gotchas
- "Harbor Breeze to Inovelli" work order (Claude artifact) — the physical
  retrofit and wiring

## Troubleshooting

**Paddle turns the light on at the last brightness instead of full.**
`number.averys_room_ceiling_fan_on_level_1` is at `255` (the restore-previous
sentinel). Set it to `254`. The change takes effect on the next off → on cycle.

**Light still cuts out at low brightness.** Expected below ~10% — the integrated
LED driver's minimum conduction level. `Dimmer+Trailing` already lowered it from
~20%. Inovelli parameter 24 (minimum dim) would raise the floor further but is
not writable — see [Inovelli parameter clusters](#inovelli-parameter-clusters--whats-reachable).
~10% is the working floor.

**One config tap advances two speeds, or the resumed speed is wrong.** The
config button emits its event twice per tap. `automation.averys_room_ceiling_fan_speed_control`
must be `mode: single` (not `queued`) so the duplicate is dropped. Separately,
if the resumed speed lands one step low, the Speed Indicator automation read
`percentage` before the fan settled and stored a stale band — confirm its 1 s
settle delay is present.

**Config-button double-tap doesn't turn the fan off.** Check the
`event.*_button_config` entity's `event_type` attribute in Developer Tools while
pressing — if a double-tap reports `multi_press_1` twice rather than
`multi_press_2`, the switch's button-press delay is set too short. Raise it via
the `Button Press Delay` / `Button Delay` select on the switch.

**LED bar stops tracking fan speed.** If a firmware update makes the switch snap
the LED back to its default indicator after `light.turn_on`, switch the Speed
Indicator automation from `light.averys_room_ceiling_fan_switch_led` to the
native `LED Intensity(Off)` select (blue is already the parameter colour).

**Paddle does nothing after a firmware update.** Confirm Smart Bulb Mode is still
enabled on the switch — a firmware update can reset it, and without it the paddle
drives the (empty) local relay instead of emitting the bound command. Re-check
the binding still lists node 10 / endpoint 1 / cluster 6.

**Entities read `unavailable` after a Thread blip.** Power-cycle the canopy once
(breaker off ~2s, on) and wait a minute. Do not cycle repeatedly — the repeated
on/off pattern is the VTM36's factory-reset sequence and will wipe its Matter
commissioning.
