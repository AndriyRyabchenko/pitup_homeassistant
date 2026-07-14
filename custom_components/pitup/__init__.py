"""Інтеграція PitUp для Home Assistant."""
from __future__ import annotations

import logging
import os

import voluptuous as vol
from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_BASE_URL, CONF_TOKEN, DOMAIN, SERVICE_SET_COUNTER
from .coordinator import PitUpCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.NUMBER]

SET_COUNTER_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): vol.Coerce(int),
        vol.Required("value"): vol.Coerce(float),
    }
)

FRONTEND_PATH = "/pitup_static"
CARD_URL = f"{FRONTEND_PATH}/pitup.js"
PANEL_PATH = "pitup"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Реєструє картку `custom:pitup-card` як ресурс + бічну панель «PitUp»."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_frontend"):
        return

    www_dir = os.path.join(os.path.dirname(__file__), "www")
    try:  # нове API (HA 2024.7+) з фолбеком на старе
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_PATH, www_dir, False)]
        )
    except (ImportError, AttributeError):
        hass.http.register_static_path(FRONTEND_PATH, www_dir, False)

    # Авто-підключення JS: картка з’являється у списку «Додати картку».
    frontend.add_extra_js_url(hass, CARD_URL)

    # Панель «PitUp» у бічному меню (готовий інформер без налаштування).
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_PATH,
            webcomponent_name="pitup-panel",
            module_url=CARD_URL,
            sidebar_title="PitUp",
            sidebar_icon="mdi:car-wrench",
            require_admin=False,
            config={},
            embed_iframe=False,
        )
    except Exception as err:  # уже зареєстрована або несумісна версія
        _LOGGER.debug("PitUp panel not registered: %s", err)

    data["_frontend"] = True


def _register_services(hass: HomeAssistant) -> None:
    """Реєструє сервіс pitup.set_counter (один раз на весь домен)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_COUNTER):
        return

    async def _handle_set_counter(call: ServiceCall) -> None:
        vehicle_id = int(call.data["vehicle_id"])
        value = round(float(call.data["value"]), 2)
        for key, coord in hass.data.get(DOMAIN, {}).items():
            if key == "_frontend" or not isinstance(coord, PitUpCoordinator):
                continue
            if any(v.get("id") == vehicle_id for v in (coord.data or {}).get("vehicles", [])):
                await coord.async_set_counter(vehicle_id, value)
                return
        _LOGGER.warning("PitUp: техніку id=%s не знайдено для set_counter", vehicle_id)

    hass.services.async_register(
        DOMAIN, SERVICE_SET_COUNTER, _handle_set_counter, schema=SET_COUNTER_SCHEMA
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PitUpCoordinator(
        hass, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN]
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await _async_register_frontend(hass)
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
