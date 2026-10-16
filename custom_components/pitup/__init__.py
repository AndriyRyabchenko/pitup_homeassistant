"""Інтеграція PitUp для Home Assistant."""
from __future__ import annotations

import logging
import os

import voluptuous as vol
from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_get_integration

from .const import (
    CONF_BASE_URL,
    CONF_MOTOHOURS,
    CONF_NOTIFY_SERVICE,
    CONF_TOKEN,
    DOMAIN,
    SERVICE_SET_COUNTER,
)
from .coordinator import PitUpCoordinator
from .motohours import MotohoursTracker

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
PANEL_PATH = "pitup"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Реєструє картку `custom:pitup-card` як ресурс + бічну панель «PitUp»."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_frontend"):
        return
    # Cache-bust: браузер/HA кешують JS за URL, тож ?v= - версія з manifest.json.
    card_url = f"{CARD_JS}?v={(await async_get_integration(hass, DOMAIN)).version}"

    www_dir = os.path.join(os.path.dirname(__file__), "www")
    try:  # нове API (HA 2024.7+) з фолбеком на старе
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_PATH, www_dir, False)]
        )
    except (ImportError, AttributeError):
        hass.http.register_static_path(FRONTEND_PATH, www_dir, False)

    # Авто-підключення JS: картка з’являється у списку «Додати картку».
    frontend.add_extra_js_url(hass, card_url)
    # + як Lovelace-ресурс, щоб дашборд чекав завантаження (без «Custom element doesn't exist»).
    # Робимо після повного запуску HA - тоді lovelace та його ресурси вже готові.
    if hass.state == CoreState.running:
        await _register_lovelace_resource(hass, card_url)
    else:
        # Асинхронний обробник - у циклі подій HA. Звичайна lambda з async_create_task виконувалась
        # поза ним: новий HA це блокує, і ресурс зі старою версією (?v=) так і не оновлювався -
        # дашборд тягнув стару картку з кешу браузера.
        async def _on_started(_event) -> None:
            await _register_lovelace_resource(hass, card_url)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)

    # Панель «PitUp» у бічному меню (готовий інформер без налаштування).
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_PATH,
            webcomponent_name="pitup-panel",
            module_url=card_url,
            sidebar_title="PitUp",
            sidebar_icon="mdi:car-wrench",
            require_admin=False,
            config={},
            embed_iframe=False,
        )
    except Exception as err:  # уже зареєстрована або несумісна версія
        _LOGGER.debug("PitUp panel not registered: %s", err)

    data["_frontend"] = True


async def _register_lovelace_resource(hass: HomeAssistant, card_url: str) -> None:
    """Додає картку як Lovelace-ресурс (module), щоб дашборд не рендерив її до завантаження."""
    try:
        data = hass.data.get("lovelace")
        resources = getattr(data, "resources", None)
        if resources is None and isinstance(data, dict):
            resources = data.get("resources")
        if resources is None or getattr(resources, "async_create_item", None) is None:
            _LOGGER.warning("PitUp: Lovelace resources недоступні (yaml-режим?) - картку треба додати вручну як ресурс %s", card_url)
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
            if existing.get("url") != card_url and hasattr(resources, "async_update_item"):
                await resources.async_update_item(existing["id"], {"res_type": "module", "url": card_url})
                _LOGGER.info("PitUp: Lovelace-ресурс оновлено → %s", card_url)
            return
        await resources.async_create_item({"res_type": "module", "url": card_url})
        _LOGGER.info("PitUp: Lovelace-ресурс %s зареєстровано", card_url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("PitUp: Lovelace-ресурс не додано (%s) - додай вручну: %s", err, card_url)


def _register_services(hass: HomeAssistant) -> None:
    """Реєструє сервіс pitup.set_counter (один раз на весь домен)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_COUNTER):
        return

    async def _handle_set_counter(call: ServiceCall) -> None:
        vehicle_id = int(call.data["vehicle_id"])
        value = round(float(call.data["value"]), 2)
        for coord in hass.data.get(DOMAIN, {}).values():
            if isinstance(coord, PitUpCoordinator) and coord.vehicle(vehicle_id):
                await coord.async_set_counter(vehicle_id, value)
                return
        # Помилка, а не тихий «успіх»: автоматизація з хибним vehicle_id одразу видна.
        raise HomeAssistantError(
            f"PitUp: техніки id={vehicle_id} немає серед вибраної для Home Assistant"
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_COUNTER, _handle_set_counter, schema=SET_COUNTER_SCHEMA
    )


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = PitUpCoordinator(
        hass, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN]
    )
    coordinator.notify_service = entry.options.get(CONF_NOTIFY_SERVICE, "")
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await _async_register_frontend(hass)
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Вбудований підрахунок мотогодин (опції: техніка → сутність «працює»).
    tracker = MotohoursTracker(hass, coordinator, entry.entry_id, entry.options.get(CONF_MOTOHOURS, {}))
    await tracker.async_start()
    entry.async_on_unload(tracker.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
