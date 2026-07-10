"""Опитування PitUp API та кешування даних для сенсорів."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, SUMMARY_PATH

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
                return await resp.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Помилка зв'язку з PitUp: {err}") from err
