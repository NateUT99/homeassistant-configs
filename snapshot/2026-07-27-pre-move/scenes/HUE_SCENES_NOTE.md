# Hue Bridge Scenes — Not Exportable via HA MCP

These 10 scene entities exist in HA because the Hue integration exposes Hue
bridge scenes as scene entities, but their configuration lives exclusively in
the Hue bridge. ha_config_get_scene cannot retrieve Hue-native scenes
(ENTITY_NOT_FOUND is returned regardless of the identifier used).

To recreate: re-pair the Hue bridge at the new house. Hue scenes are stored
in the bridge itself and are not lost when HA is reinstalled.

## Hue scenes present at snapshot time

| entity_id | friendly_name |
|---|---|
| scene.kitchen_cabinet_accent_emerald_flutter | Kitchen Cabinet Accent Emerald flutter |
| scene.kitchen_cabinet_accent_motown | Kitchen Cabinet Accent Motown |
| scene.kitchen_cabinet_accent_nighttime | Kitchen Cabinet Accent Nighttime |
| scene.kitchen_cabinet_accent_painted_sky | Kitchen Cabinet Accent Painted sky |
| scene.kitchen_cabinet_accent_resplendent | Kitchen Cabinet Accent Resplendent |
| scene.kitchen_cabinet_accent_sunset_allure | Kitchen Cabinet Accent Sunset allure |
| scene.office_background_lights_chinatown | Office Background Lights Chinatown |
| scene.office_background_lights_hal | Office Background Lights Hal |
| scene.office_background_lights_motown | Office Background Lights Motown |
| scene.office_background_lights_sundown | Office Background Lights Sundown |
