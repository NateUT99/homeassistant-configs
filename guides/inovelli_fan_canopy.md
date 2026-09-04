# Inovelli Fan Canopy

*Last updated: September 2026*

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

Five mechanisms connect the wall switch to the fan/light:

| Function | Mechanism | Works with HA down? |
|---|---|---|
| Paddle tap up/down → light on/off | Matter binding, cluster 6 (switch → canopy) | Yes |
| Paddle hold up/down → light dim up/down | Matter binding, cluster 8 (switch → canopy) | Yes |
| Paddle double-tap down → fan + light off; double-tap up → fan on (last speed) + light on | HA automation | No |
| Config button taps → fan speed (1 tap cycle, 2 taps off, 3 taps peek) | HA automation | No |
| Fan speed change → switch LED bar blip + speed memory | HA automation | No |

The whole-room off/on gesture is a paddle **double-tap** (`multi_press_2` on the
up/down paddle event entity), handled by the HA automation. Tap → light and
hold → light are Matter bindings and are independent of it.

## Architecture

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
                       │  light.*_switch_led        │◄── automation: Ceiling Fan Wall Control
                       └────────────────────────────┘

  automation.averys_room_ceiling_fan_wall_control   (one automation, four triggers)
      event.*_button_config        ──►  fan.set_percentage / fan.turn_off   (1 / 2 taps)
                                   └─►  blip                                (3 taps: peek)
      event.*_button_down (multi_press_2) ─►  fan.turn_off + light.turn_off
      event.*_button_up   (multi_press_2) ─►  fan.set_percentage (last speed) + light.turn_on
      fan.averys_room_ceiling_fan  ──►  input_select.averys_room_ceiling_fan_last_speed
                                   └─►  script.averys_room_ceiling_fan_led_blip

  script.averys_room_ceiling_fan_led_blip   (mode: restart)
      light.averys_room_ceiling_fan_switch_led          ◄── blip speed hue, 75% / 25%
                                                            (reads input_boolean.avery_sleeping)
      select.averys_room_ceiling_fan_switch_led_effect  ◄── "Fast Falling" (off) / "Fast Rising" (on-from-off)
      tail                                             ──► light.turn_off bar + effect select "Solid"
