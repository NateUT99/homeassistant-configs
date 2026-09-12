# Adaptive Lighting

*Last updated: September 2026*

## Overview

Adaptive Lighting (AL — HACS, `basnijholt/adaptive-lighting`) adjusts light brightness through
the day on a sun-position curve. Two instances run here, **Standard** and **Avery Schedule**,
covering the three Inovelli canopy ceiling-fan light kits (Master Bedroom, Office, Avery's
Room). Those fixtures are dumb LED loads on a Matter/Thread dimmer, so AL adapts brightness
only — colour temperature is not available on the hardware. All three lights (and their paired
fan entities) are exposed to Apple Home through Home-Assistant-Matter-Hub bridging rather than
direct Matter commissioning, so an Apple Home turn-on is a real `light.turn_on` call AL's
`intercept` adapts immediately, the same as HA's own dashboard or a script. Only a wall-paddle
tap — a Matter binding written into the switch firmware that never reaches HA — falls outside
`intercept`'s reach; a companion automation pre-stages each fixture's Matter `OnLevel` so that
binding-driven turn-on lands closer to the adapted level, and the wall-control automations add
a fast 2-second correction on every observed turn-on as a backstop regardless of source (see
Design Decisions).

## Architecture

```
Standard          switch.adaptive_lighting_standard
  lights          light.master_bedroom_ceiling_fan_light, light.office_ceiling_fan_light
  sleep mode      switch.adaptive_lighting_standard_sleep_mode
                    ◄── Household: Sleep Mode   (input_boolean.everyone_sleeping)

Avery Schedule    switch.adaptive_lighting_avery_schedule
  light           light.averys_room_ceiling_fan_light
  sleep mode      switch.adaptive_lighting_avery_schedule_sleep_mode
                    ◄── Avery's Room: Sleep Mode   (input_boolean.avery_sleeping)

Both instances
  intercept       a bare light.turn_on is adapted to the curve at turn-on
  wall dim        paddle hold → long_release → set_manual_control(true)      ┐
  turn-off        light → off → set_manual_control(false)                    │  per-room
  turn-on         light → on (not manual) → adaptive_lighting.apply, 2s      ┘  wall-control automation

automation.adaptive_lighting_pre_stage
  every 15 min + on light→off + on sleep-mode flip + on HA start
  writes number.<room>_ceiling_fan_on_level_1 while that light is off
  → a binding-driven paddle tap turns on near the current curve target
```

### Design decisions

#### Two instances, split by sleep schedule

AL's sleep mode is a per-instance switch, not a per-light setting. Avery goes to bed before
the rest of the household, so her ceiling needs a sleep switch that `Avery's Room: Sleep
Mode` can flip independently of `input_boolean.everyone_sleeping`. Every other adapted light
joins Standard. There is no Colour-Only instance because nothing under AL supports colour
temperature.

#### Brightness only; `adapt_color` off

The canopy light kits report `supported_color_modes: ["brightness"]`, so there is nothing for
AL to colour-adapt. Both instances' `adapt_color` sub-switches are **off** — AL would skip
colour on these lights regardless, but off is the accurate reading of what the system does.
Re-enable it per instance if a colour-capable light is ever enrolled; the `*_color_temp`
settings are given sane values so that switch is the only change needed.

#### `manual_control_on_external_turn_on` stays off

This AL v1.32.0 option treats any turn-on without a matching HA context as a manual override.
A binding-driven wall-paddle tap is exactly that, so enabling it would freeze every
paddle-lit ceiling off-curve for the autoreset window. It must stay `false`; pre-staging is
what makes a bare paddle turn-on land near the curve instead.

#### `detect_non_ha_changes` is on

AL's own off→on handler treats a binding-driven turn-on as manual unconditionally whenever
this is off — a wall-paddle tap never calls `light.turn_on`, so every tap would be flagged
regardless of how close pre-staging landed it to the curve, defeating pre-staging entirely.
With it on, AL instead compares the light's actual value against its target and only flags a
genuine mismatch (`LESSONS.md` has the source-level detail). The wall-control automations'
`long_release`/turn-off branches (`guides/inovelli_switches.md` Step 6) still separately
handle a mid-hold dim of an already-on light and a binding-driven turn-off, neither of which
this setting reaches on its own.

#### Pre-staging via Matter `OnLevel`, not MQTT

