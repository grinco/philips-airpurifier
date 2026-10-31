[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs) [![Tests](https://github.com/grinco/philips-airpurifier/actions/workflows/tests.yml/badge.svg)](https://github.com/grinco/philips-airpurifier/actions/workflows/tests.yml) [![Validate](https://github.com/grinco/philips-airpurifier/actions/workflows/validate.yml/badge.svg)](https://github.com/grinco/philips-airpurifier/actions/workflows/validate.yml)

## Supported devices

Philips purifiers that use the **encrypted HTTP protocol** (`/di/v1/...` on port 80),
e.g. AC2729, AC2889, AC3829. Newer CoAP-only models are not supported.

## Breaking changes in 3.0

- Set up from the UI; YAML configuration is deprecated (imported automatically, see below)
- Requires Home Assistant 2025.1 or newer
- The integration folder is now `custom_components/philips_airpurifier` (must match the domain)
- Custom services now take a `target` like any other entity service
- `pycryptodome` is no longer required (uses the `cryptography` package shipped with Home Assistant)
- Preset `Bacteria` is back for devices that report it

---
## Setup

**Settings → Devices & services → Add integration → Philips AirPurifier**, then enter the
IP address of the purifier. Give the purifier a fixed DHCP lease. You can change the
address later with **Reconfigure** and the polling interval (default 30 s) under **Configure**.

### Migrating from YAML

If you still have

```yaml
fan:
  platform: philips_airpurifier
  host: 192.168.0.17
```

in `configuration.yaml`, it is imported into a UI config entry on the next restart and a
repair notice asks you to remove the YAML block. The device must be reachable during
that restart.

### Automatic recovery

These purifiers sometimes stop answering. The integration recovers on its own:

1. Every failed poll drops the encryption session and reconnects with a new key exchange.
2. After 3 failed polls in a row, the integration reloads itself.
3. While the purifier stays offline, the entity shows *unavailable* and Home Assistant
   keeps retrying the setup with a growing delay. The entity comes back when the device answers.

---
## Sensors

Created for each value the device reports (models without a humidifier get no humidity/water/wick sensors):

| Sensor | Unit | Notes |
| ------ | ---- | ----- |
| PM2.5 | µg/m³ | |
| Allergen index | – | 1–12 |
| Temperature | °C | humidifier models |
| Humidity | % | humidifier models |
| Water level | % | humidifier models |
| Pre-filter cleaning, HEPA filter, Active carbon filter, Wick filter | h | diagnostic: hours until clean/replace |

The same values are also kept as attributes of the fan entity, so existing templates keep working.

## Fan preset modes:

- Auto
- Allergen
- Sleep
- Bacteria (if supported)
- Speed 1
- Speed 2
- Speed 3
- Turbo

## Services

The `philips_airpurifier` integration provides the following custom services:

### `philips_airpurifier.set_function`

Set the device function (if supported)

| Field     | Value                             | Necessity  | Description                                               |
| --------- | --------------------------------- | ---------- | --------------------------------------------------------- |
| entity_id | `"fan.living_room"`               | _Required_ | Name(s) of the entities to set function                   |
| function  | `"Purification & Humidification"` | _Required_ | One of "Purification" or "Purification & Humidification". |

### `philips_airpurifier.set_target_humidity`

Set the device target humidity (if supported)

| Field     | Value               | Necessity  | Description                                    |
| --------- | ------------------- | ---------- | ---------------------------------------------- |
| entity_id | `"fan.living_room"` | _Required_ | Name(s) of the entities to set target humidity |
| humidity  | `40`                | _Required_ | One of 40, 50, 60                              |

### `philips_airpurifier.set_light_brightness`

Set the device light brightness

| Field     | Value               | Necessity  | Description                                                           |
| --------- | ------------------- | ---------- | --------------------------------------------------------------------- |
| entity_id | `"fan.living_room"` | _Required_ | Name(s) of the entities to set light brightness                       |
| level     | `50`                | _Required_ | One of 0, 25, 50, 75, 100. Turns off the display light if level is 0. |

### `philips_airpurifier.set_child_lock`

Set the device child lock on or off

| Field     | Value               | Necessity  | Description                               |
| --------- | ------------------- | ---------- | ----------------------------------------- |
| entity_id | `"fan.living_room"` | _Required_ | Name(s) of the entities to set child lock |
| lock      | `true`              | _Required_ | true or false                             |

### `philips_airpurifier.set_timer`

Set the device off time

| Field     | Value               | Necessity  | Description                              |
| --------- | ------------------- | ---------- | ---------------------------------------- |
| entity_id | `"fan.living_room"` | _Required_ | Name(s) of the entities to set off timer |
| hours     | `5`                 | _Required_ | Hours between 0 and 12                   |

### `philips_airpurifier.set_display_light`

Set the device display light on or off

| Field     | Value               | Necessity  | Description                                  |
| --------- | ------------------- | ---------- | -------------------------------------------- |
| entity_id | `"fan.living_room"` | _Required_ | Name(s) of the entities to set display light |
| light     | `true`              | _Required_ | true or false                                |

---
## Development

Tests run against a fake purifier that speaks the encrypted HTTP protocol (`tests/fake_device.py`), so no hardware is needed:

```bash
pip install pytest-homeassistant-custom-component
python -m pytest
```

GitHub Actions runs the tests against the oldest supported and the latest Home Assistant release, plus `hassfest` and HACS validation, on every push and weekly.

---
## License

MIT, see [LICENSE](LICENSE). The upstream project was licensed under MIT in
[marlub/philips-airpurifier@dafee1e](https://github.com/marlub/philips-airpurifier/commit/dafee1ea1a4ff3c8575358973d26bdc8571cae54)
(closing [#2](https://github.com/marlub/philips-airpurifier/issues/2)).
