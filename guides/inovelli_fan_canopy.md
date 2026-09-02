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

Four mechanisms connect the wall switch to the fan/light:

| Function | Mechanism | Works with HA down? |
|---|---|---|
| Paddle tap up/down → light on/off | Matter binding, cluster 6 (switch → canopy) | Yes |
| Paddle hold down → fan + light off; hold up → fan on (last speed) + light on | HA automation | No |
| Config button taps → fan speed (1 tap cycle, 2 taps off, 3 taps peek) | HA automation | No |
| Fan speed change → switch LED bar blip + speed memory | HA automation | No |

The paddle **hold** was originally a second Matter binding (cluster 8, Level
Control) that dimmed the light up/down locally. That binding is removed: the hold
gesture is now an HA automation (`long_press` on the up/down paddle event
entity) mapped to whole-room off/on, which was preferred over hold-to-dim. Tap →
light on/off stays a binding and is unaffected.

## Architecture

```
                       Avery's Room ceiling
                       ┌───────────────────────────┐
                       │  VTM36 canopy (node 10)   │
                       │   endpoint 1: light  ──────┼──► light.averys_room_ceiling_fan_light
                       │   endpoint 2: fan    ──────┼──► fan.averys_room_ceiling_fan
                       └────────▲─────────▲─────────┘
                                │         │
          Matter binding        │         │   Matter (HA-issued commands)
        (On/Off cluster 6)      │         │
                                │         │
                       ┌────────┴─────────┴─────────┐
    wall paddle  ──────► VTM30-SN switch (node 11)  │
    config button ─────► endpoint 2: Binding cluster│
                       │  event.*_button_down/up    │──► automation: hold → fan/light off / on
                       │  event.*_button_config     │──► automation: Ceiling Fan Wall Control
                       │  light.*_switch_led        │◄── automation: Ceiling Fan Wall Control
                       └────────────────────────────┘

  automation.averys_room_ceiling_fan_wall_control   (one automation, four triggers)
      event.*_button_config        ──►  fan.set_percentage / fan.turn_off   (1 / 2 taps)
                                   └─►  snapshot + blip                     (3 taps: peek)
      event.*_button_down (long_press) ─►  fan.turn_off + light.turn_off
      event.*_button_up   (long_press) ─►  fan.set_percentage (last speed) + light.turn_on
      fan.averys_room_ceiling_fan  ──►  input_select.averys_room_ceiling_fan_last_speed
                                   ├─►  scene.create  scene.averys_room_ceiling_fan_led_restore
                                   │       (snapshot RGB bar + LED-effect select, guarded)
                                   └─►  script.averys_room_ceiling_fan_led_blip

  script.averys_room_ceiling_fan_led_blip   (mode: restart)
      light.averys_room_ceiling_fan_switch_led          ◄── blip speed hue (75/25%) / amber-gold (100/40%)
                                                            (reads input_boolean.avery_sleeping)
      select.averys_room_ceiling_fan_switch_led_effect  ◄── snapshotted only; no blip writes it
      scene.averys_room_ceiling_fan_led_restore         ──► re-assert both (else light.turn_off)
```

**Key design decisions:**

