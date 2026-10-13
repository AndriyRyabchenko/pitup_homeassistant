"""UI-налаштування інтеграції PitUp (лише API-токен - адреса фіксована)."""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BASE_URL,
    CONF_NOTIFY_SERVICE,
    CONF_TOKEN,
    DEFAULT_BASE_URL,
    DOMAIN,
    SUMMARY_PATH,
)


class PitUpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Майстер додавання інтеграції PitUp - потрібен лише токен із кабінету."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PitUpOptionsFlow(config_entry)

    async def _check_token(self, token: str) -> str | None:
        """None - токен робочий, інакше ключ помилки (strings.json → error)."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{DEFAULT_BASE_URL}{SUMMARY_PATH}",
                headers={"X-Api-Token": token},  # не в URL - URL потрапляють у логи
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    return "invalid_auth"
                if resp.status == 403:
                    return "plan_limit"  # інтеграції не входять у тариф
                if resp.status != 200:
                    return "cannot_connect"
        except (aiohttp.ClientError, TimeoutError):
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if error := await self._check_token(token):
                errors["base"] = error
            else:
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

    async def async_step_reauth(self, entry_data):
        """Токен перегенерували в PitUp - просимо новий (сутності й налаштування лишаються)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if error := await self._check_token(token):
                errors["base"] = error
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )


class PitUpOptionsFlow(config_entries.OptionsFlow):
    """Опції: notify-сервіс для нативних пушів (ТО/страховки)."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            svc = (user_input.get(CONF_NOTIFY_SERVICE) or "").strip()
            return self.async_create_entry(title="", data={CONF_NOTIFY_SERVICE: svc})
        cur = self._entry.options.get(CONF_NOTIFY_SERVICE, "")
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_NOTIFY_SERVICE, default=cur): str}
            ),
        )
