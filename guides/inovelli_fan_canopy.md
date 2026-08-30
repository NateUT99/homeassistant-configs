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
                       │  event.*_button_config     │──► automation: Ceiling Fan Wall Control
                       │  light.*_switch_led        │◄── automation: Ceiling Fan Wall Control
                       └────────────────────────────┘

  automation.averys_room_ceiling_fan_wall_control   (one automation, three triggers)
      event.*_button_config           ──►  fan.set_percentage / fan.turn_off
      fan.averys_room_ceiling_fan     ──►  input_select.averys_room_ceiling_fan_last_speed
      input_boolean.avery_sleeping    └─►  light.averys_room_ceiling_fan_switch_led
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
  binding for paddle press-and-hold dimming was tested on both stock `1.0.0` and
  beta `1.0.1r1` canopy firmware and does not work — the paddle hold does not
  emit a bound Move/Step command. It was removed rather than left in place,
  because a non-functional binding could start behaving unpredictably after a
  firmware update. Dimming is HA-only for now (app, dashboards, automations).
  Revisit a Level Control binding when Inovelli and the matter.js server support
  paddle-hold dimming and it can be bench-verified.
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
- **One automation per room, not two.** `automation.<prefix>_ceiling_fan_wall_control`
  carries all three non-binding links (config button, fan → LED/memory, sleep →
  LED) on three triggers with a top-level `choose` on `condition: trigger id`.
  This keeps every room a single reviewable unit and the behaviour identical
  across rooms. `mode: queued` (max 10) so fan-change repaints process in order
  and last wins.
