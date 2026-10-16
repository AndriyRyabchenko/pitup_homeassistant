"""Опитування PitUp API та кешування даних для сенсорів."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
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
        self._by_id: dict[int, dict] = {}
        self._not_applied: set[int] = set()  # техніка, про яку вже показано сповіщення

    def vehicle(self, vehicle_id: int) -> dict | None:
        """Техніка з останнього зведення (None - її вже немає або доступ знято)."""
        return self._by_id.get(vehicle_id)

    async def _async_update_data(self) -> dict:
        url = f"{self.base_url}{SUMMARY_PATH}"
        try:
            async with self._session.get(
                url,
                headers={"X-Api-Token": self.token},  # не в URL - URL потрапляють у логи
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 401:
                    # HA покаже «Потрібна повторна автентифікація» (крок reauth у config_flow)
                    raise ConfigEntryAuthFailed("Недійсний токен PitUp")
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Помилка зв'язку з PitUp: {err}") from err
        self._by_id = {v.get("id"): v for v in data.get("vehicles", [])}
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
                        f"{title}: {it.get('name')} - "
                        + ("прострочено" if st == "overdue" else "скоро")
                    )
            for p in v.get("policies", []):
                st = p.get("status")
                if st in ("overdue", "soon"):
                    msgs[f"p|{v.get('id')}|{p.get('kind')}|{st}"] = (
                        f"{title}: {p.get('kind')} - "
                        + ("прострочено" if st == "overdue"
                           else f"спливає ({p.get('days_left')} дн)")
                    )
        cur = set(msgs)
        if self._notified is None:  # перший запуск - лише базовий стан, без пушу
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
                {"title": "PitUp - нагадування", "message": "\n".join(lines)},
                blocking=False,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("PitUp: пуш не надіслано (notify.%s): %s", service, err)

    async def async_set_counter(self, vehicle_id: int, value: float) -> None:
        """Записує лічильник (пробіг/мотогодини) техніки в PitUp.

        Лічильник у PitUp лише зростає: менше значення бекенд ігнорує (`applied: false`) -
        тоді попередження в журнал і одне сповіщення в HA (без винятку, інакше автоматизація
        падала б щоразу). Після запису оновлюємо лише цю техніку, без повного опитування.
        """
        url = f"{self.base_url}{ODOMETER_PATH}"
        try:
            async with self._session.post(
                url,
                headers={"X-Api-Token": self.token},
                json={"vehicle_id": int(vehicle_id), "value": float(value)},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                body = await resp.json(content_type=None) or {}
                if resp.status >= 400:
                    # 400 - значення, 403 - тариф / техніка не для HA / лише перегляд, 404 - немає
                    raise HomeAssistantError(f"PitUp: HTTP {resp.status} {body.get('detail', '')}".strip())
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise HomeAssistantError(f"Помилка зв'язку з PitUp: {err}") from err
        vehicle_id = int(vehicle_id)
        current = body.get("value")
        if body.get("applied") is False:
            self._warn_not_applied(vehicle_id, float(value), current)
        elif vehicle_id in self._not_applied:
            self._not_applied.discard(vehicle_id)
            persistent_notification.async_dismiss(self.hass, self._notification_id(vehicle_id))
        self._apply_counter(vehicle_id, current)

    @staticmethod
    def _notification_id(vehicle_id: int) -> str:
        return f"pitup_counter_not_applied_{vehicle_id}"

    def _warn_not_applied(self, vehicle_id: int, sent: float, current) -> None:
        """Значення менше за лічильник у PitUp: журнал щоразу, сповіщення в HA - один раз."""
        v = self._by_id.get(vehicle_id) or {}
        title = v.get("title") or f"#{vehicle_id}"
        _LOGGER.warning(
            "PitUp: значення %s для техніки %s (id %s) не застосовано - у PitUp уже %s "
            "(лічильник лише зростає). Перевір базу (offset) у сценарії set_counter.",
            sent, title, vehicle_id, current,
        )
        if vehicle_id in self._not_applied:
            return
        self._not_applied.add(vehicle_id)
        persistent_notification.async_create(
            self.hass,
            (
                f"Home Assistant надсилає {sent} для «{title}», а в PitUp уже {current}. "
                "Лічильник у PitUp лише зростає, тож значення не записано.\n\n"
                "Якщо рахуєш мотогодини за прикладом generator-motohours.yaml - виправ базу: "
                f"input_number.generator_hours_offset = {current} - поточне значення "
                "sensor.generator_motohours."
            ),
            title="PitUp: лічильник не оновлено",
            notification_id=self._notification_id(vehicle_id),
        )

    def _apply_counter(self, vehicle_id: int, value) -> None:
        """Нове значення лічильника - у дані цієї техніки й сенсори, без повного опитування.

        Не `async_set_updated_data`: вона переносить наступне планове опитування, і при записах
        кожні 15 хв повне оновлення (статуси ТО, поліси) не відбулося б ніколи.
        """
        v = self._by_id.get(vehicle_id)
        if v is None or value is None:
            return
        v["mileage"] = int(value) if float(value) == int(value) else value
        v["mileage_estimated"] = False
        self.async_update_listeners()
