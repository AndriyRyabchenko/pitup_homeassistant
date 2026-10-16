"""Налаштування, сутності, повторна авторизація, сервіс set_counter і config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pitup.const import DOMAIN

SUMMARY = "https://pitup.app/api/ha/summary/"
ODOMETER = "https://pitup.app/api/ha/odometer/"


def _summary(*vehicles):
    return {"status": "ok", "totals": {"vehicles": len(vehicles)}, "vehicles": list(vehicles)}


def _vehicle(vid, title):
    return {"id": vid, "title": title, "status": "ok", "unit": "km", "mileage": 1000, "items": []}


def _entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="pitup_tok",
                            data={"base_url": "https://pitup.app", "token": "tok"})
    entry.add_to_hass(hass)
    return entry


async def _setup(hass, aioclient_mock, *vehicles):
    aioclient_mock.get(SUMMARY, json=_summary(*vehicles))
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ids(hass, entry, domain):
    return sorted(e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
                  if e.domain == domain)


async def test_new_vehicle_appears_without_reload(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    assert _ids(hass, entry, "number") == [f"{entry.entry_id}_counter_1"]

    aioclient_mock.clear_requests()
    aioclient_mock.get(SUMMARY, json=_summary(_vehicle(1, "Audi"), _vehicle(2, "Honda")))
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()
    assert _ids(hass, entry, "number") == [f"{entry.entry_id}_counter_1", f"{entry.entry_id}_counter_2"]
    assert f"{entry.entry_id}_vehicle_2" in _ids(hass, entry, "sensor")


async def test_removed_vehicle_becomes_unavailable(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    aioclient_mock.clear_requests()
    aioclient_mock.get(SUMMARY, json=_summary())
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_counter_1")
    assert hass.states.get(entity_id).state == "unavailable"


async def test_invalid_token_starts_reauth(hass, aioclient_mock):
    aioclient_mock.get(SUMMARY, status=401)
    entry = _entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)


async def test_reauth_updates_token(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": " new-tok "})
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-tok"


async def test_set_counter_unknown_vehicle_raises(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    with pytest.raises(HomeAssistantError, match="id=99"):
        await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 99, "value": 5}, blocking=True)
    assert not [c for c in aioclient_mock.mock_calls if c[0] == "POST"]


async def test_set_counter_shows_server_reason(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    aioclient_mock.post(ODOMETER, status=403, json={"detail": "vehicle is read-only for this token"})
    with pytest.raises(HomeAssistantError, match="read-only"):
        await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 5}, blocking=True)


async def test_set_counter_posts_value(hass, aioclient_mock):
    await _setup(hass, aioclient_mock, _vehicle(1, "Audi"))
    aioclient_mock.post(ODOMETER, json={"ok": True})
    await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 1234.567}, blocking=True)
    post = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][0]
    assert post[2] == {"vehicle_id": 1, "value": 1234.57}


@pytest.mark.parametrize(("status", "exc", "error"), [
    (401, None, "invalid_auth"), (403, None, "plan_limit"), (500, None, "cannot_connect"),
    (None, TimeoutError, "cannot_connect"),
])
async def test_config_flow_errors(hass, aioclient_mock, status, exc, error):
    if exc:
        aioclient_mock.get(SUMMARY, exc=exc)
    else:
        aioclient_mock.get(SUMMARY, status=status)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "tok"})
    assert result["errors"] == {"base": error}


async def test_config_flow_creates_entry(hass, aioclient_mock):
    aioclient_mock.get(SUMMARY, json=_summary())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.pitup.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": " tok "})
    assert result["type"] == "create_entry" and result["data"]["token"] == "tok"


def _notifications(hass):
    from homeassistant.components import persistent_notification

    return persistent_notification._async_get_or_create_notifications(hass)


async def test_set_counter_not_applied_warns_once(hass, aioclient_mock, caplog):
    """Менше значення PitUp ігнорує (лічильник лише зростає): журнал щоразу, сповіщення одне, без винятку."""
    await _setup(hass, aioclient_mock, _vehicle(1, "Генератор"))
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": False, "vehicle_id": 1, "value": 44.27})
    for _ in range(2):
        await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 0.14}, blocking=True)
    await hass.async_block_till_done()
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "не застосовано" in r.getMessage()]
    assert len(warnings) == 2 and "44.27" in warnings[0].getMessage()
    notes = _notifications(hass)
    assert list(notes) == ["pitup_counter_not_applied_1"]
    assert "44.27" in notes["pitup_counter_not_applied_1"]["message"]


async def test_set_counter_applied_again_dismisses_notification(hass, aioclient_mock):
    """Базу виправили - значення знову записується: сповіщення прибирається."""
    await _setup(hass, aioclient_mock, _vehicle(1, "Генератор"))
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": False, "value": 44.27})
    await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 0.14}, blocking=True)
    aioclient_mock.clear_requests()
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 44.5})
    await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 44.5}, blocking=True)
    await hass.async_block_till_done()
    assert not _notifications(hass)


async def test_set_counter_updates_value_without_full_refresh(hass, aioclient_mock):
    """Після запису - нове значення в сутності лічильника, без повторного GET усієї техніки."""
    entry = await _setup(hass, aioclient_mock, _vehicle(1, "Генератор"))
    gets = len([c for c in aioclient_mock.mock_calls if c[0] == "GET"])
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "vehicle_id": 1, "value": 44.5})
    await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 44.5}, blocking=True)
    await hass.async_block_till_done()
    assert len([c for c in aioclient_mock.mock_calls if c[0] == "GET"]) == gets
    counter = next(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
                   if e.domain == "number")
    assert float(hass.states.get(counter).state) == 44.5


async def test_not_applied_notification_escapes_markdown(hass, aioclient_mock):
    """Назву спільної техніки вводить інший користувач: у сповіщенні (markdown) - без посилань."""
    await _setup(hass, aioclient_mock, _vehicle(1, "[клік](https://evil.example)"))
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": False, "value": 10})
    await hass.services.async_call(DOMAIN, "set_counter", {"vehicle_id": 1, "value": 1}, blocking=True)
    msg = _notifications(hass)["pitup_counter_not_applied_1"]["message"]
    assert "](https://" not in msg and "\\[клік\\]" in msg
