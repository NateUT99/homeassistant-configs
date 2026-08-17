# HA Automation & Script Mirror

This directory contains version-controlled YAML exports of every automation and script in the Home Assistant instance. It is a **living mirror** — updated in the same session as any HA change.

## Relationship to HA

**HA is authoritative.** This directory is downstream. When the two disagree, HA wins. The mirror exists for:

- **Recovery:** paste a YAML file back into HA after a rebuild, adjusting entity IDs for any room or device changes
- **Diffing:** `git diff` shows exactly what changed in an automation across sessions
- **Audit:** the full history of what an automation looked like at any point in time is preserved in git

## Relationship to the snapshot

`../snapshot/2026-07-27-pre-move/` is a **frozen archive** of the old apartment instance, captured before the 2026 house move. It is read-only — never modify it. Use it as a reference when rebuilding prior functionality, but do not copy its YAML directly here: entity IDs and area names are from the old house and must be rebuilt fresh.

## Sync rule

Whenever an automation or script is created, modified, or deleted in HA:

1. Export from HA via `ha_config_get_automation` or `ha_config_get_script` (MCP tools)
2. Write or update the corresponding file here
3. Commit the mirror update in the same commit as any guide or standards changes for that automation

Updating the mirror is part of "done" for any automation/script work — don't leave the two out of sync.

## File naming

```
automations/automation.<object_id>.yaml
scripts/script.<object_id>.yaml
```

The object_id is the entity_id without the domain: `automation.bathroom_night_lamp` → `automation.bathroom_night_lamp.yaml`.

## What's NOT here

- Helpers, scenes, and dashboards — HA-only or covered by guides
- `configuration.yaml` entries — in the relevant guide
- Template sensors — in `configuration.yaml` / packages (not HA-storage artifacts)
- Snapshot files from the old house — in `../snapshot/`
