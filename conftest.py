import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytest_plugins = "pytest_homeassistant_custom_component"

from tests.common import FakeGeoDropsClient  # noqa: E402  (needs the sys.path entry above)


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
    real async_setup_entry. Without it, HA sets up each entry a flow creates
    or reloads, which would make flow tests depend on setup. The stub still
    sets runtime_data, which the real async_unload_entry's platforms expect
    at hass teardown (after this patch ends)."""
    async def _setup(hass, entry):
        entry.runtime_data = MagicMock()
        return True

    with patch("custom_components.geodrops.async_setup_entry", side_effect=_setup):
        yield


@pytest.fixture
def entity_registry_enabled_by_default():
    """Create disabled-by-default sensors enabled (HA core's fixture of the same name)."""
    with patch("homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
               new_callable=PropertyMock, return_value=True):
        yield


@pytest.fixture(autouse=True)
def fake_geodrops_client():
    """Never talk to Google: every GeoDropsClient the integration makes is a fake."""
    FakeGeoDropsClient.created = []
    with (
        patch("custom_components.geodrops.GeoDropsClient", FakeGeoDropsClient),
        patch("custom_components.geodrops.config_flow.GeoDropsClient", FakeGeoDropsClient),
    ):
        yield FakeGeoDropsClient
