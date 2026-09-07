# Generac Generator Monitoring

*Last updated: September 2026*

---

## Overview

The Generac MobileLink cloud integration monitors the whole-home standby generator, exposing its connectivity, run status, and diagnostic metadata as HA entities on the "Home Generator" device (area: Outside). A trigger-based template sensor layered on top of the integration's status sensor records the last time the generator actually ran, since the integration itself only exposes point-in-time status, not a history of run events.

## Architecture

```
Generac MobileLink cloud API
        │
        ▼
Generac integration (config entry)
        │
        ├── binary_sensor / sensor / weather / image entities
        │   on device "Home Generator" (area: Outside)
        │
        └── sensor.outside_home_generator_generac_959903_status (enum)
                    │  trigger: state → "Running"
                    ▼
        sensor.outside_home_generator_last_ran (template, timestamp)
```

The status sensor's `options` attribute lists every possible value: `Ready`, `Running`, `Exercising`, `Warning`, `Stopped`, `Communication Issue`, `Unknown`, `Online`, `Offline`. The last-ran sensor only reacts to the transition into `Running`, so it holds the timestamp of the most recent actual run rather than re-evaluating on every poll.

## Prerequisites

- Generac MobileLink account with the generator already registered
- Generac integration installed and configured via **Settings → Devices & Services**

## Steps

1. Add the Generac integration in HA, authenticate with the MobileLink account credentials, and let it create the "Home Generator" device.
2. Assign the device to the **Outside** area if the integration doesn't already suggest it.
3. Add `packages/generac.yaml` (below) to the HA host and reload the Template platform (`template.reload`) — no full restart needed.

```yaml
# packages/generac.yaml
template:
  - trigger:
      - trigger: state
        entity_id: sensor.outside_home_generator_generac_959903_status
        to: "Running"
    sensor:
      - name: "Home Generator Last Ran"
        unique_id: outside_home_generator_last_ran
        state: "{{ now().isoformat() }}"
        device_class: timestamp
```

> **Coordinated change:** the trigger's `entity_id` is hard-coded to this generator's status sensor. If the integration is ever removed and re-added, the new config entry may regenerate the `959903` panel ID segment — update this file and re-deploy if the status sensor's entity_id changes.

Trigger-based template sensors created via the `template:` platform are not attached to a device, so the area-based entity_id prefixing described in `standards/naming.md` §4.1 does not apply — HA generates the entity_id from the `name` field alone (`sensor.home_generator_last_ran`). Set the area and override the entity_id manually after creation, same as the §4.4 area-less import fix:

```bash
# via HA entity registry (Settings → Entities, or ha_set_entity)
sensor.home_generator_last_ran → sensor.outside_home_generator_last_ran, area: Outside
```

## Related HA Config

| Friendly Name | entity_id | Type |
|---|---|---|
| Home Generator Status | `sensor.outside_home_generator_generac_959903_status` | Generac integration |
| Home Generator Last Ran | `sensor.outside_home_generator_last_ran` | Template sensor (this guide) |

The Generac device also exposes connectivity, run/protection time, battery voltage, outdoor temperature, weather, and maintenance/warning binary sensors — all under the "Home Generator" device, `Home Generator <Field>` naming. Dealer contact info, address, activation date, model/serial number, wifi SSID, panel ID, signal strength, connection timestamps, and the raw connection-type/connecting-flag sensors are marked hidden (not disabled) — they're static or low-value cloud metadata with no polling cost to keep live, just excluded from the default entity list and dashboards.

## Related Files

| Repo path | Deployed location | Purpose |
|---|---|---|
| `scripts/generac.yaml` | `/config/packages/generac.yaml` on the HA host | Trigger-based "last ran" template sensor |

## Related Documents

- `standards/naming.md` §4.1, §4.4 — entity_id area-prefixing mechanism and the area-less fix pattern used above
