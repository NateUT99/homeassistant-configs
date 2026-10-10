# Energy Monitoring

*Last updated: October 2026*

## Overview

Whole-home electricity monitoring via a Rainforest EAGLE-3, which pairs with the utility
smart meter over Zigbee (HAN) and exposes real-time demand and lifetime energy registers on
its local REST API. Home Assistant's built-in `rainforest_eagle` integration polls the
device on the LAN and publishes three sensors. The lifetime "delivered" register feeds the
Home Assistant Energy Dashboard as the grid-consumption source, with a fixed per-kWh price
applied for cost tracking.

---

## Architecture

```
Utility smart meter
      │ Zigbee (HAN)
      ▼
Rainforest EAGLE-3 ── local REST API (HTTP Basic: Cloud ID + Install Code)
      │ Wi-Fi / LAN
      ▼
HA  rainforest_eagle  (local polling)
      │
      ├─ sensor.household_energy_monitor_power_demand            kW,  power,  measurement
      ├─ sensor.household_energy_monitor_total_energy_delivered  kWh, energy, total_increasing
      └─ sensor.household_energy_monitor_total_energy_received   kWh, energy, total_increasing
                    │
       total_energy_delivered
                    ▼
      Energy Dashboard ── grid source "Grid Consumption", fixed price $0.2033/kWh
```

### Design decisions

**Local polling, not the Rainforest cloud.** The integration talks to the device at its LAN
address using credentials printed on the device. Energy data stays on the LAN and monitoring
survives an internet outage. The device's separate cloud uploader is independent of this
integration and can be left on or off.

**`total_energy_delivered` feeds the dashboard, not `power_demand`.** The Energy Dashboard
consumes kWh statistics with `state_class: total_increasing`; instantaneous kW cannot be a
grid source. Using the meter's own lifetime register avoids a Riemann-sum helper and the
integration error it would introduce.

**Fixed price, not a rate entity.** The tariff is a flat residential rate, so a single
`number_energy_price` is sufficient. The value is owned by the Reference Values table below.

**`total_energy_received` is mapped but idle.** There is no solar or export, so it stays at
`0.0`. The dashboard pairs it automatically and it is ready if on-site generation is added.

**Individual devices.** The EAGLE reads the revenue meter only, so per-device breakdown
comes from each device's own energy sensor added under "Individual devices". The washer
(`lg_thinq`) reports `energy_today` with `state_class: total` and a midnight `last_reset` —
the correct shape for this section, since HA stitches the daily resets into a continuous
long-term statistic. Only `energy_today` is added; `energy_yesterday`/`energy_this_month`/
`energy_last_month` are the same underlying data at coarser windows and would double-count
if also added. The dryer exposes no energy sensor via either the official `lg_thinq`
integration or the HACS `ha-smartthinq-sensors` alternative, so it can't be tracked here.

