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


@pytest.fixture
def mock_setup_entry():
    """Stub out real component bootstrap for config-flow tests only.

    Not autouse: config-flow tests opt in via
    `pytestmark = pytest.mark.usefixtures("mock_setup_entry")` (see
    tests/test_config_flow.py) so every other test file still exercises the
    real async_setup_entry (BigQuery client, coordinator refresh — covered
    by test_coordinator.py and test_sensor.py). Without this fixture, HA
    auto-sets-up a newly created config entry with the real (unmocked)
    async_setup_entry, which fails against the flow tests' fake credentials
    and crashes fixture teardown."""
    with patch("custom_components.geodrops.async_setup_entry", return_value=True):
        yield
