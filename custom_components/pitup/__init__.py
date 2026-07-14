"""Інтеграція PitUp для Home Assistant."""
from __future__ import annotations

import logging
import os

import voluptuous as vol
from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall

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
CARD_JS = f"{FRONTEND_PATH}/pitup.js"
# Cache-bust: браузер/HA кешують JS за URL, тож при кожній версії міняємо ?v=…
# (тримати синхронно з manifest.json version).
_JS_VERSION = "0.7.1"
CARD_URL = f"{CARD_JS}?v={_JS_VERSION}"
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
    # + як Lovelace-ресурс, щоб дашборд чекав завантаження (без «Custom element doesn't exist»).
    # Робимо після повного запуску HA — тоді lovelace та його ресурси вже готові.
    if hass.state == CoreState.running:
        await _register_lovelace_resource(hass)
    else:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            lambda _e: hass.async_create_task(_register_lovelace_resource(hass)),
        )

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


async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """Додає картку як Lovelace-ресурс (module), щоб дашборд не рендерив її до завантаження."""
    try:
        data = hass.data.get("lovelace")
        resources = getattr(data, "resources", None)
        if resources is None and isinstance(data, dict):
            resources = data.get("resources")
        if resources is None or getattr(resources, "async_create_item", None) is None:
            _LOGGER.warning("PitUp: Lovelace resources недоступні (yaml-режим?) — картку треба додати вручну як ресурс %s", CARD_URL)
            return
        try:  # переконатись, що сховище завантажене
            if hasattr(resources, "async_get_info"):
                await resources.async_get_info()
            elif hasattr(resources, "async_load") and not getattr(resources, "loaded", False):
                await resources.async_load()
                resources.loaded = True
        except Exception:  # noqa: BLE001
            pass
        items = list(resources.async_items()) if hasattr(resources, "async_items") else []
        existing = next((i for i in items if (i.get("url") or "").split("?")[0] == CARD_JS), None)
        if existing:
            if existing.get("url") != CARD_URL and hasattr(resources, "async_update_item"):
                await resources.async_update_item(existing["id"], {"res_type": "module", "url": CARD_URL})
                _LOGGER.info("PitUp: Lovelace-ресурс оновлено → %s", CARD_URL)
            return
        await resources.async_create_item({"res_type": "module", "url": CARD_URL})
        _LOGGER.info("PitUp: Lovelace-ресурс %s зареєстровано", CARD_URL)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("PitUp: Lovelace-ресурс не додано (%s) — додай вручну: %s", err, CARD_URL)


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
