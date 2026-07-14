"""Опитування PitUp API та кешування даних для сенсорів."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, ODOMETER_PATH, SUMMARY_PATH

_LOGGER = logging.getLogger(__name__)


class PitUpCoordinator(DataUpdateCoordinator):
    """Тягне зведення стану техніки з PitUp раз на інтервал."""

    def __init__(self, hass: HomeAssistant, base_url: str, token: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="PitUp",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.notify_service = ""  # notify-сервіс для пушів (з опцій)
        self._notified = None  # baseline попереджень (щоб слати лише нові)
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        url = f"{self.base_url}{SUMMARY_PATH}"
        try:
            async with self._session.get(
                url,
                params={"token": self.token},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 401:
                    raise UpdateFailed("Недійсний токен PitUp")
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Помилка зв'язку з PitUp: {err}") from err
        await self._maybe_notify(data)
        return data

    async def _maybe_notify(self, data: dict) -> None:
        """Нативний пуш у HA про НОВІ «скоро/прострочено» (ТО + страховки)."""
        msgs = {}
        for v in (data or {}).get("vehicles", []):
            title = v.get("title", "")
            for it in v.get("items", []):
                st = it.get("status")
                if st in ("overdue", "soon"):
                    msgs[f"i|{v.get('id')}|{it.get('name')}|{st}"] = (
                        f"{title}: {it.get('name')} — "
                        + ("прострочено" if st == "overdue" else "скоро")
                    )
            for p in v.get("policies", []):
                st = p.get("status")
                if st in ("overdue", "soon"):
                    msgs[f"p|{v.get('id')}|{p.get('kind')}|{st}"] = (
                        f"{title}: {p.get('kind')} — "
                        + ("прострочено" if st == "overdue"
                           else f"спливає ({p.get('days_left')} дн)")
                    )
        cur = set(msgs)
        if self._notified is None:  # перший запуск — лише базовий стан, без пушу
            self._notified = cur
            return
        new = cur - self._notified
        self._notified = cur
        if not new or not self.notify_service:
            return
        service = self.notify_service.split(".")[-1]
        lines = [msgs[k] for k in new][:10]
        try:
            await self.hass.services.async_call(
                "notify", service,
                {"title": "PitUp — нагадування", "message": "\n".join(lines)},
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("PitUp: пуш не надіслано (notify.%s): %s", service, err)

    async def async_set_counter(self, vehicle_id: int, value: int) -> None:
        """Записує лічильник (пробіг/мотогодини) техніки в PitUp і оновлює дані."""
        url = f"{self.base_url}{ODOMETER_PATH}"
        async with self._session.post(
            url,
            headers={"X-Api-Token": self.token},
            json={"vehicle_id": int(vehicle_id), "value": float(value)},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            resp.raise_for_status()
        await self.async_request_refresh()
