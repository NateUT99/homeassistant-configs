# Energy Monitoring

*Last updated: September 2026*

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

**No per-device breakdown.** The EAGLE reads the revenue meter only. Individual-device
consumption in the dashboard requires separate per-circuit or per-plug energy sensors added
under "Individual devices".

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