AL only commands lights that are on. A wall-paddle turn-on runs in the switch/canopy firmware
(cluster 6 binding) and never reaches `light.turn_on`, so AL's `intercept` cannot touch it —
the only value that governs that turn-on level is the canopy's Level Control `OnLevel`
attribute (`number.<room>_ceiling_fan_on_level_1`). `automation.adaptive_lighting_pre_stage`
writes the current curve target there while the light is off. See [Step 4](#step-4--pre-staging).

#### Every observed turn-on gets a fast 2s correction, not just a pre-staged one

Only the wall-paddle path depends on `OnLevel` pre-staging — it's a Matter binding in switch
firmware that never calls `light.turn_on`, so AL's `intercept` cannot touch it, and pre-staging
narrows but does not guarantee the gap between the paddle's actual turn-on and the current
curve target. Every other turn-on path (HA dashboard, scripts, Apple Home via the
Home-Assistant-Matter-Hub bridge) is a real `light.turn_on` call `intercept` adapts directly, so
it lands on the curve without needing a correction. Rather than special-case the paddle path,
each wall-control automation's "Ceiling light changed" branch calls `adaptive_lighting.apply`
with a 2s transition on **any** observed turn-on that isn't manually controlled, regardless of
source — a fast backstop for the paddle, and a no-op everywhere `intercept` already landed it
correctly.

#### `autoreset_control_seconds` with `pause_changed` needs AL ≥ 1.32.0

The design relies on a wall-dimmed light being handed back to AL 30 minutes later by the
autoreset timer, with `take_over_control_mode: pause_changed` so only the changed attribute
is paused. That combination was broken before v1.32.0; it is a hard minimum version.

---

## Prerequisites

- HACS, with **Adaptive Lighting v1.32.0 or later** installed. The autoreset + `pause_changed`
  path and the `has_entity_name` switch IDs below are 1.32.0 behaviour; v1.32.0 itself needs
  HA core 2025.9+.
- The three Inovelli canopy ceiling fans built per `guides/inovelli_switches.md` — the
  `light.<room>_ceiling_fan_light` entities, the `number.<room>_ceiling_fan_on_level_1`
  entities, and the per-room wall-control automations must already exist.
- `input_boolean.everyone_sleeping` and `input_boolean.avery_sleeping`, with the
  `Household: Sleep Mode` and `Avery's Room: Sleep Mode` automations.

---

## Step 1 — Create the two instances

**Settings → Devices & Services → Add Integration → Adaptive Lighting.** Add it twice.

| Instance name | Lights |
|---|---|
| `Standard` | `light.master_bedroom_ceiling_fan_light`, `light.office_ceiling_fan_light` |
| `Avery Schedule` | `light.averys_room_ceiling_fan_light` |

Each instance registers a main switch plus `_adapt_brightness`, `_adapt_color`, and
`_sleep_mode` sub-switches. On v1.32.0 (`has_entity_name`) the IDs are
`switch.adaptive_lighting_<instance>` and `switch.adaptive_lighting_<instance>_<sub>` — e.g.
`switch.adaptive_lighting_standard_sleep_mode`. Confirm the exact IDs in Developer Tools →
States before wiring anything against them.

Apply the `int_adaptive_lighting` label to both config entries and to the three enrolled
`light.*_ceiling_fan_light` entities (`standards/automations.md` §3.2).

## Step 2 — Configure each instance

**Settings → Devices & Services → Adaptive Lighting → [instance] → Configure.** Both instances
take identical values. The advanced options are behind collapsible sections in v1.32.0.

| Setting | Value | Note |
|---|---|---|
| Interval | `90` | |
| Transition | `45` | |
| Initial transition | `1` | |
| Min brightness | `35` | Evening / pre-sleep floor. |
| Max brightness | `100` | The canopy light kit already caps physical output at ~70% (`guides/inovelli_switches.md` Step 2), so HA's full range is used. |
| Sleep brightness | `10` | Also the middle-of-the-night wall-tap level, via pre-staging. |
| Brightness mode | `tanh` | S-curve; ramp shape decoupled from sun elevation. |
| Brightness mode time dark | `1800` | |
| Brightness mode time light | `5400` | |
| Min / Max sunrise time | `06:30:00` / `07:30:00` | Clamps the morning ramp anchor. |
| Min / Max sunset time | `20:00:00` / `21:00:00` | Clamps the evening wind-down anchor. |
| Take over control | on | |
| Take over control mode | `pause_changed` | Default is `pause_all`. Pauses only the attribute that changed. |
| Adapt only on bare turn on | on | A `light.turn_on` carrying brightness or colour skips adaptation. |
| Detect non-HA changes | on | See Design Decisions. |
| Manual control on external turn on | off | Default. Load-bearing — see Design Decisions. |
| Reset manual control on sleep mode change | on | Default. A sleep-mode flip clears a stale evening wall-dim. |
| Autoreset control seconds | `1800` | Default is `0`. Hands a wall-dimmed light back after 30 min. |
| Skip redundant commands | off | Default. |
| Intercept / Multi-light intercept | on | Adapts a bare `light.turn_on` at turn-on. |
| Expand light groups | on | Default; inert, no groups enrolled. |
| Only once / Separate turn-on commands / Prefer RGB colour | off | |
| Send split delay / Adapt delay | `0` | |
| Min / Max / Sleep color temp | `2000` / `5500` / `2000` | Inert on brightness-only fixtures; set for future use. |

Leave `adapt_brightness` and the main switch **on** for both instances; `adapt_color` is
**off** (see Design Decisions). The `_sleep_mode` sub-switches stay **off** — the sleep
automations drive them (Step 3).

## Step 3 — Sleep-mode wiring

Sleep mode is not scheduled; it is driven by the two existing sleep automations.

| Instance sleep switch | Driven by |
|---|---|
| `switch.adaptive_lighting_standard_sleep_mode` | `Household: Sleep Mode` — `switch.turn_on` in the night-prep parallel block, `switch.turn_off` in the wake block. Replaces the old hand-dim of the master bedroom ceiling to 25%; AL's `sleep_brightness` owns it now, and AL only commands lights that are already on, so the "only if on" guard is implicit. |
| `switch.adaptive_lighting_avery_schedule_sleep_mode` | `Avery's Room: Sleep Mode` — enabled after the ceiling-light fade-off at bedtime; cleared first thing on wake, before the sunrise below. |

On wake, `Avery's Room: Sleep Mode` runs an Adaptive Lighting sunrise on her ceiling:
`set_manual_control(true)` → `adaptive_lighting.apply` over 120 s toward the morning target →
race the bedroom-door-open trigger with a 2 s `apply` → `set_manual_control(false)`. The
Standard rooms have no wake ramp — AL adapts them from whatever level they hold when next
turned on.

> **Coordinated change:** the sleep switch IDs above. If an instance is renamed or recreated,
> update both sleep automations to match. The sleep-off order in `Avery's Room: Sleep Mode`
> (clear the sleep switch **before** `set_manual_control`) is load-bearing —
> `reset_manual_control_on_sleep_mode_change` would otherwise clear the lock mid-sunrise.

## Step 4 — Pre-staging

`automation.adaptive_lighting_pre_stage` ("Adaptive Lighting: Pre-Stage", Maintenance
category; labels `int_adaptive_lighting`, `int_inovelli_fan_canopy`, `scope_whole_home`).
YAML lives in the `ha/` mirror.

**What it solves.** A wall-paddle turn-on is a cluster 6 Matter binding in the switch
firmware; it never calls `light.turn_on`, so AL's `intercept` cannot adapt it. The canopy's
Level Control `OnLevel` (`number.<room>_ceiling_fan_on_level_1`) is the only value that
governs that turn-on level. The automation keeps `OnLevel` loaded with the current AL
brightness target while the light is off, so a paddle tap lands near the curve.

**Triggers:** a `/15` minute poll; each `light.<room>_ceiling_fan_light` → `off`; each
instance's `_sleep_mode` switch changing; `homeassistant` start.

**Per fixture, while its light is off:** take that fixture's own instance-switch
`brightness_pct`, convert to a raw 0–254 `OnLevel` ([Scale Reference](#scale-reference)), and
write it **only if it differs from the stored value by at least the perceptibility
threshold**. On the poll trigger the threshold is `25` raw units (≈ 10 HA brightness points);
on the turn-off, sleep, and start triggers any non-zero difference is written, because those
are the moments worth getting exact.

**Why the threshold.** `OnLevel` is a non-volatile Matter attribute — every write is a flash
write. Gating on ~10 perceptible points keeps writes to a few per device per day: nothing
across the flat midday top or the flat sleep floor, a handful during each ramp.

Standard drives Master Bedroom and Office; Avery Schedule drives Avery's Room. Each fixture
row in the automation names its own instance switch, so the two curves stay independent.
Adding a fourth fixture is one `for_each` row plus enrolment in an instance.

## Step 5 — Turn-on correction

Each `automation.<room>_ceiling_fan_wall_control`'s "Ceiling light changed" branch (shared
with the turn-off release logic — `guides/inovelli_switches.md` Step 6) adds: whenever that
room's light is observed **on** and is not in its instance's `manual_control_brightness` list,
call `adaptive_lighting.apply` with `transition: 2` to snap it to the current curve target.

**Why this exists in addition to pre-staging.** Pre-staging only narrows the gap on a
wall-paddle turn-on; it does not guarantee an exact landing, since `OnLevel` is a coarse
0–254 value re-staged periodically rather than a live command. Rather than accept that gap,
this forces a 2-second correction on every turn-on regardless of source, closing it instead of
waiting on AL's normal ~45s adaptation cycle. On a turn-on `intercept` already caught (HA
dashboard, scripts, Apple Home via Matter Hub), the call is a no-op.

## Scale Reference

**Brightness percent → raw `OnLevel`:** `round(brightness_pct / 100 × 254)`, then clamp to
`1`–`254`. (`255` is the canopy's "restore previous" sentinel and is never written here.)

| AL `brightness_pct` | raw `OnLevel` written | Physical light output\* |
|---|---|---|
| 10 (sleep) | 25 | ~19% |
| 35 (evening floor) | 89 | ~33% |
| 90 | 229 | ~64% |
| 100 (daytime peak) | 254 | ~70% |

\* HA 1–100% maps onto the canopy light kit's ~13–70% phase-cut window —
`guides/inovelli_switches.md` Step 2 owns the Minimum / Maximum dim level values that define
it.

**Poll write threshold:** `25` raw units ≈ 10 percentage points of HA brightness — roughly
where an average person notices a ceiling light came on brighter or dimmer than expected.
Held in the automation's `variables` block for one-place tuning.

---

## Related HA Config

| Friendly name | Entity ID | Type |
|---|---|---|
| Adaptive Lighting: Standard | `switch.adaptive_lighting_standard` (+ `_adapt_brightness`, `_adapt_color`, `_sleep_mode`) | AL instance switches |
| Adaptive Lighting: Avery Schedule | `switch.adaptive_lighting_avery_schedule` (+ `_adapt_brightness`, `_adapt_color`, `_sleep_mode`) | AL instance switches |
| Adaptive Lighting: Pre-Stage | `automation.adaptive_lighting_pre_stage` | Automation (Maintenance; `int_adaptive_lighting`, `int_inovelli_fan_canopy`, `scope_whole_home`) |

The three `light.*_ceiling_fan_light` entities carry the `int_adaptive_lighting` label as
enrolled members, as do the three `automation.*_ceiling_fan_wall_control` automations (whose
`long_release`, turn-off, and turn-on-snap branches call `adaptive_lighting.set_manual_control`
/ `adaptive_lighting.apply`).

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.adaptive_lighting_pre_stage.yaml` | HA automation registry | Mirror — pre-stage automation |

AL instance settings are a config-flow options flow with no on-disk or MCP-retrievable form;
Step 2 is the record of them.

## Related Documents

- `guides/inovelli_switches.md` — the canopy hardware, the `OnLevel` and dim-level
  parameters, and the wall-control automations that carry the `long_release` and turn-off AL
  branches
- `standards/automations.md` — category and label rules; the `int_adaptive_lighting` label
- `LESSONS.md` — why `detect_non_ha_changes: false` blanket-flags every untracked turn-on as
  manual, and why a binding-driven turn-off needs the wall-control automation to release it

## Troubleshooting

**A ceiling comes on at a wall-driven brightness and stays there.** Check
`manual_control_brightness` on the instance switch. A binding-driven turn-off never reaches AL
as a `light.turn_off` service call, so only the room's wall-control automation (which reacts to
the light's observed state, not the call), the 30-minute autoreset, or an explicit
`adaptive_lighting.set_manual_control` false clears it — confirm the wall-control automation's
last trace ran. If this happens on a plain turn-on with no preceding hold, confirm
`detect_non_ha_changes` reads **on** for that instance; off blanket-flags every untracked
turn-on regardless of the resulting brightness. `LESSONS.md` has the mechanism.

**Pre-staging never writes.** The instance switch must expose `brightness_pct` — check
Developer Tools → States on `switch.adaptive_lighting_standard`. If it is absent, the instance
has no lights or has not run its first cycle.

**Pre-stage writes on every poll.** The stored `OnLevel` is being changed out of band between
polls (a wall hold, a manual `number.set_value`), and each poll re-corrects it. Harmless, but
check what else writes that entity.

**A paddle tap still comes on at full.** `number.<room>_ceiling_fan_on_level_1` is at `254`
and the curve target is near 100%, so `254` is correct — pre-staging only lowers it once the
curve drops. Confirm at a lower point on the curve (evening, or with sleep mode on).

**A ceiling flashes bright, then corrects within ~2s.** Expected — Step 5's turn-on snap
working as designed; pre-staging did not land it on the curve, so the fast correction did.

**A ceiling flashes bright and stays there for longer than ~2s.** The turn-on snap didn't
fire. Check the wall-control automation's trace for the "Ceiling light changed" run: either
the light was already in `manual_control_brightness` (so the snap correctly stood down — check
whether that's right), or the `adaptive_lighting.apply` call itself errored (check the trace's
action result). If this happens on an Apple Home turn-on specifically, confirm the light and
fan still carry the `matterhub` label and that Apple Home is commanding the Matter Hub-bridged
accessory, not a stale direct-Matter one — a turn-on that bypasses HA's `light.turn_on`
entirely depends on the same `OnLevel` pre-staging as the wall paddle and won't be caught by
`intercept`.

**Diagnosing AL itself.** The config entry's **Download diagnostics** action (v1.32.0) dumps
the full instance state — prefer it over reading logs.