- **Bar off when the fan is off; colour by speed when it's running.** Over Matter
  the bar is one RGB light — no per-segment / level-meter control (unlike the
  Zigbee White series). Running speed is encoded as hue (teal low / blue medium /
  violet high); brightness carries only day-vs-night (full awake, dim when the
  room's sleep boolean is on). Fan off → `light.turn_off` plus `LED Intensity(Off)`
  = 0 so the resting state is dark in every path. A true segment fill would
  require putting the switch in Dimmer mode and driving an internal level — not
  worth the mode change for a cosmetic gain.
- **The config button emits its event twice per physical tap** (~8 ms apart, on
  this VTM30-SN firmware / matter.js server). Because `mode: queued` can't drop
  the duplicate, the config branch carries a guard condition: skip the run when
  less than 0.3 s separates this config-event state from the previous one.
  Genuine separate taps are gated by the switch's button-press-delay window and
  land far enough apart to each get their own run.
- **The Matter fan reports `state: on` before `percentage` populates**, so the
  fan trigger is a `state` trigger on the **`percentage` attribute** — it only
  fires once the value is real, no settle delay needed. (An earlier version used
  a bare `state` trigger plus a 1 s delay; under `mode: queued` those delayed
  runs piled up and every LED repaint read the *final* speed, so the bar stuck
  on one colour. Triggering on the attribute drains the queue fast and each
  repaint reads its own speed.) Bands are widened (`< 45` = low, `< 78` =
  medium, else high) to absorb the fan's percentage rounding around 33 / 66 / 100.

## Prerequisites

- Home Assistant with the Matter integration and a matter.js-based Matter
  Server (binding UI is standard, not beta, since the June 2026 rebuild)
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
| `light.averys_room_ceiling_fan_switch_led` | RGB indicator bar |
| `switch.averys_room_ceiling_fan_switch_load_control` | Empty Load relay — see Step 5 |

> HA's slugifier turns "Avery's" into `avery_s`, not `averys`. Every entity and
> helper created from an "Avery's Room …" name needs its ID corrected to
> `averys_room_*` afterward to match the naming standard.

**Duplicate config entities.** A firmware change that moves config parameters
onto spec-compliant Mode Select endpoints leaves the pre-change entities behind
as dead duplicates: they read `unavailable` (`restored`) after an HA restart and
a fresh entity (often `…_2`-suffixed) carries the live value. On the VTM36 this
is firmware `1.0.1r1`; on the VTM30-SN it dates to the June 2026 matter.js
rebuild. For the canopy, delete the dead originals and rename the survivors back
to the clean slug — `select.<prefix>_ceiling_fan_light_mode` and `_fan_mode` —
per [Updating the canopy firmware](#updating-the-canopy-firmware-101r1). The
VTM30-SN's own dead duplicates are left as-is (the live copies keep their `_2`
suffix); nothing references them.

## Step 2 — Canopy module (VTM36) parameters

Set on the canopy device page (entity IDs assume the `1.0.1r1` layout and the
post-update rename — see [Step 1](#step-1--device-and-entity-naming)):

| Setting | Entity | Value | Why |
|---|---|---|---|
| Light Mode | `select.averys_room_ceiling_fan_light_mode` | `Trailing Dimmer` | The integrated LED driver cuts out at ~20% on leading edge; trailing (reverse phase) drops that to ~10%, and Minimum dim level (below) then pins a clean floor. (`1.0.1r1` renamed the option from `Dimmer+Trailing` to `Trailing Dimmer`.) |
| Fan Mode | `select.averys_room_ceiling_fan_fan_mode` | `Ceiling (3 Speed)` | Matches the fan; gives HA a 3-speed `fan` entity (low 33 / medium 66 / high 100). |
| Minimum dim level | `select.averys_room_ceiling_fan_ligh_min_level` | `13%` | New on `1.0.1r1` as a real Mode Select — the parameter that was unreachable on `1.0.0`. `13%` is the lowest step that holds without the driver dropping the light; `1%` on the HA brightness slider now maps to this floor instead of cutting out. (Friendly name reads "Ligh Min Level" — an Inovelli typo.) |
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
| Smart Bulb Mode | Enabled | Keeps the switch from chasing its empty local relay — the paddle emits Matter commands (events / bindings) instead. Required for the binding to fire. The live entity is `select.*_smart_bulb_mode_2` = `Smart Bulb Enable`; the un-suffixed `_smart_bulb_mode` is the dead pre-June-2026 duplicate. Same pattern for `LED Color` (`_2` live). |
| LED bar color | Blue | Bedroom indicator. The wall-control automation drives it via the light entity; the `LED Color` parameter is the fallback if the light-entity route ever stops holding. |
| `LED Intensity(On)` **and** `LED Intensity(Off)` | `0` | The switch keeps an internal on/off state (toggled by the paddle even in Smart Bulb Mode) and lights the bar to `LED Intensity(On)` / `(Off)` for it. Zeroing both means that native indicator never shows, so the bar reflects *only* the fan-speed automation and the paddle (light on/off) doesn't touch it. Each is exposed **twice** — a **select** and a `… (Load Control)` **number** — set all four to `0` per switch. The two `(Load Control)` numbers occasionally re-read their factory defaults (`33` / `1`) after a Matter Server restart; re-zero them if the bar starts glowing faintly at rest. The automation drives the bar through a separate RGB-notification channel that still works with the intensities at 0. |

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

> **Rebuild the binding after a canopy firmware update.** VTM36 `1.0.1r1`
> reworked the binding implementation; per Inovelli's advisory, bindings created
> before the update may silently stop firing. If the paddle goes dead after an
> update: delete the binding on **both** the switch and the canopy, power-cycle
> both (breaker off ~10 s), then recreate it with the steps above. See
> [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).

## Step 5 — Hide the phantom load switch

`switch.averys_room_ceiling_fan_switch_load_control` is the switch's internal
On/Off relay. The Load terminal is empty, so this entity controls nothing —
toggling it does not touch the light (which responds to the paddle via the
binding, or to `light.averys_room_ceiling_fan_light` directly). Hide it from the
dashboards so nobody taps it and concludes the install is broken.

## Step 6 — HA automation

One automation per room — `automation.averys_room_ceiling_fan_wall_control`
(category Climate, label `int_inovelli_fan_canopy`). YAML lives in the `ha/`
mirror. Three triggers, top-level `choose` on which one fired:

**Config button** (`event.*_button_config`) — guarded to skip the ~8 ms
duplicate event (see design decisions), then branches on `event_type`:

| Config gesture | Fan state | Result |
|---|---|---|
| Single tap (`multi_press_1`) | off | Resume `input_select.averys_room_ceiling_fan_last_speed` |
| Single tap (`multi_press_1`) | on | Advance low → medium → high → low |
| Double tap (`multi_press_2`) | any | Off |

**Fan `percentage` attribute change or sleep toggle** (triggering on the
attribute means the value is already settled — no delay):

1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to `input_select.*_ceiling_fan_last_speed`
   (skipped when off, so the memory survives an off/on cycle).
3. Sync `light.*_ceiling_fan_switch_led`: fan off → `light.turn_off`; fan
   running → hue by speed, brightness by time of day (see Scale reference).

`mode: queued`, `max: 10` — repaints process in order, last wins.

## Scale reference

Fan speed (VTM36 3-speed): `1–33% = low`, `34–66% = medium`, `67–100% = high`.
The automations use 33 / 66 / 100, with `< 45` / `< 78` band edges to absorb the
Matter fan's percentage rounding.

LED bar — **off entirely when the fan is off**; when the fan is running, hue
carries the speed and brightness carries day vs. night:

| Fan | Hue (`hs_color`) | Brightness (awake / sleeping) |
|---|---|---|
| off | — (bar off) | — |
| low | 175 (teal) | 55% / 20% |
| medium | 220 (blue) | 55% / 20% |
| high | 265 (violet) | 55% / 20% |

"Bar off when fan off" needs two things: the automation's fan-off branch does
`light.turn_off`, **and** the switch's `LED Intensity(Off)` param is set to `0`
so the native fallback (HA down, or notification cleared) is also dark.

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
| Canopy Matter node | 10 | 12 |
| Switch Matter node | 11 | 13 |
| Sleep boolean (Indicator trigger + night dim) | `input_boolean.avery_sleeping` | `input_boolean.everyone_sleeping` (no MBR-specific toggle; household sleep ≈ parents in bed) |

If the canopy ships on `1.0.0`, update it to `1.0.1r1` and run the cleanup in
[Updating the canopy firmware](#updating-the-canopy-firmware-101r1) before Step 2
— otherwise the entity IDs and the minimum-dim control below will not match.

**Identical across every room — do not vary:**

- Canopy: `Light Mode` = `Trailing Dimmer`; `Fan Mode` = `Ceiling (3 Speed)`;
  `Minimum dim level` = `13%`; `On level` (light endpoint) = `254`; power-on
  behaviour = `previous`; light transition time (`On` / `Off` / `On-Off`) =
  `0.5` s
- Switch: Single-pole; Smart Bulb Mode enabled; LED colour Blue;
  `LED Intensity(On)` **and** `(Off)` = `0` (all four entities — select + number,
  each ×2) so only the fan automation lights the bar
- Binding: switch Binding endpoint → canopy light endpoint, cluster **6 only**
  (no cluster 8 — paddle-hold dimming is left out until it works)
- Automation: one `automation.<prefix>_ceiling_fan_wall_control`, category
  Climate, label `int_inovelli_fan_canopy`, `mode: queued` max 10
- Speed bands 33 / 66 / 100 with `< 45` / `< 78` edges; LED off when the fan is
  off; running hues 175 / 220 / 265 at 55% awake / 20% sleeping

Each room gets its own helper (`input_select.<prefix>_ceiling_fan_last_speed`)
and its own copy of the wall-control automation with the prefix and sleep
boolean substituted. The `int_inovelli_fan_canopy` label and this guide are
shared. (Rooms 3+: revisit whether to turn this into a blueprint — see the
`standards/automations.md` gap note if so.)

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
   light transition-time numbers too (also Level Control attributes) and reset
   them to `0.5` s if the flash returned them to `2.5`.
8. **Verify**: paddle on/off, config-button speed cycle, LED bar colour by speed
   and dark when the fan is off, and the light riding down to `1%` on the HA
   slider without cutting out.

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
| Avery's Room: Ceiling Fan Wall Control | `automation.averys_room_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Master Bedroom: Ceiling Fan Wall Control | `automation.master_bedroom_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Avery's Room Ceiling Fan Last Speed | `input_select.averys_room_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Master Bedroom Ceiling Fan Last Speed | `input_select.master_bedroom_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Ceiling Fan | `fan.averys_room_ceiling_fan` / `light.averys_room_ceiling_fan_light` | Matter device (VTM36) |
| Ceiling Fan Switch | `event.averys_room_ceiling_fan_switch_button_config` et al. | Matter device (VTM30-SN) |

## Related files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.averys_room_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Avery's Room wall-control automation |
| `ha/automations/automation.master_bedroom_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Master Bedroom wall-control automation |
| `scripts/matter_write_attribute.py` | run from a LAN machine (Mac Mini) | Reads vendor-cluster attributes HA doesn't expose; `--dump-node` / `--dump-modes` for discovery |

## Related documents

- `standards/automations.md` — automation naming, category, and label rules
- `standards/naming.md` — entity/device naming (the `avery_s` slug gotcha)
- `LESSONS.md` — Matter binding and VTM3x parameter gotchas
- "Harbor Breeze to Inovelli" work order (Claude artifact) — the physical
  retrofit and wiring
- Inovelli, "VTM35-SN & VTM36 Firmware 1.0.1r1+ Update Advisory" —
  <https://help.inovelli.com/en/articles/15454545-vtm35-sn-vtm36-firmware-1-0-1r1-update-advisory>
  (stale-entity cleanup and binding-rebuild steps)

## Troubleshooting

**Paddle turns the light on at the last brightness instead of full.**
`number.averys_room_ceiling_fan_on_level_1` is at `255` (the restore-previous
sentinel). Set it to `254`. The change takes effect on the next off → on cycle.

**Light cuts out at low brightness.** Raise `Minimum dim level`
(`select.<prefix>_ceiling_fan_ligh_min_level`) one step at a time until the low
end holds — `13%` is the tested value with `Trailing Dimmer`. HA slider `1%` maps
to whatever this floor is set to. On stock `1.0.0` firmware this parameter is not
settable and the light rides the LED driver's ~10% hardware floor; `1.0.1r1` is
what exposes it (see
[Config parameters over Matter](#config-parameters-over-matter)).

**One config tap advances two speeds, or the resumed speed is wrong.** The
config button emits its event twice per tap; the config branch's guard condition
(`< 0.3 s since the previous config event → skip`) must be present to drop the
duplicate. Separately, if the resumed speed lands one step low, the fan/sleep
branch read `percentage` before the fan settled — confirm the fan trigger is on
the `percentage` **attribute** (not a bare `state` trigger).

**Config-button double-tap doesn't turn the fan off.** Check the
`event.*_button_config` entity's `event_type` attribute in Developer Tools while
pressing — if a double-tap reports `multi_press_1` twice rather than
`multi_press_2`, the switch's button-press delay is set too short. Raise it via
the `Button Press Delay` / `Button Delay` select on the switch.

**LED bar stops tracking fan speed.** If a firmware update makes the switch snap
the LED back to its default indicator after `light.turn_on`, switch the Speed
Indicator automation from `light.averys_room_ceiling_fan_switch_led` to the
native `LED Intensity(Off)` select (blue is already the parameter colour).

**Paddle does nothing after a firmware update.** Two causes. (1) Smart Bulb Mode
reset — confirm `select.*_smart_bulb_mode_2` still reads `Smart Bulb Enable`;
without it the paddle drives the (empty) local relay instead of emitting the
bound command. (2) The binding stopped firing — VTM36 `1.0.1r1` reworked the
binding stack and pre-update bindings can go silent. Delete the binding on both
the switch and the canopy, power-cycle both, and recreate it per
[Step 4](#step-4--matter-binding-paddle--light). Re-check it lists the canopy
node / endpoint 1 / cluster 6.

**Duplicate or greyed-out config entities after a canopy firmware update.**
Expected on `1.0.1r1` — the config parameters moved to new Mode Select endpoints
and the originals are now dead. Clean them up per
[Updating the canopy firmware](#updating-the-canopy-firmware-101r1).

**Entities read `unavailable` after a Thread blip.** Power-cycle the canopy once
(breaker off ~2s, on) and wait a minute. Do not cycle repeatedly — the repeated
on/off pattern is the VTM36's factory-reset sequence and will wipe its Matter
commissioning.
