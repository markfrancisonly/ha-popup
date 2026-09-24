"""Config flow for the Popup integration: one entry, nothing to configure."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class PopupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single Popup entry after a confirmation step."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and create the entry."""
        if user_input is not None:
            return self.async_create_entry(title="Popup", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
