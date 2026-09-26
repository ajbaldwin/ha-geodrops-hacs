import json
import re
from pathlib import Path

from custom_components.geodrops.sensor import SENSOR_SPECS

ROOT = Path(__file__).parent.parent / "custom_components" / "geodrops"
# hassfest's translation_key_validator: translation keys, state keys and
# icons.json state keys must all look like this
KEY = re.compile(r"^[a-z0-9_-]+$")


def _load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _sensor_strings():
    return _load("strings.json")["entity"]["sensor"]


def _enum_specs():
    return [s for s in SENSOR_SPECS if s.options]


def test_en_json_matches_strings_json():
    # custom integrations ship translations/en.json as-is (no build step)
    assert _load("translations/en.json") == _load("strings.json")


def test_every_sensor_has_a_translated_name_with_its_placeholders():
    strings = _sensor_strings()
    for spec in SENSOR_SPECS:
        name = strings[spec.translation_key]["name"]
        assert set(re.findall(r"{(\w+)}", name)) == set(spec.placeholders or {}), spec.suffix


def test_no_unused_sensor_translations():
    assert set(_sensor_strings()) == {s.translation_key for s in SENSOR_SPECS}


def test_every_enum_state_has_a_label_and_an_icon():
    strings, icons = _sensor_strings(), _load("icons.json")["entity"]["sensor"]
    for spec in _enum_specs():
        assert set(strings[spec.translation_key]["state"]) == set(spec.options), spec.suffix
        assert set(icons[spec.translation_key]["state"]) == set(spec.options), spec.suffix


def test_icons_only_reference_real_sensors():
    icons = _load("icons.json")["entity"]["sensor"]
    assert set(icons) <= {s.translation_key for s in SENSOR_SPECS}


def test_keys_pass_hassfest_validation():
    keys = []
    for key, entry in _sensor_strings().items():
        keys += [key, *entry.get("state", {})]
    for key, entry in _load("icons.json")["entity"]["sensor"].items():
        keys += [key, *entry.get("state", {})]
    for spec in _enum_specs():
        keys += spec.options
    assert [k for k in keys if not KEY.match(k)] == []