```

## Key design decisions

- **The light is bound; the fan is not.** Matter binding writes the paddle → light
  relationship into the switch's firmware, so it survives HA being offline and has
  no round-trip lag. An on/off switch has no bindable Matter cluster for Fan
  Control (0x0202), so the config button drives the fan through an HA automation.
  The split is deliberate: the everyday interaction is resilient; the fan, used
  less often, accepts the HA dependency.

- **Two bindings: On/Off (cluster 6) and Level Control (cluster 8).** Cluster 6 is
  paddle tap → light on/off; cluster 8 is paddle press-and-hold → smooth local dim,
  release stops the ramp. Cluster 8 only emits Move/Step while `Dimming Speed
  (Simulated)` is a non-`Instant` duration — both rooms run `2s`. See `LESSONS.md`
  for the values tested and rejected.

- **Paddle double-tap → whole-room off/on (HA automation).** `multi_press_2` on
  `event.<prefix>_ceiling_fan_switch_button_down` turns fan and light off;
  `multi_press_2` on `…_button_up` sets the fan to the remembered speed
  (`input_select.<prefix>_ceiling_fan_last_speed`) and turns the light on. Each
  branch gates on the event's `event_type` being `multi_press_2`, so a single tap
  or a hold does not match. Double-tap (not hold) leaves the cluster 8 hold-to-dim
  binding free; the switch's `300ms` Button Delay already covers multi-tap
  detection, so it costs no extra latency. `mode: queued` plus idempotent actions
  make a stray duplicate a no-op. HA-only — a paddle double-tap does nothing with
  HA down.

- **Binding fires on physical presses only.** A command sent to the switch from HA
  or Apple Home does not propagate over the binding, and bound state does not
  report back — the LED bar will not track software light changes. Neither matters
  here: the light is controlled directly via `light.averys_room_ceiling_fan_light`,
  and the bar is repurposed as a fan-speed indicator.

- **Config button: taps only, never holds.** Holding the config button opens the
  VTM30-SN's local programming menu, so only `multi_press_*` events are mapped:
  `multi_press_1` cycles the speed (or resumes from off), `multi_press_2` turns the
  fan off, `multi_press_3` is a read-only peek that fires the LED blip without
  touching the fan. The button-press-delay window aggregates a multi-tap into one
  event, so a triple tap emits `multi_press_3` alone.

- **Speed memory lives in a helper.** When the Matter fan is off, HA retains no
  memory of its prior speed (`percentage` reads 0, `preset_mode` null).
  `input_select.averys_room_ceiling_fan_last_speed` records the running speed so a
  config-button tap from off can resume it.

- **One automation per room.** `automation.<prefix>_ceiling_fan_wall_control`
  carries the non-binding links (config button gestures, down/up paddle
  double-taps, fan → speed memory + LED blip) on four triggers with a top-level
  `choose` on `condition: trigger id`. `mode: queued` (max 10) so fan-change runs
  process in order and the "no blip already in flight" guard can't race itself.
  This keeps each room a single reviewable unit with identical behaviour.

- **The LED bar rests dark and only blips on a change — at all hours.** Over
  Matter the bar is one RGB light, with no per-segment control. At rest it is
  dark whatever the fan is doing; it lights transiently to acknowledge a change:
  the speed's hue for 5 s on a speed change, or the last running speed's hue for
  2.5 s plus a `Fast Falling` animation when the fan is switched off. A fan coming
  on *from off* also carries a `Fast Rising` sweep. The off blip exists because a
  dark bar gives a double-tap-off no confirmation otherwise; the falling / rising
  animations read as "powering down / spinning up". Full spec:
  [Scale reference](#scale-reference).

- **Two blips drive a second channel — the LED-effect select.** The RGB
  notification channel (`light.<prefix>_ceiling_fan_switch_led`) sets colour and
  brightness but has no animation. Inovelli's base LED-effect parameter, exposed as
  `select.<prefix>_ceiling_fan_switch_led_effect`, has the animation list but plays
  in the fixed `LED Color` param. The off blip uses both at once (the last speed's
  hue + `Fast Falling`); the on-from-off blip uses the speed hue + `Fast Rising`.
  On-from-off
  is detected by the fan entity still reading `off` when the blip fires — the wall
  paths call the blip before `fan.set_percentage` lands, so a config advance (fan
  already `on`) gets no sweep. The select's **resting value is `Solid`, not `Off`**
  — `Off` blanks the RGB notification channel too, so the speed-hue blips would
  stop rendering. `Solid` at `LED Intensity` 0 is still dark at rest.

- **Blip brightness follows the room's sleep boolean: 75 % awake, 25 % asleep.**
  The blip script reads `input_boolean.<sleep>` once at fire time to pick `level`.
  This is the only place the sleep boolean touches the LED path — the automation
  has no sleep trigger or branch.

- **The blip lives in a per-room script, not an inline `delay`.** The wall-control
  automation is `mode: queued` and shares that queue with the config-button
  gestures, so an inline `delay` would stall tap handling behind LED animations.
  `script.<prefix>_ceiling_fan_led_blip` (`mode: restart`) runs the hold outside
  that queue; the automation fires it with `script.turn_on` and returns
  immediately. `restart` also gives the right feel: cycling low→medium→high keeps
  the bar lit and resets the timer, so it darkens 5 s after you *stop*, and a
  fan-off landing mid-speed-blip swaps straight to the off ack.

- **Button-press branches fire the blip immediately; the fan-settled branch is the
  fallback.** The `fan` trigger only fires after `fan.set_percentage` round-trips
  over Thread (~0.3–0.6 s), which makes the blip feel disconnected from the tap. So
  the config single-tap and both paddle double-tap branches `script.turn_on` the
  blip themselves *before* touching `fan.*`, passing the intended result as a
  `blip_speed` variable. The fan-settled branch still records speed memory, but its
  own `script.turn_on` is guarded on the blip script being idle, so it only blips
  for changes with no button branch (config double-tap off, external fan changes).
  `mode: queued` serialises the two.

- **The blip owns no resting state — it just turns the bar off.** The bar is dark
  except during a blip, so the blip's tail is a plain `light.turn_off` plus a
  forced `Solid` on the effect select. There is no snapshot or restore. If the
  bar ever gets a persistent status colour, that changes — see
  [Deferred — LED-bar status colour and snapshot/restore](#deferred--led-bar-status-colour-and-snapshotrestore).

- **The config button emits its event twice per physical tap** (~8 ms apart, on
  this VTM30-SN firmware / matter.js server). `mode: queued` can't drop the
  duplicate, so the config branch carries a guard condition: skip the run when less
  than 0.3 s separates this config-event state from the previous one. Genuine
  separate taps are gated by the switch's button-press-delay window and land far
  enough apart to each get their own run.

- **The fan trigger is a `state` trigger on the `percentage` attribute.** The
  Matter fan reports `state: on` before `percentage` populates, so triggering on
  the attribute means the value is real when the branch runs — no settle delay.
  Bands are widened (`< 45` = low, `< 78` = medium, else high) to absorb the fan's
  percentage rounding around 33 / 66 / 100. See `LESSONS.md`.

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

**Duplicate config entities.** A firmware change that moves config parameters onto
spec-compliant Mode Select endpoints leaves the pre-change entities behind as dead
duplicates: they read `unavailable` (`restored`) after an HA restart and a fresh
entity (often `…_2`-suffixed) carries the live value. On the VTM36 this is
firmware `1.0.1r1`; on the VTM30-SN it dates to the June 2026 matter.js rebuild.
On both devices, delete the dead originals and rename the surviving `…_2` entity
back to the clean slug:

- Canopy: `select.<prefix>_ceiling_fan_light_mode`, `_fan_mode`, and
  `number.<prefix>_ceiling_fan_on_off_transition_time` — per
  [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).
- VTM30-SN: `select.<prefix>_ceiling_fan_switch_smart_bulb_mode`, `…_led_color`,
  `…_led_effect`, and the `light.<prefix>_ceiling_fan_switch_led` bar.

Only `light.<prefix>_ceiling_fan_switch_led` is referenced by an automation (the
wall-control automation, twice) — if its slug changes, update that automation and
its `ha/` mirror in the same pass. The rest are config entities nothing depends
on, so those renames are safe on their own.

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
| LED bar color | Blue | Bedroom indicator. The wall-control automation drives colour via the light entity; the `LED Color` parameter is the fallback if the light-entity route ever stops holding, and it is the colour the `LED Effect` animation plays in. |
| `LED Effect` (`select.*_ceiling_fan_switch_led_effect`) | `Solid` | Resting value. **Not `Off`** — `Off` blanks the RGB notification channel and the automation's blips stop rendering. `Solid` at `LED Intensity` 0 is still dark at rest. The fan-off blip flips this to `Fast Falling` (~2.5 s) and the fan-on-from-off blip to `Fast Rising` (~5 s); the blip's tail forces it back to `Solid`. |
| `LED Intensity(On)` **and** `LED Intensity(Off)` | `0` | The switch keeps an internal on/off state (toggled by the paddle even in Smart Bulb Mode — this is what fires the binding, see the `Control of switch load` row) and lights the bar to `LED Intensity(On)` / `(Off)` for it. Zeroing both means that native indicator never shows, so the bar reflects *only* the fan-speed automation. Each is exposed **twice** — a **select** and a `… (Load Control)` **number** — set all four to `0` per switch. The two `(Load Control)` numbers occasionally re-read their factory defaults (`33` / `1`) after a Matter Server restart; re-zero them if the bar starts glowing faintly at rest. |

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
(category Climate, label `int_inovelli_fan_canopy`). YAML lives in the `ha/`
mirror. Four triggers, top-level `choose` on which one fired:

**Config button** (`event.*_button_config`) — guarded to skip the ~8 ms
duplicate event (see design decisions), then branches on `event_type`:

| Config gesture | Fan state | Result |
|---|---|---|
| Single tap (`multi_press_1`) | off | Resume `input_select.averys_room_ceiling_fan_last_speed` |
| Single tap (`multi_press_1`) | on | Advance low → medium → high → low |
| Double tap (`multi_press_2`) | any | Off |
| Triple tap (`multi_press_3`) | any | Blip the current speed — fan untouched |

**Paddle double-tap** (`event.*_button_down` / `event.*_button_up`) — each branch
fires on the entity changing and gates on its `event_type` attribute being
`multi_press_2`, so a single tap (cluster 6 binding) or a hold (cluster 8
binding) on the same paddle doesn't match:

| Paddle gesture | Result |
|---|---|
| Double-tap down (`multi_press_2`) | immediate off-blip (last speed's hue, `blip_speed: off`), then `fan.turn_off` + `light.turn_off` |
| Double-tap up (`multi_press_2`) | immediate speed-hue blip, then `fan.set_percentage` to the remembered speed + `light.turn_on` (full, per On level 254) |

No de-dup guard: `mode: queued` plus idempotent actions make a repeat
`multi_press_2` a no-op.

**Immediate blip.** The config single-tap and both paddle double-tap branches
don't wait for the fan. Before touching `fan.*` they `script.turn_on` the blip
with a `blip_speed` variable set to the *intended* result — remembered speed for
a resume / up double-tap, computed next band for a config advance, `off` for the
down double-tap. The bar lights within the switch's ~0.3 s LED latency instead of
after the ~0.3–0.6 s fan round-trip.

**Fan `percentage` attribute change** (the value is already settled — no delay):

1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to `input_select.*_ceiling_fan_last_speed`
   (skipped when off, so the memory survives an off/on cycle).
3. **If** `script.*_ceiling_fan_led_blip` is `off` (no blip in flight),
   `script.turn_on` the blip (no `blip_speed` — the script reads the now-settled
   fan). When a button branch already started an immediate blip this step is
   skipped. The script shows the acknowledgement, holds, then does
   `light.turn_off` on the bar and forces the effect select back to `Solid`. Blip
   spec: [Scale reference](#scale-reference).

`mode: queued`, `max: 10` — runs process in order, so the "no blip in flight"
guard can't race itself. The blip's timed hold runs in the `mode: restart`
script, off this queue.

## Scale reference

Fan speed (VTM36 3-speed): `1–33% = low`, `34–66% = medium`, `67–100% = high`.
The automations use 33 / 66 / 100, with `< 45` / `< 78` band edges to absorb the
Matter fan's percentage rounding.

LED bar — **dark at rest at all hours**, whatever the fan is doing. It only blips
to acknowledge a change; when the blip finishes the script turns the bar off and
re-asserts `Solid` on the effect select. This table is the single source of
truth for the blip; other sections reference it.

| Fan | RGB hue (`hs_color`) | Effect select | Blip hold | Blip brightness (awake / asleep) |
|---|---|---|---|---|
| off | last running speed's hue | `Fast Falling` | 2.5 s | 75% / 25% |
| on from off | that speed's hue | `Fast Rising` | 5 s | 75% / 25% |
| speed change (already on) | that speed's hue | — (`Solid`, untouched) | 5 s | 75% / 25% |

Speed hues: teal low 175 / blue medium 220 / violet high 265. On-from-off is
detected by the fan entity still reading `off` when the blip fires.

"Dark at rest" needs: the blip's tail does `light.turn_off` on the bar and
`select.select_option` `Solid` on the effect select, **and** the switch's
`LED Intensity(Off)` param is `0` so the native fallback (HA down) is also dark.
The effect select rests on `Solid`, not `Off` — `Off` blanks the RGB
notification channel and the speed blips stop rendering.

## Deferred — LED-bar status colour and snapshot/restore

The bar has no persistent resting state today: it is dark except during a blip,
and the blip script ends by turning it off. So the blip does **not** snapshot or
restore anything — it just fires its colour, holds, then `light.turn_off` +
force `Solid`.

If the bar is ever given a **persistent resting colour** — a status indicator
(alarm armed, someone home, a timer running, an unacknowledged alert) painted on
`light.<prefix>_ceiling_fan_switch_led` — the blip must stop clobbering it. Bring
back a snapshot/restore around every blip:

1. **Snapshot before the blip.** In each automation branch that calls
   `script.turn_on` (config single tap, triple-tap peek, both paddle double-taps,
   fan-settled), and at the top of the blip script for direct runs, `scene.create`
   a scene capturing `light.<prefix>_ceiling_fan_switch_led` **and**
   `select.<prefix>_ceiling_fan_switch_led_effect` into
   `scene.<prefix>_ceiling_fan_led_restore`.
2. **Guard the snapshot on the blip being idle.** Wrap the `scene.create` in
   `if: condition: state, entity_id: script.<prefix>_ceiling_fan_led_blip,
   state: "off"`. The script is `mode: restart`; snapshotting mid-blip captures
   the blip's own colour as the "resting" state and the bar never goes dark
   again. `mode: queued` on the automation keeps its runs serialised so the guard
   can't race itself.
3. **Restore in the blip tail.** Replace the `light.turn_off` tail with
   `if states.scene.<prefix>_ceiling_fan_led_restore is not none →
   scene.turn_on` it, else `light.turn_off`. Then **still force the effect select
   to `Solid` unconditionally** — see the trap below.

Traps carried over from the removed implementation:

- **Never let the snapshot own the effect channel's resting value.** Once the
  effect select drifts off `Solid` (e.g. a blip restarted before its tail ran), a
  `scene.create` captures the drifted animation value and every restore
  re-applies it forever — the bar stays mid-animation. Force `Solid` after the
  scene restore, always.
- **`scene.create` on this bar can suppress the next colour command.** A
  `light.turn_on` issued shortly after a `scene.create` on the same entity was
  observed to report success and render nothing for colour-temp and
  low-saturation values (fully-saturated `hs_color` was unaffected). Test the
  real status colour through the full snapshot → blip → restore path before
  shipping. See `LESSONS.md`.

## Replicating for another room

This setup is a per-room pattern. Avery's Room is the first instance and the
Master Bedroom the second; Living Room and Office are planned and use the same
build. Every room is configured identically apart from the substitutions below.
To add a room, work through Steps 1–6 with these substitutions.

**Per-room substitutions:**

| Placeholder | Avery's Room | Master Bedroom | Living Room | Office |
|---|---|---|---|---|
| Area / entity prefix | `averys_room` | `master_bedroom` | `living_room` | `office` |
| Canopy device name | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` |
| Switch device name | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` |
| Canopy Matter node | 10 | 12 | TBD | TBD |
| Switch Matter node | 11 | 13 | TBD | TBD |
| Sleep boolean (blip brightness) | `input_boolean.avery_sleeping` | `input_boolean.everyone_sleeping` | `input_boolean.everyone_sleeping` | `input_boolean.everyone_sleeping` |

Only Avery's Room has a person-specific sleep toggle; the other rooms use the
household `input_boolean.everyone_sleeping`.

If the canopy ships on `1.0.0`, update it to `1.0.1r1` and run the cleanup in
[Updating the canopy firmware](#updating-the-canopy-firmware-101r1) before Step 2
— otherwise the entity IDs and the minimum-dim control will not match.

**Everything else is identical across rooms** — every parameter value in Steps
2–3, the two bindings, the automation shape (one
`automation.<prefix>_ceiling_fan_wall_control`, category Climate, label
`int_inovelli_fan_canopy`, `mode: queued` max 10, four triggers), the blip script
(one `script.<prefix>_ceiling_fan_led_blip`, `mode: restart`), the speed bands,
and the blip spec in [Scale reference](#scale-reference). Two values are easy to
get wrong and worth re-checking per room: `LED Effect` = `Solid` (**not `Off`**)
and `Control of switch load` left at `Remote & paddle control`.

Each room gets its own copies with the prefix and sleep boolean substituted:

- `automation.<prefix>_ceiling_fan_wall_control`
- `script.<prefix>_ceiling_fan_led_blip`
- `input_select.<prefix>_ceiling_fan_last_speed`

The `int_inovelli_fan_canopy` label and this guide are shared.

**Parity check.** The per-room automation and script copies must differ *only* by
the entity prefix, the sleep boolean (`avery_sleeping` vs `everyone_sleeping`),
the automation `id`, and the friendly-name prefix in `alias` / `description`.
After editing any room, `diff` its `ha/` mirror against another room's to confirm
nothing else diverged — any other difference is a bug.

Per-room copies rather than a blueprint: the blip script must be `mode: restart`
per room (a shared script would have to be `mode: parallel`, which breaks the
keep-lit-through-a-burst behaviour within a room), and a templated
`target.entity_id` in one shared automation would leave the GUI editor showing
only an inputs form — against the house preference for GUI-editable automations.
There is also no blueprint convention in this repo. Four self-contained copies
kept honest by the parity check is the accepted cost.

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
   lights the speed's hue almost immediately (before the fan spins up) and holds
   ~5 s; a 1-tap resume from off adds a `Fast Rising` sweep, a config double-tap
   off shows the last speed's hue + `Fast Falling` for ~2.5 s, and both return to dark (effect
   select back to `Solid`); the triple-tap peek showing the current speed
   without moving the fan; a change made while the room's sleep boolean is on
   blipping dimmer (25 %); and the light riding down to `1%` on the HA slider
   without cutting out.

## Security summary

| Control | Detail |
|---|---|
| Fabric membership | Both devices are commissioned to the Home Assistant Matter fabric and the Apple Home fabric (multi-admin). The binding is written by HA as a fabric admin. |
| Binding scope | The paddle → light binding is node 11 → node 10 endpoint 1, On/Off (cluster 6) only. The corresponding ACL entry on the canopy grants the switch operate (not administer) access. |
| Blast radius if the switch were compromised | It can turn the fan light on and off and change its brightness. It has no Load, no access to other devices, and no administer rights on the canopy. |
| Local control | The switch's config-button programming menu is reachable by anyone physically present (config-button hold). This is Inovelli firmware behaviour and is not exposed over the network. |

## Related HA config

| Friendly name | Entity ID | Type |
|---|---|---|
| Avery's Room: Ceiling Fan Wall Control | `automation.averys_room_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Master Bedroom: Ceiling Fan Wall Control | `automation.master_bedroom_ceiling_fan_wall_control` | Automation (Climate, `int_inovelli_fan_canopy`) |
| Avery's Room: Ceiling Fan LED Blip | `script.averys_room_ceiling_fan_led_blip` | Script (`mode: restart`) — acknowledgement blip for the switch LED bar |
| Master Bedroom: Ceiling Fan LED Blip | `script.master_bedroom_ceiling_fan_led_blip` | Script (`mode: restart`) — acknowledgement blip for the switch LED bar |
| Avery's Room Ceiling Fan Last Speed | `input_select.averys_room_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Master Bedroom Ceiling Fan Last Speed | `input_select.master_bedroom_ceiling_fan_last_speed` | Helper (`int_inovelli_fan_canopy`) |
| Ceiling Fan | `fan.averys_room_ceiling_fan` / `light.averys_room_ceiling_fan_light` | Matter device (VTM36) |
| Ceiling Fan Switch | `event.averys_room_ceiling_fan_switch_button_config` et al. | Matter device (VTM30-SN) |

