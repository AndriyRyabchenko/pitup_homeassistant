"""UI-налаштування інтеграції PitUp (лише API-токен — адреса фіксована)."""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_BASE_URL, CONF_TOKEN, DEFAULT_BASE_URL, DOMAIN, SUMMARY_PATH


class PitUpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Майстер додавання інтеграції PitUp — потрібен лише токен із кабінету."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    f"{DEFAULT_BASE_URL}{SUMMARY_PATH}",
                    params={"token": token},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401:
                        errors["base"] = "invalid_auth"
                    elif resp.status != 200:
                        errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(f"pitup_{token[:10]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="PitUp",
                    data={CONF_BASE_URL: DEFAULT_BASE_URL, CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
