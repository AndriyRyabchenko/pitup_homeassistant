"""Спільне для сутностей техніки PitUp (сенсор стану, лічильник)."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PitUpCoordinator


def track_vehicles(
    coordinator: PitUpCoordinator, entry: ConfigEntry, add: Callable[[list[int]], None]
) -> None:
    """Сутності для наявної техніки зараз і для нової - щойно вона з'явиться в зведенні
    (додали в PitUp чи вибрали для HA), без перезапуску інтеграції."""
    known: set[int] = set()

    @callback
    def _add_new() -> None:
        new = [v["id"] for v in (coordinator.data or {}).get("vehicles", []) if v["id"] not in known]
        if new:
            known.update(new)
            add(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class PitUpVehicleEntity(CoordinatorEntity[PitUpCoordinator]):
    """Сутність однієї техніки; недоступна, якщо техніки вже немає в зведенні."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PitUpCoordinator, vehicle_id: int) -> None:
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id

    @property
    def vehicle(self) -> dict:
        return self.coordinator.vehicle(self._vehicle_id) or {}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.vehicle(self._vehicle_id) is not None
