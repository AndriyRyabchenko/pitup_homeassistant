"""Сенсори PitUp: загальний стан + по одному на кожну техніку."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PitUpCoordinator
from .entity import PitUpVehicleEntity, track_vehicles

STATUS_ICON = {
    "overdue": "mdi:alert-circle",
    "soon": "mdi:clock-alert",
    "ok": "mdi:check-circle",
    "none": "mdi:help-circle",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PitUpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PitUpOverallSensor(coordinator, entry)])
    track_vehicles(coordinator, entry, lambda ids: async_add_entities(
        PitUpVehicleSensor(coordinator, entry, vid) for vid in ids))


class PitUpOverallSensor(CoordinatorEntity[PitUpCoordinator], SensorEntity):
    """Загальний стан парку: ok / soon / overdue + зведення в атрибутах."""

    _attr_has_entity_name = False
    _attr_name = "PitUp"

    def __init__(self, coordinator: PitUpCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_overall"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PitUp",
            manufacturer="PitUp",
            configuration_url="https://pitup.app",
        )

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("status")

    @property
    def icon(self):
        return STATUS_ICON.get(self.native_value, "mdi:car-wrench")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        totals = data.get("totals", {})
        return {
            "totals": totals,
            "vehicles_count": totals.get("vehicles"),
            "overdue": totals.get("overdue"),
            "soon": totals.get("soon"),
            "policy_overdue": totals.get("policy_overdue"),
            "policy_soon": totals.get("policy_soon"),
            "generated_at": data.get("generated_at"),
            "vehicles": data.get("vehicles", []),
        }


class PitUpVehicleSensor(PitUpVehicleEntity, SensorEntity):
    """Стан однієї техніки: ok / soon / overdue + деталі в атрибутах."""

    _attr_name = None  # ім'я = назва пристрою (техніки)

    def __init__(
        self, coordinator: PitUpCoordinator, entry: ConfigEntry, vehicle_id: int
    ) -> None:
        super().__init__(coordinator, vehicle_id)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_{vehicle_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{vehicle_id}")},
            name=self.vehicle.get("title", f"Техніка {vehicle_id}"),
            manufacturer="PitUp",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def native_value(self):
        return self.vehicle.get("status")

    @property
    def icon(self):
        return STATUS_ICON.get(self.native_value, "mdi:car")

    @property
    def extra_state_attributes(self):
        v = self.vehicle
        nxt = v.get("next") or {}
        return {
            "title": v.get("title"),
            "kind": v.get("kind"),
            "mileage": v.get("mileage"),
            "mileage_estimated": v.get("mileage_estimated"),
            "unit": v.get("unit"),
            "overdue": v.get("overdue"),
            "soon": v.get("soon"),
            "ok": v.get("ok"),
            "next_name": nxt.get("name"),
            "next_status": nxt.get("status"),
            "next_due_km": nxt.get("due_km"),
            "next_over_km": nxt.get("over_km"),
            "next_date": nxt.get("next_date"),
            "items": v.get("items", []),
        }
