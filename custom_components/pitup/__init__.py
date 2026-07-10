"""Інтеграція PitUp для Home Assistant."""
from __future__ import annotations

import logging
import os

from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BASE_URL, CONF_TOKEN, DOMAIN
from .coordinator import PitUpCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PitUpCoordinator(
        hass, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN]
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await _async_register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