- **The light is bound; the fan is not.** Matter binding writes the
  relationship into the switch's firmware, so paddle → light survives HA being
  offline and has no round-trip lag. Fan control has no bindable Matter cluster
  on an on/off switch (Fan Control is cluster 0x0202, which an on/off switch's
  client clusters don't map onto), so the config button must go through an HA
  automation. This split is deliberate: the everyday interaction (light on/off)
  is resilient; the fan, used less often, accepts the HA dependency.
- **One binding: On/Off (cluster 6).** Cluster 6 is paddle tap → light on/off,
  and it is the only binding — it survives HA being offline and has no
  round-trip lag. A second binding (cluster 8, Level Control) originally gave
  paddle press-and-hold → smooth local dim up/down; it was removed in favour of
  mapping the hold gesture to a whole-room off/on in the HA automation (see
  **Paddle hold**, below), which is used more than hold-to-dim was. Cluster 8 is
  fiddly on this switch anyway — it only emits Move/Step while
  `Dimming Speed (Simulated)` is a non-`Instant` duration, `2s` was the only
  reliable value, and `3s` regressed intermittently. If hold-to-dim is ever
  wanted back, re-add the cluster 8 target ([Step 4](#step-4--matter-binding-paddle--light))
  and set `select.<prefix>_ceiling_fan_switch_dimming_speed_simulated` to `2s` —
  but note the hold automation branches would then need to be dropped or they
  fight the local ramp.
- **Paddle hold → whole-room off/on (HA automation).** A `long_press` on
  `event.<prefix>_ceiling_fan_switch_button_down` turns the fan off and the light
  off; a `long_press` on `…_button_up` sets the fan to the remembered speed
  (`input_select.<prefix>_ceiling_fan_last_speed`) and turns the light on. Each
  branch gates on the event entity's `event_type` attribute being `long_press`,
  so a tap (`multi_press_1`) on the same entity does not match. `mode: queued`
  makes a stray duplicate `long_press` harmless — the actions are idempotent.
  Every hold blips the LED bar: when it changes the fan, the `percentage` branch
  fires the blip; when it doesn't (hold down while already off, hold up while
  already at the last speed), the hold branch fires the blip itself, gated on the
  fan's pre-call state so the two paths never double up (see
  [Step 6](#step-6--ha-automation)). This is HA-only — with HA down, a paddle
  hold does nothing (tap still works over the binding).
- **Binding fires on physical presses only.** A command sent to the switch from
  HA or Apple Home does not propagate over the binding to the light, and bound
  state does not report back — the switch LED bar will not track light changes
  made in software. Neither matters here: the light is controlled directly via
  `light.averys_room_ceiling_fan_light`, and the LED bar is repurposed as a fan
  indicator (below).
- **Config button: taps only, never holds.** Holding the config button puts the
  VTM30-SN into its own local programming menu. An automation on the config
  button's `long_press` event would fire *and* open programming mode at the same
  time. Only `multi_press_*` events are mapped: `multi_press_1` cycles the speed
  (or resumes from off), `multi_press_2` turns the fan off, `multi_press_3` is a
  read-only peek — it fires the LED blip without touching the fan, so the current
  speed is legible at the wall now that the bar carries no steady colour. The
  switch's button-press-delay window aggregates a multi-tap into one event, so a
  triple tap emits `multi_press_3` alone (no `multi_press_1`/`_2` alongside it).
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
- **One automation per room.** `automation.<prefix>_ceiling_fan_wall_control`
  carries the non-binding links (config button gestures, down/up paddle holds,
  fan → speed memory + LED blip) on four triggers with a top-level `choose` on
  `condition: trigger id`. This keeps every room a single reviewable unit and the
  behaviour identical across rooms. `mode: queued` (max 10) so fan-change runs
  process in order and the snapshot guard can't interleave with itself.
- **The bar rests dark and only blips on a change — at all hours.** Over Matter
  the bar is one RGB light — no per-segment / level-meter control (unlike the
  Zigbee White series). An earlier design left the bar steadily lit (50 % awake,
  1 % at night) for as long as the fan ran; after living with the night-only blip
  for a few days, the resting-dark bar was preferred around the clock. Now the
  bar is dark at rest whatever the fan is doing, and lights transiently to
  acknowledge a change: the new speed's hue for 3 s (teal low 175 / blue medium
  220 / violet high 265), or **amber-gold (hue 50) for 3 s** when the fan is
  switched off. The off blip exists because a dark resting bar gives a
  double-tap-off no visual confirmation at all. Amber, not red: red is kept in
  reserve for a real alert.
- **This bar renders warm hues far dimmer than cool hues — the off blip is
  pushed brighter and greener to compensate.** The speed hues (175–265) are all
  blue-heavy and this bar's blue channel is bright. A saturated amber at hue 30
  has no blue, leans on red + green, and rendered so dim it was invisible in a
  lit room even though the `light.turn_on` executed and the bar entity read `on`
  for the full 3 s. The off blip now uses **hue 50** (amber-gold — more green,
  which renders brighter here) at its **own higher brightness: 100 % awake /
  40 % asleep**, versus 75 / 25 for the speed blips. If hue 50 still washes out,
  the next move is a hue with blue content (magenta ~315) or white — not a
  warmer amber.
- **The off blip is solid, not animated.** An earlier version added a
  `Fast Falling` animation on `select.<prefix>_ceiling_fan_switch_led_effect` for
  a "powering down" motion. It was dropped as a simplification when the off blip
  was reworked for visibility — one channel, one `light.turn_on`, same shape as
  the speed blips. Nothing writes the effect select now; its **resting value must
  stay `Solid`, not `Off`** — `Off` blanks the RGB notification channel and every
  blip (speed and off) stops rendering. `Solid` at `LED Intensity` 0 is still
  dark at rest.
- **Blip brightness follows the room's sleep boolean: 75 % awake, 25 % asleep.**
  15 % (the old night-only value) is hard to read in a sunlit room; 75 % at 3 a.m.
  defeats the dark adaptation the blip is meant to preserve. The blip script
  reads `input_boolean.<sleep>` once at fire time to pick `level`. This is the
  only place the sleep boolean touches the LED path — the automation no longer
  has a sleep trigger or a sleeping/awake branch.
- **The blip lives in a per-room script, not an inline `delay`.** The wall-control
  automation is `mode: queued` and shares that queue with the config-button
  gestures, so an inline `delay` would stall tap handling behind LED animations
  (the same failure that made the earlier bare-`state` + 1 s delay version stick
  on one colour). `script.<prefix>_ceiling_fan_led_blip` (`mode: restart`) runs
  the delay outside that queue; the automation fires it with `script.turn_on` and
  returns immediately. `restart` also buys the right feel for free: cycling
  low→medium→high keeps the bar lit and resets the timer, so it darkens 3 s after
  you *stop*, and a fan-off landing mid-speed-blip swaps straight to the solid
  amber ack.
- **The blip restores what the bar was showing, it doesn't blindly turn it off.**
  The bar is the room's one always-idle ambient surface, so it's the natural home
  for a future status colour (guest mode, an alert, a laundry indicator). Rather
  than hard-coding "dark" as the resting state, the automation snapshots both LED
  channels — `light.<prefix>_ceiling_fan_switch_led` and
  `select.<prefix>_ceiling_fan_switch_led_effect` — into
  `scene.<prefix>_ceiling_fan_led_restore` via `scene.create` *before* firing the
  blip, and the blip's tail re-asserts that scene (`scene.turn_on`), falling back
  to `light.turn_off` only when the scene doesn't exist — a bare manual
  `script.turn_on`, since the automation always snapshots first. Existence is
  tested with `states.scene.<id> is not none`, not `states()` / `has_value()`: a
  freshly `scene.create`d scene reads `unknown` until first activated. The effect
  select is still in the snapshot even though no blip writes it any more (the
  `Fast Falling` step was dropped) — it costs one Matter Mode Select write on the
  restore, off the critical path (after the 3 s hold), and keeps the restore
  layer ready if a future status colour or a working effect ever drives that
  channel. Aside from the fan automation
  nothing else drives the bar today (`LED Intensity(On)`/`(Off)` are both 0), so
  the RGB half of the snapshot is "off" and that half of the restore is a no-op —
  the layer is built now so a future owner of the bar needs zero coordination with
  this automation.
- **The snapshot is guarded on the blip script being idle.** The blip is
  `mode: restart`, so a second fan change mid-blip restarts it. An unguarded
  re-snapshot would then capture the *blip's own colour* as the resting state and
  leave the bar stuck lit. Guarding the `scene.create` on
  `script.<prefix>_ceiling_fan_led_blip` being `off` means a burst snapshots once
  and every restart reuses that first scene. `mode: queued` on the automation
  keeps its runs serialised so the check can't race itself. `scene.create` scenes
  are runtime-only (gone on restart, recreated on the next blip) and show as
  non-editable rows under Settings → Automations & Scenes → Scenes — accepted
  clutter for a restore layer that costs no helper.
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
rebuild. On both devices, delete the dead originals and rename the surviving
`…_2` entity back to the clean slug:

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
| Smart Bulb Mode | Enabled | Keeps the load permanently powered so the paddle emits Matter commands (events / bindings) instead of chasing the empty local relay. Required for the binding to fire. Live entity: `select.*_ceiling_fan_switch_smart_bulb_mode` = `Smart Bulb Enable`. |
| Control of switch load | `Remote & paddle control` (default — **do not** change) | On the White series the outgoing On/Off binding is triggered by the paddle's local load action. Setting this to `Remote control only` (to stop the phantom `switch.*_ceiling_fan_switch_load_control` toggle) also kills the paddle → light binding, even with Smart Bulb Mode on. Leave it at `Remote & paddle control` and accept the internal-relay toggle as the cost of a working binding. See `LESSONS.md`; Inovelli may decouple these in a later firmware. Live entity: `select.*_ceiling_fan_switch_control_of_switch_load`. |
| Dimming Speed (Simulated) | `Instant` (default — leave it) | Only mattered for the removed cluster 8 (Level Control) binding — it set the ramp time for a paddle press-and-hold dim. With cluster 8 gone and the hold gesture handled in the HA automation ([Step 6](#step-6--ha-automation)), this parameter is inert; leave it at the factory default. Historical note if the binding is ever re-added: `Instant` emits no Move/Step, `2s` was the only reliable value, `3s` regressed intermittently, `500ms`–`1s` ramped too fast to land a level. Live entity: `select.*_ceiling_fan_switch_dimming_speed_simulated`. |
| LED bar color | Blue | Bedroom indicator. The wall-control automation drives colour via the light entity; the `LED Color` parameter is the fallback if the light-entity route ever stops holding, and it is also the colour the `LED Effect` animation plays in. |
| `LED Effect` (`select.*_ceiling_fan_switch_led_effect`) | `Solid` | Resting value, and nothing moves it — the fan-off blip's old `Fast Falling` step was dropped as a simplification. **Not `Off`** — `Off` blanks the RGB notification channel and every blip stops rendering. `Solid` at `LED Intensity` 0 is still dark at rest. |
| `LED Intensity(On)` **and** `LED Intensity(Off)` | `0` | The switch keeps an internal on/off state (toggled by the paddle even in Smart Bulb Mode — this is what fires the binding, see the `Control of switch load` row) and lights the bar to `LED Intensity(On)` / `(Off)` for it. Zeroing both means that native indicator never shows, so the bar reflects *only* the fan-speed automation. Each is exposed **twice** — a **select** and a `… (Load Control)` **number** — set all four to `0` per switch. The two `(Load Control)` numbers occasionally re-read their factory defaults (`33` / `1`) after a Matter Server restart; re-zero them if the bar starts glowing faintly at rest. The automation drives the bar through a separate RGB-notification channel that still works with the intensities at 0. |

## Step 4 — Matter binding: paddle → light

Done in the Matter Server Web UI.

1. Open node **11** (Ceiling Fan Switch). Node IDs come from the Matter
   identifier on the device page (`deviceid_…-00000000000000NN-…`, hex).
2. Find the endpoint exposing the **Binding** cluster — **endpoint 2** on the
   VTM30-SN (endpoint 1 is the dead Load relay).
3. Add one binding target, to node **10** (Ceiling Fan canopy), **endpoint 1**
   (the Dimmable Light — *not* endpoint 2, the fan):
   - cluster **6 (On/Off)** — paddle tap → light on/off
4. If the UI has a separate ACL step, add an entry on node 10 granting node 11
   operate access. Most binding UIs write the ACL automatically.
5. Test at the wall: tap up → light on (full, per the On level parameter), tap
   down → light off. Confirm it still works with Home Assistant stopped.

The paddle **hold** is not bound — it is an HA automation
([Step 6](#step-6--ha-automation)). An earlier build also bound cluster **8
(Level Control)** here for paddle press-and-hold → local dim; that target was
removed when the hold gesture was remapped to whole-room off/on. To restore
hold-to-dim, re-add a cluster 8 target to node 10 / endpoint 1, set
`Dimming Speed (Simulated)` = `2s` ([Step 3](#step-3--switch-vtm30-sn-parameters)),
and drop the down/up-hold branches from the automation so the local ramp and the
automation don't fight.

> **Rebuild the binding after a canopy firmware update.** VTM36 `1.0.1r1`
> reworked the binding implementation; per Inovelli's advisory, bindings created
> before the update may silently stop firing. If the paddle goes dead after an
> update: delete the cluster 6 binding on the switch and the canopy, power-cycle
> both (breaker off ~10 s), then recreate it with the steps above. See
> [Updating the canopy firmware](#updating-the-canopy-firmware-101r1).

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
| Triple tap (`multi_press_3`) | any | Snapshot the bar, then blip the current speed — fan untouched |

**Paddle hold** (`event.*_button_down` / `event.*_button_up`) — each branch fires
on the entity changing and gates on its `event_type` attribute being
`long_press`, so a tap on the same paddle (`multi_press_1`, handled by the cluster
6 binding, not this automation) doesn't match:

| Paddle gesture | Result |
|---|---|
| Hold down (`long_press`) | `fan.turn_off` + `light.turn_off` |
| Hold up (`long_press`) | `fan.set_percentage` to the remembered speed + `light.turn_on` (full, per On level 254) |

`long_press` fires while the paddle is still held (~1 s in), not on release —
`long_release` is left unmapped. No de-dup guard: `mode: queued` plus idempotent
actions make a repeat `long_press` a no-op.

**LED acknowledgement.** Every hold blips the bar — amber-gold for the down
(off) gesture, the resumed speed's hue for the up (on) gesture. When the
gesture actually changes the fan (hold down while it's running, hold up while
it's off), the `percentage` branch below fires the blip. When it doesn't (hold
down while already off, hold up while already at the last speed), that branch
never runs, so the hold branch fires the blip itself — guarded on the fan's
*pre-call* state (`fan == off` for down, `fan == on` for up; the fan entity still
reads its old value here because of Matter round-trip lag) so the two paths never
both fire for the same gesture, and snapshot-guarded like the peek branch.

**Fan `percentage` attribute change** (triggering on the attribute means the
value is already settled — no delay):

1. Resolve the current speed band into a `speed` variable
   (`off`/`low`/`medium`/`high`).
2. If the fan is on, write `speed` to `input_select.*_ceiling_fan_last_speed`
   (skipped when off, so the memory survives an off/on cycle).
3. If `script.*_ceiling_fan_led_blip` is `off` (no blip in flight), snapshot
   `light.*_ceiling_fan_switch_led` **and**
   `select.*_ceiling_fan_switch_led_effect` into `scene.*_ceiling_fan_led_restore`
   via `scene.create`.
4. `script.turn_on` the blip script and return. The script shows the
   acknowledgement (speed hue for 3 s at 75 / 25 % brightness, or amber-gold
   hue 50 for 3 s at 100 / 40 % on a fan-off — warm hues render dim on this bar,
   so the off blip runs brighter), holds, then re-asserts
   `scene.*_ceiling_fan_led_restore` — or `light.turn_off` if that scene doesn't
   exist.

`mode: queued`, `max: 10` — runs process in order, so the "no blip in flight"
snapshot guard can't race itself. The blip's timed hold runs in the
`mode: restart` script, off this queue.

## Scale reference

Fan speed (VTM36 3-speed): `1–33% = low`, `34–66% = medium`, `67–100% = high`.
The automations use 33 / 66 / 100, with `< 45` / `< 78` band edges to absorb the
Matter fan's percentage rounding.

LED bar — **dark at rest at all hours**, whatever the fan is doing. It only blips
to acknowledge a change, then restores whatever it was showing before (dark
today). Every blip is a solid colour on the RGB channel (`light.turn_on` with
`hs_color`), distinguished by hue. This bar renders **cool hues bright and warm
hues dim** (its blue channel is strong; hue 30 has no blue and washed out
entirely), so the fan-off blip runs at hue 50 and a higher brightness than the
speed blips.

| Fan | RGB hue (`hs_color`) | Blip hold | Blip brightness (awake / asleep) |
|---|---|---|---|
| off | 50 (amber-gold) | 3 s | 100% / 40% |
| low | 175 (teal) | 3 s | 75% / 25% |
| medium | 220 (blue) | 3 s | 75% / 25% |
| high | 265 (violet) | 3 s | 75% / 25% |

The effect select (`select.*_ceiling_fan_switch_led_effect`) is never written by
a blip — an earlier `Fast Falling` step on the fan-off blip was dropped as a
simplification.

"Dark at rest" needs: the blip's tail restores the pre-blip snapshot (RGB
`off` + effect `Solid`) or does `light.turn_off`, **and** the switch's
`LED Intensity(Off)` param is `0` so the native fallback (HA down) is also dark.
The effect select rests on `Solid`, not `Off` — `Off` blanks the RGB
notification channel and every blip stops rendering.

## Replicating for another room

This setup is a per-room pattern. Avery's Room is the first instance and the
Master Bedroom the second; Living Room and Office are planned and use the same
build. Every room is configured identically apart from the substitutions below.
To add a room, work through Steps 1–6 with these substitutions and keep every
parameter value the same.

**Per-room substitutions:**

| Placeholder | Avery's Room | Master Bedroom | Living Room | Office |
|---|---|---|---|---|
| Area / entity prefix | `averys_room` | `master_bedroom` | `living_room` | `office` |
| Canopy device name | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` | `Ceiling Fan` |
| Switch device name | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` | `Ceiling Fan Switch` |
| Canopy Matter node | 10 | 12 | TBD | TBD |
| Switch Matter node | 11 | 13 | TBD | TBD |
| Sleep boolean (blip brightness) | `input_boolean.avery_sleeping` | `input_boolean.everyone_sleeping` | `input_boolean.everyone_sleeping` | `input_boolean.everyone_sleeping` |
| Restore scene (created at runtime) | `scene.averys_room_ceiling_fan_led_restore` | `scene.master_bedroom_ceiling_fan_led_restore` | `scene.living_room_ceiling_fan_led_restore` | `scene.office_ceiling_fan_led_restore` |

Only Avery's Room has a person-specific sleep toggle; the other rooms use the
household `input_boolean.everyone_sleeping` (household sleep ≈ everyone in bed).

If the canopy ships on `1.0.0`, update it to `1.0.1r1` and run the cleanup in
[Updating the canopy firmware](#updating-the-canopy-firmware-101r1) before Step 2
— otherwise the entity IDs and the minimum-dim control below will not match.

**Identical across every room — do not vary:**

- Canopy: `Light Mode` = `Trailing Dimmer`; `Fan Mode` = `Ceiling (3 Speed)`;
  `Minimum dim level` = `13%`; `On level` (light endpoint) = `254`; power-on
  behaviour = `previous`; light transition time (`On` / `Off` / `On-Off`) =
  `0.5` s
- Switch: Single-pole; Smart Bulb Mode enabled; `Control of switch load` left at
  `Remote & paddle control` (changing it breaks the binding — see Step 3); LED
  colour Blue; `LED Effect` = `Solid` (**not `Off`** — `Off` blanks the RGB
  notification channel the blips use); `LED Intensity(On)` **and** `(Off)` = `0`
  (all four entities — select + number, each ×2) so only the fan automation lights
  the bar; `Dimming Speed (Simulated)` left at `Instant` (the cluster 8 binding
  that used it is not present)
- Binding: switch Binding endpoint → canopy light endpoint 1, cluster **6
  (On/Off)** only — paddle tap → light on/off. No cluster 8 (Level Control)
  binding; the paddle hold is handled by the automation instead
- Automation: one `automation.<prefix>_ceiling_fan_wall_control`, category
  Climate, label `int_inovelli_fan_canopy`, `mode: queued` max 10, four triggers
  (config button, fan `percentage`, down paddle hold, up paddle hold)
- Script: one `script.<prefix>_ceiling_fan_led_blip`, `mode: restart`
- Speed bands 33 / 66 / 100 with `< 45` / `< 78` edges; bar dark at rest at all
  hours; every blip a solid `hs_color` for 3 s — speed hues 175 / 220 / 265 at
  75 / 25 % brightness, fan-off hue 50 at 100 / 40 % (warm hues render dim on
  this bar); no blip writes `select.<prefix>_ceiling_fan_switch_led_effect` (it
  stays `Solid`), though the restore scene still snapshots it alongside the RGB
  bar
- Gestures: config button — 1 tap cycles / resumes, 2 taps off, 3 taps peek;
  paddle hold down → fan + light off, hold up → fan (last speed) + light on; both
  holds blip the bar (solid amber for off, speed hue for on)

Each room gets its own copies with the prefix and sleep boolean substituted:

- `automation.<prefix>_ceiling_fan_wall_control`
- `script.<prefix>_ceiling_fan_led_blip`
- `input_select.<prefix>_ceiling_fan_last_speed`
- `scene.<prefix>_ceiling_fan_led_restore` — nothing to pre-create; the
  automation makes it with `scene.create` on the first blip

The `int_inovelli_fan_canopy` label and this guide are shared.

**Parity check.** The per-room automation and script copies must differ *only* by
the entity prefix, the sleep boolean (`avery_sleeping` vs `everyone_sleeping`),
the automation `id`, and the friendly-name prefix in `alias` / `description`.
After editing any room, `diff` its `ha/` mirror against another room's to confirm
nothing else diverged — any other difference is a bug.

**Why four copies, not a blueprint.** The blip script has to be per-room:
`mode: restart` is what keeps the bar lit through a burst and resets the 3 s
timer, and a script shared across rooms would have to be `mode: parallel`, which
breaks that within a room. Collapsing the automations into one templated
multi-room automation, or into a blueprint, means templated `target.entity_id`
(the GUI editor then shows only an inputs form — against the house preference for
GUI-editable automations) and one `mode: queued` shared across rooms. There is
also no blueprint convention in this repo and no MCP tool that writes a blueprint
file. Four self-contained copies kept honest by the parity check is the accepted
cost.

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
8. **Verify**: paddle on/off; config-button speed cycle (1 tap); the LED bar
   dark at rest and blipping the speed's hue for ~3 s on a change, amber-gold
   for ~3 s on a double-tap off, then returning to dark; the triple-tap peek
   showing the current speed without moving the fan; a change made while the room's
   sleep boolean is on
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
| Avery's Room Ceiling Fan LED Restore | `scene.averys_room_ceiling_fan_led_restore` | Transient scene — `scene.create`d by the automation before each blip, holds the pre-blip state of `light.averys_room_ceiling_fan_switch_led` + `select.averys_room_ceiling_fan_switch_led_effect`; not persisted, gone on restart and recreated on the next blip |
| Master Bedroom Ceiling Fan LED Restore | `scene.master_bedroom_ceiling_fan_led_restore` | Transient scene — as above, for the `master_bedroom` entities |
| Ceiling Fan | `fan.averys_room_ceiling_fan` / `light.averys_room_ceiling_fan_light` | Matter device (VTM36) |
| Ceiling Fan Switch | `event.averys_room_ceiling_fan_switch_button_config` et al. | Matter device (VTM30-SN) |

## Related files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `ha/automations/automation.averys_room_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Avery's Room wall-control automation |
| `ha/automations/automation.master_bedroom_ceiling_fan_wall_control.yaml` | HA automation registry | Mirror — Master Bedroom wall-control automation |
| `ha/scripts/script.averys_room_ceiling_fan_led_blip.yaml` | HA script registry | Mirror — Avery's Room night LED-bar acknowledgement blip |
| `ha/scripts/script.master_bedroom_ceiling_fan_led_blip.yaml` | HA script registry | Mirror — Master Bedroom night LED-bar acknowledgement blip |
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

**Paddle hold does nothing.** The hold gesture is an HA automation, not a binding
— it does nothing with HA stopped, and nothing if the automation is disabled.
When HA is up, watch `event.*_ceiling_fan_switch_button_down` /`_up` in Developer
Tools while holding: the `event_type` attribute must land on `long_press`. If a
hold reports only `multi_press_1`, the switch's button-press-delay / long-press
threshold is off — adjust it on the switch. (There is intentionally no
hold-to-dim: the cluster 8 binding that provided it was removed — see
[Step 4](#step-4--matter-binding-paddle--light).)

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

**LED bar blip doesn't show, or the bar won't go dark.** If a firmware update
makes the switch snap the LED back to its default indicator after `light.turn_on`
(so the blip is invisible or the restore can't hold), fall back to the native
`LED Intensity(Off)` select for the indicator (blue is already the parameter
colour). Separately, if the bar is stuck lit on a blip colour, a `scene.create`
snapshot captured a blip colour as the resting state — check the automation's
snapshot step is still guarded on `script.<prefix>_ceiling_fan_led_blip` being
`off`. Clearing it: `scene.turn_on` won't help (the scene *is* the wrong state);
`light.turn_off` the bar, then trigger a fresh fan change to re-snapshot.

**Paddle does nothing after a firmware update.** Two causes. (1) Smart Bulb Mode
reset — confirm `select.*_ceiling_fan_switch_smart_bulb_mode` still reads
`Smart Bulb Enable`; without it the paddle drives the (empty) local relay instead
of emitting the bound command. (2) The binding stopped firing — VTM36 `1.0.1r1` reworked the
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
