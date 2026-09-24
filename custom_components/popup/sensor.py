"""Status sensor: the loaded version, with the number of subscribed browsers."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the status sensor."""
    async_add_entities([PopupStatusSensor(hass, entry)])


class PopupStatusSensor(SensorEntity):
    """The running Popup version; ``browsers`` counts live subscriptions."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:dock-window"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Popup",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _data(self) -> dict:
        return self._hass.data[DOMAIN]

    @property
    def native_value(self) -> str:
        return self._data["version"]

    @property
    def extra_state_attributes(self) -> dict:
        return {"browsers": self._data["clients"]}

    async def async_added_to_hass(self) -> None:
        @callback
        def notify() -> None:
            self.async_write_ha_state()

        self._data["notify"] = notify

    async def async_will_remove_from_hass(self) -> None:
        self._data["notify"] = lambda: None
