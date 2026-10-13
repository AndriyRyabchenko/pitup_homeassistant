"""Спільне для тестів: кастомні інтеграції увімкнено, фронтенд (панель, Lovelace) - заглушка."""
from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_frontend(hass):
    # Залежності з manifest (frontend, panel_custom...) вважаємо вже піднятими: інтерфейс HA
    # (hass_frontend) у тестах не потрібен, панель і Lovelace-ресурс - заглушка.
    hass.config.components.update({"frontend", "panel_custom", "http", "lovelace"})
    with patch("custom_components.pitup._async_register_frontend"):
        yield
