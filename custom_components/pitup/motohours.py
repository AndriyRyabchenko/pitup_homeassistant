"""Вбудований підрахунок мотогодин: сутність «працює» (on/off) → час роботи → лічильник у PitUp.

Без YAML і без бази вручну: коли техніка вмикається, база - поточний лічильник у PitUp;
поки працює - значення йде в PitUp раз на 15 хв, при зупинці - одразу фінальне. Сесія
(початок і база) зберігається на диску: перезапуск HA посеред роботи не губить час.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PUSH_INTERVAL = timedelta(minutes=15)
# Одиниці PitUp, які рахуються часом роботи (код одиниці з /api/ha/summary/).
TIME_UNITS = ("moto_hours", "hours")


class MotohoursTracker:
    """Рахує час роботи техніки за сутністю on/off і пише лічильник у PitUp."""

    def __init__(self, hass: HomeAssistant, coordinator, entry_id: str, trackers: dict[str, str]) -> None:
        self.hass = hass
        self.coordinator = coordinator
        # {vehicle_id: entity_id}; ключі - рядки (так їх зберігають опції HA)
        self.trackers = {int(vid): ent for vid, ent in trackers.items() if ent}
        self._store = Store(hass, 1, f"{DOMAIN}.motohours.{entry_id}")
        self._sessions: dict[int, dict] = {}  # {vehicle_id: {"start": iso, "base": float}}
        self._unsubs: list = []

    async def async_start(self) -> None:
        if not self.trackers:
            return
        self._sessions = {int(k): v for k, v in ((await self._store.async_load()) or {}).items()}
        now = dt_util.utcnow()
        for vid, entity_id in self.trackers.items():
            running = self._is_on(self.hass.states.get(entity_id))
            if running and vid not in self._sessions:
                self._begin(vid, now)
            elif not running and vid in self._sessions:
                # Зупинилась, поки HA не працював: останнє записане значення вже в PitUp.
                self._sessions.pop(vid, None)
        await self._save()
        self._unsubs.append(async_track_state_change_event(
            self.hass, list(self.trackers.values()), self._on_state_change))
        self._unsubs.append(async_track_time_interval(self.hass, self._on_interval, PUSH_INTERVAL))

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @staticmethod
    def _is_on(state) -> bool:
        return state is not None and state.state == STATE_ON

    def _begin(self, vehicle_id: int, now: datetime) -> None:
        """Сесія роботи: база - фактичний лічильник у PitUp (не оцінка за середнім)."""
        v = self.coordinator.vehicle(vehicle_id) or {}
        base = v.get("counter", v.get("mileage"))
        if base is None:
            _LOGGER.warning("PitUp: техніка id %s недоступна - мотогодини не рахуються", vehicle_id)
            return
        self._sessions[vehicle_id] = {"start": now.isoformat(), "base": float(base)}

    def value(self, vehicle_id: int, now: datetime) -> float | None:
        s = self._sessions.get(vehicle_id)
        if not s:
            return None
        hours = (now - datetime.fromisoformat(s["start"])).total_seconds() / 3600
        return round(s["base"] + max(hours, 0), 2)

    async def _push(self, vehicle_id: int, now: datetime) -> None:
        value = self.value(vehicle_id, now)
        if value is None:
            return
        try:
            body = await self.coordinator.async_set_counter(vehicle_id, value, quiet=True)
        except HomeAssistantError as err:
            _LOGGER.warning("PitUp: мотогодини (id %s) не записано: %s", vehicle_id, err)
            return
        s = self._sessions.get(vehicle_id)
        if s is None:
            return
        s["last"] = now.isoformat()
        current = body.get("value")
        if body.get("applied") is False and current is not None:
            # У PitUp більше (змінили вручну) - рахуємо далі від нього, без бази вручну.
            s["start"], s["base"] = now.isoformat(), float(current)

    @callback
    def _on_state_change(self, event: Event) -> None:
        self.hass.async_create_task(self._handle_change(event))

    async def _handle_change(self, event: Event) -> None:
        entity_id = event.data["entity_id"]
        new, old = event.data.get("new_state"), event.data.get("old_state")
        # unavailable/unknown - не зупинка (зв'язок з інвертором тощо), чекаємо справжнього стану.
        if new is None or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        now = dt_util.utcnow()
        for vid, ent in self.trackers.items():
            if ent != entity_id:
                continue
            if self._is_on(new) and vid not in self._sessions:
                self._begin(vid, now)
            elif not self._is_on(new) and vid in self._sessions:
                await self._push(vid, now)
                self._sessions.pop(vid, None)
        await self._save()

    async def _on_interval(self, now: datetime) -> None:
        for vid in list(self._sessions):
            await self._push(vid, dt_util.utcnow())
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({str(k): v for k, v in self._sessions.items()})