The dishwasher's Third Reality plug (ZHA) reports `summation_delivered` — a lifetime kWh
register with `state_class: total_increasing` already, so it feeds the dashboard directly
with no daily-reset stitching needed (unlike the washer's `energy_today`). The plug's
Metering only mode is enabled and Power-on behavior is set to On, so it acts as a pass-through
meter rather than a switched outlet; the `switch.kitchen_dishwasher` on/off control is disabled
since toggling it is a no-op in this mode.

**Dishwasher cycle detection.** The plug's `power_rise_threshold` / `power_drop_threshold`
(15W / 5W) drive `binary_sensor.kitchen_dishwasher_opening` — a ZHA power-threshold-crossing
flag repurposed from an "opening" cluster, renamed "Dishwasher Power Threshold" and hidden
since its name no longer describes a door. Observed over a real cycle, the raw signal flips
on/off 40+ times in ~80 minutes: the wash/drain pump load is bursty (20–90W bursts separated
by sub-5W troughs), not flat, so the raw flag reads "off" repeatedly during troughs that are
really just gaps between pump bursts. `binary_sensor.kitchen_dishwasher_running`
(`ha/packages/dishwasher_running.yaml`) debounces this with `delay_off: 4m30s`, collapsing the
blips into one clean on/off span per cycle. Some troughs run close to 4 minutes, so `delay_off`
needs margin above that or the sensor reports false "off" spans mid-cycle. `delay_off` has no
Template Helper config-flow field, so this is a YAML `template:` package rather than a
UI-created helper.

**Refrigerator.** Same plug model and configuration as the dishwasher — Metering only mode
enabled, Power-on behavior On, `sensor.kitchen_refrigerator_summation_delivered` feeding the
dashboard directly. `power_rise_threshold` / `power_drop_threshold` are set symmetrically to
15W / 15W. The resulting `binary_sensor.kitchen_refrigerator_compressor` (originally registered as
`_opening`; renamed to **Refrigerator Compressor** with a `running` device-class override,
and its entity_id manually renamed to match) is a **momentary edge pulse, not a level
sensor** — confirmed by
live testing (dropping both thresholds to the minimum, 1W, produced zero additional events
during 2+ minutes of steady ~55W running, because the device simply stops emitting power
reports once nothing is changing enough to report). It fires briefly on a rise or fall and
then reverts to `off` regardless of whether the load is still present, so no rise/drop
threshold value makes it hold a sustained "compressor is running" state — that isn't what this
cluster measures. It's left visible as a "something just changed" pulse, not a running/idle
indicator. A real running/idle signal would need a `threshold` helper on
`sensor.kitchen_refrigerator_power` instead (native HA level detector with hysteresis) —
not yet built.

`switch.kitchen_refrigerator` is **hidden, not disabled**, unlike the dishwasher's identical
control. A disabled entity is removed from the state machine entirely, and
Kitchen: Refrigerator Keep Powered (`automation.kitchen_refrigerator_keep_powered`) needs to
watch this entity's state to catch the relay ever actually switching off — something Metering
only mode should make impossible, which is exactly why it's worth watching for. Hidden keeps
it off dashboards while staying live for the automation.

**Refrigerator temperature.** The plug can only show whether the fridge has power. An Aqara
temperature sensor (`lumi.weather`, ZHA, device **Refrigerator Climate**) sits inside the fridge
on the middle shelf, toward the back, away from the door and the cold-air vent. It answers
whether the food is cold, and it keeps working when the plug or its outlet fails.
`sensor.kitchen_refrigerator_climate_temperature` normally reads about 35–37°F, rising and
falling slightly with each compressor cycle. The sensor reports on change and sends a
heartbeat about once an hour, so `last_reported` should never go much past an hour.

Three automations guard the refrigerator, all category Maintenance:

- **Kitchen: Refrigerator Power Monitor**
  (`automation.kitchen_refrigerator_power_monitor`) — alerts on three faults:
  - **Plug silent for 15 minutes** — neither `sensor.kitchen_refrigerator_voltage` nor
    `sensor.kitchen_refrigerator_current` has reported (`last_reported`). ZHA waits 2 hours
    before marking a mains-powered device `unavailable`, so a hung plug looks healthy to HA
    for that whole window; this check is what catches it. Voltage and current are the
    freshness signals because grid voltage drifts constantly, so they update every few
    seconds even when the fridge is idle. Power does not: the plug stops sending it while
    the load is steady, and gaps of 10+ minutes are normal.
  - **Plug `unavailable` for 10 minutes** — the backstop for a plug that is already missing
    when HA or ZHA starts.
  - **Under 5W for 2 hours** — breaker trip, unplugged cord, or a dead compressor. Outages are
    covered by the whole-house generator, so this branch only catches faults HA can still see.

  The automation is `mode: single` with `max_exceeded: silent`, so a hung plug that later
  also goes `unavailable` stays one alert and one recovery notice. Alerts are a standard
  push, not critical: a plug or power fault only matters if the food warms, and the
  Temperature Monitor below alerts critically when it does.
- **Kitchen: Refrigerator Temperature Monitor**
  (`automation.kitchen_refrigerator_temperature_monitor`) — alerts on two faults:
  - **Above 41°F for 45 minutes** — 41°F is the food-safety limit. The 45-minute window
    rides out a long door-open while loading groceries.
  - **Sensor silent for 2 hours** — no `last_reported` from the temperature sensor. That is
    two missed heartbeats. ZHA waits 6 hours before marking a battery device `unavailable`.

  It is a separate automation from the Power Monitor because of the Power Monitor's
  `mode: single`: a too-warm alert arriving while a plug-silent run waits for recovery
  would be silently dropped, and a dead outlet produces exactly that sequence. This one is
  `mode: parallel` (`max: 2`). Each trigger must clear before it can fire again, and
  clearing ends its own run's wait, so the two faults never block each other and never
  duplicate. Alerts route by presence and sleep state: a critical push when no one is home;
  otherwise through `script.household_tts_announce` — a broadcast when someone is home and
  awake, or the master bedroom with `critical_fallback: true` when everyone is asleep.
- **Kitchen: Refrigerator Keep Powered**
  (`automation.kitchen_refrigerator_keep_powered`) — if Metering only mode itself turns off,
  re-enables it immediately; if the relay reports `off`, waits 2 minutes (debounce) and then
  restores the relay, Metering only mode, and Power-on behavior together, since an `off`
  relay means the whole protective config likely broke, not just the switch. Always critical,
  regardless of presence — self-healing doesn't make the underlying fault less worth seeing.
  Suppressed by `input_boolean.kitchen_refrigerator_maintenance`.

---

## Prerequisites

- Rainforest EAGLE-3, commissioned to the utility smart meter (paired at the meter; the
  utility may need to authorize the HAN device)
- EAGLE-3 reachable on the LAN at a stable IP — it is on Wi-Fi, so a DHCP reservation is
  required
- Cloud ID and Install Code from the label on the underside of the device
- Built-in `rainforest_eagle` integration (no HACS component involved)
- A recent electricity bill, to compute the all-in effective rate

---

## Steps

### 1. Commission the EAGLE-3 to the meter

Use the Rainforest setup portal to pair the device with the smart meter. Some utilities
require the HAN device's MAC/Install Code to be registered before the meter will provision
it. Confirm the device reports live demand before continuing.

### 2. Reserve the device IP

Add a DHCP reservation for the EAGLE-3 on the router. The integration polls a fixed host; a
lease change silently breaks it, and Wi-Fi clients are the most likely to move.

### 3. Add the integration

**Settings → Devices & Services → Add Integration → Rainforest EAGLE**. Enter the Cloud ID
and Install Code, and the host if it is not discovered. The integration creates the
**Household Energy Monitor** device with the three sensors listed in Related HA Config.

Entity IDs follow the device Name `Household Energy Monitor` — `household_` scope per
`standards/naming.md`, no area prefix.

### 4. Add the grid source to the Energy Dashboard

**Settings → Dashboards → Energy**, then under **Electricity grid → Add consumption**:

| Field | Value |
|---|---|
| Consumed energy | `sensor.household_energy_monitor_total_energy_delivered` |
| Use an energy price | Fixed price |
| Price | `0.2033` |

Name the entry `Grid Consumption`. Leave **Return to grid** empty; the UI auto-links
`sensor.household_energy_monitor_total_energy_received`, which is harmless while it reads
`0.0`.

### 5. Verify

Long-term statistics are computed on the hour. The first bar and the cost figure appear
after the next hour boundary. There is no historical backfill — data begins when the source
was added.

---

## Reference Values

| Item | Value |
|---|---|
| Utility | FirstEnergy — residential service |
| Account number | `5001502452` |
| Supply rate (energy charge only) | `11.09` ¢/kWh |
| All-in effective rate (bill total ÷ kWh billed) | `$0.2033` /kWh |
| Energy Dashboard price field | `number_energy_price = 0.2033` |

The all-in rate includes supply, delivery/distribution, fixed service charges, and taxes
spread across metered kWh — it is roughly double the supply rate and is what makes the
dashboard's cost figure track the real bill.

> **Coordinated change:** the price is stored in two places — this table and the Energy
> Dashboard grid source (Step 4). If a later bill's all-in rate changes materially, update
> both. Price changes apply going forward only; past cost data is not recomputed.

---

## Security Summary

| Control | Detail |
|---|---|
| Authentication | HTTP Basic — Cloud ID (username) and Install Code (secret), both printed on the device |
| Transport | Unencrypted HTTP on the LAN; the local API offers no TLS |
| Network exposure | LAN-only, polled at the device's local IP; no inbound internet path |
| Credential storage | Held in the HA config entry (`.storage/core.config_entries`); never committed to this repo |
| Least privilege | The device is read-only telemetry to HA, but its local API also allows cloud-uploader reconfiguration — keep it on the trusted/IoT segment |
| Worst case if compromised | An attacker already on the LAN could read whole-home demand and consumption (which reveals occupancy patterns) and repoint the device's cloud uploader. No control of HA or any home device; no billing or account credentials are exposed. |

---

## Related HA Config

| Friendly Name | Entity ID | Type |
|---|---|---|
| Household Energy Monitor Power demand | `sensor.household_energy_monitor_power_demand` | Sensor (`rainforest_eagle`) — instantaneous kW |
| Household Energy Monitor Total energy delivered | `sensor.household_energy_monitor_total_energy_delivered` | Sensor (`rainforest_eagle`) — kWh, grid-consumption statistic |
| Household Energy Monitor Total energy received | `sensor.household_energy_monitor_total_energy_received` | Sensor (`rainforest_eagle`) — kWh, export statistic (idle, no generation) |
| Grid Consumption | Energy Dashboard grid source | `.storage/energy` — consumed energy = Total energy delivered; fixed price per Reference Values |
| Washer | Energy Dashboard individual device | `.storage/energy` — consumed energy = `sensor.utility_room_washer_energy_today` (`lg_thinq`) |
| Dishwasher | Energy Dashboard individual device | `.storage/energy` — consumed energy = `sensor.kitchen_dishwasher_summation_delivered` (ZHA, Third Reality metering plug) |
| Dishwasher Power | `sensor.kitchen_dishwasher_power` | Sensor (ZHA) — instantaneous W |
| Dishwasher (switch, disabled) | `switch.kitchen_dishwasher` | ZHA — relay control, disabled; metering-only mode makes toggling it a no-op |
| Dishwasher Power Threshold (hidden) | `binary_sensor.kitchen_dishwasher_opening` | ZHA — raw power-threshold flag; flaps during a cycle, kept as input to the sensor below |
| Dishwasher Running | `binary_sensor.kitchen_dishwasher_running` | Template sensor (package) — debounced cycle-running flag, `delay_off: 4m30s` |
| Refrigerator | Energy Dashboard individual device | `.storage/energy` — consumed energy = `sensor.kitchen_refrigerator_summation_delivered` (ZHA, Third Reality metering plug) |
| Refrigerator Power | `sensor.kitchen_refrigerator_power` | Sensor (ZHA) — instantaneous W |
| Refrigerator (switch, hidden) | `switch.kitchen_refrigerator` | ZHA — relay control, hidden not disabled; watched by Keep Powered below |
| Refrigerator Compressor | `binary_sensor.kitchen_refrigerator_compressor` | ZHA — power-threshold-crossing edge pulse (15W rise/drop), renamed and re-classed `running`; momentary, not a running/idle level indicator |
| Refrigerator Climate Temperature | `sensor.kitchen_refrigerator_climate_temperature` | Sensor (ZHA, Aqara `lumi.weather`) — air temperature inside the fridge, °F |
| Refrigerator Power Monitor | `automation.kitchen_refrigerator_power_monitor` | Automation — silent/offline/no-draw alerting |
| Refrigerator Temperature Monitor | `automation.kitchen_refrigerator_temperature_monitor` | Automation — too-warm/sensor-silent alerting |
| Refrigerator Keep Powered | `automation.kitchen_refrigerator_keep_powered` | Automation — self-heals an unexpected relay/metering-only-mode off |
| Refrigerator Maintenance | `input_boolean.kitchen_refrigerator_maintenance` | Helper — suppresses Keep Powered during deliberate plug work |

---

## Troubleshooting

### Sensors drop to `unavailable` intermittently

The Wi-Fi EAGLE-3 has gone offline or picked up a new IP. Confirm the DHCP reservation from
Step 2 is in place and the device is on a stable band.

### Totals do not advance while `power_demand` reads fine

Some meters withhold the summation (lifetime energy) registers from the HAN even when demand
is published. The utility may need to enable summation reporting on the meter. Until then the
Energy Dashboard has no usable consumption statistic.

### `total_energy_received` stays at `0.0`

Expected — there is no solar or net-metered export feeding the meter.
