"""Number-сутність лічильника (пробіг / мотогодини) кожної техніки PitUp."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PitUpCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PitUpCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        PitUpCounterNumber(coordinator, entry, v["id"])
        for v in (coordinator.data or {}).get("vehicles", [])
    ]
    async_add_entities(entities)


class PitUpCounterNumber(CoordinatorEntity[PitUpCoordinator], NumberEntity):
    """Лічильник техніки: пробіг (км) або напрацювання (мотогодини)."""

    _attr_has_entity_name = True
    _attr_name = "Лічильник"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:counter"
    _attr_native_min_value = 0
    _attr_native_max_value = 100000000
    _attr_native_step = 0.01

    def __init__(
        self, coordinator: PitUpCoordinator, entry: ConfigEntry, vehicle_id: int
    ) -> None:
        super().__init__(coordinator)
        self._vehicle_id = vehicle_id
        self._attr_unique_id = f"{entry.entry_id}_counter_{vehicle_id}"
        self._attr_native_unit_of_measurement = self._vehicle().get("unit")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{vehicle_id}")},
        )

    def _vehicle(self) -> dict:
        for v in (self.coordinator.data or {}).get("vehicles", []):
            if v.get("id") == self._vehicle_id:
                return v
        return {}

    @property
    def native_value(self):
        return self._vehicle().get("mileage")

    @property
    def extra_state_attributes(self):
        return {"vehicle_id": self._vehicle_id}

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_counter(self._vehicle_id, round(float(value), 2))
