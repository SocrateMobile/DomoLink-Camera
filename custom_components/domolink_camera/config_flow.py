"""Config flow for DomoLink Camera integration."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

try:
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:
    ConfigFlowResult = Any  # type: ignore[misc,assignment]

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)


class DomoLinkCameraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DomoLink Camera."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get options flow."""
        return DomoLinkCameraOptionsFlow(config_entry)


class DomoLinkCameraOptionsFlow(config_entries.OptionsFlow):
    """Handle options for DomoLink Camera."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
