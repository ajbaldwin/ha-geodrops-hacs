import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let hass.config_entries.flow discover custom_components/geodrops in tests."""
    yield


@pytest.fixture(autouse=True)
def mock_setup_entry():
    """Config-flow tests exercise flow logic only; real component bootstrap
    (BigQuery client, coordinator refresh) is covered by test_coordinator.py
    and test_sensor.py. Without this, HA auto-sets-up newly created config
    entries with the real (unmocked) async_setup_entry, which fails against
    the flow tests' fake credentials and crashes fixture teardown."""
    with patch("custom_components.geodrops.async_setup_entry", return_value=True):
        yield
