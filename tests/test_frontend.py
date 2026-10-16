"""Картка на дашборді: Lovelace-ресурс оновлюється на поточну версію (інакше браузер тягне стару)."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState

import custom_components.pitup as pitup

# conftest глушить реєстрацію фронтенду для всіх тестів - тут потрібна справжня.
_REGISTER_FRONTEND = pitup._async_register_frontend


class _Resources:
    def __init__(self, items):
        self.items = items
        self.updated = []

    async def async_get_info(self):
        return {}

    def async_items(self):
        return self.items

    async def async_create_item(self, data):
        self.items.append(data)

    async def async_update_item(self, item_id, data):
        self.updated.append((item_id, data["url"]))


async def test_old_resource_url_is_updated(hass):
    """Ресурс без ?v= (додали колись вручну чи стара версія) - на адресу з поточною версією."""
    res = _Resources([{"id": "r1", "url": "/pitup_static/pitup.js", "type": "module"}])
    hass.data["lovelace"] = MagicMock(resources=res)
    await pitup._register_lovelace_resource(hass, "/pitup_static/pitup.js?v=0.12.1")
    assert res.updated == [("r1", "/pitup_static/pitup.js?v=0.12.1")]


async def test_resource_registered_after_start(hass):
    """HA ще стартує: оновлення ресурсу - після EVENT_HOMEASSISTANT_STARTED, у циклі подій."""
    hass.set_state(CoreState.starting)
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch.object(pitup, "_register_lovelace_resource", AsyncMock()) as reg, \
            patch.object(pitup.frontend, "add_extra_js_url"), \
            patch.object(pitup.panel_custom, "async_register_panel", AsyncMock()):
        await _REGISTER_FRONTEND(hass)
        reg.assert_not_called()
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()
        reg.assert_awaited_once()