## Related files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.averys_room_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Avery's Room wall-control automation |
| `ha/automations/automation.master_bedroom_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Master Bedroom wall-control automation |
| `ha/scripts/script.averys_room_ceiling_fan_led_blip.yaml` | HA script registry | Mirror — Avery's Room LED-bar acknowledgement blip |
| `ha/scripts/script.master_bedroom_ceiling_fan_led_blip.yaml` | HA script registry | Mirror — Master Bedroom LED-bar acknowledgement blip |
| `scripts/matter_write_attribute.py` | run from a LAN machine (Mac Mini) | Reads vendor-cluster attributes HA doesn't expose; `--dump-node` / `--dump-modes` for discovery |

## Related documents

- `standards/automations.md` — automation naming, category, and label rules
- `standards/naming.md` — entity/device naming (the `avery_s` slug gotcha)
- `LESSONS.md` — Matter binding and VTM3x parameter gotchas (dimming speed values,
  `scene.create` inside a restart script, `light.turn_off` dropping `transition`)
- "Harbor Breeze to Inovelli" work order (Claude artifact) — the physical
  retrofit and wiring
- Inovelli, "VTM35-SN & VTM36 Firmware 1.0.1r1+ Update Advisory" —
  <https://help.inovelli.com/en/articles/15454545-vtm35-sn-vtm36-firmware-1-0-1r1-update-advisory>
  (stale-entity cleanup and binding-rebuild steps)

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

**Light cuts out at low brightness.** Raise `Minimum dim level`
(`select.<prefix>_ceiling_fan_ligh_min_level`) one step at a time until the low
end holds — `13%` is the tested value with `Trailing Dimmer`. HA slider `1%` maps
to whatever this floor is set to. On stock `1.0.0` firmware this parameter is not
settable (see
[Config parameters over Matter](#config-parameters-over-matter)).

**One config tap advances two speeds, or the resumed speed is wrong.** The
config button emits its event twice per tap; the config branch's guard condition
(`< 0.3 s since the previous config event → skip`) must be present to drop the
duplicate. If the resumed speed lands one step low, confirm the fan trigger is on
the `percentage` **attribute**, not a bare `state` trigger.

**LED bar blip doesn't show, or the bar won't go dark.** If a firmware update
makes the switch snap the LED back to its default indicator after `light.turn_on`
(so the blip is invisible), fall back to the native `LED Intensity(Off)` select
for the indicator (blue is already the parameter colour). If the bar is stuck lit
after a blip, the blip script's tail didn't run — it was restarted and killed
before its `light.turn_off`. Clear it by hand: `light.turn_off` the bar and set
`select.<prefix>_ceiling_fan_switch_led_effect` to `Solid`; the next fan change
blips and cleans up normally.

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
