"""Вбудований підрахунок мотогодин: сутність «працює» → час роботи → лічильник у PitUp."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.pitup.const import DOMAIN

SUMMARY = "https://pitup.app/api/ha/summary/"
ODOMETER = "https://pitup.app/api/ha/odometer/"
GEN = "binary_sensor.generator"


def _gen(counter=44.0, unit_code="moto_hours", vid=1, title="GENA"):
    return {"id": vid, "title": title, "status": "ok", "unit": "мотогодин", "unit_code": unit_code,
            "mileage": counter, "counter": counter, "items": []}


async def _setup(hass, aioclient_mock, *vehicles, tracked=None):
    aioclient_mock.get(SUMMARY, json={"status": "ok", "totals": {}, "vehicles": list(vehicles)})
    entry = MockConfigEntry(domain=DOMAIN, unique_id="pitup_tok",
                            data={"base_url": "https://pitup.app", "token": "tok"},
                            options={"motohours": tracked or {}})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _posts(aioclient_mock):
    return [c[2]["value"] for c in aioclient_mock.mock_calls if c[0] == "POST"]


async def test_run_and_stop_sends_hours(hass, aioclient_mock, freezer):
    """30 хв роботи: при зупинці в PitUp іде база + 0.5, без бази вручну."""
    hass.states.async_set(GEN, "off")
    await _setup(hass, aioclient_mock, _gen(44.0), tracked={"1": GEN})
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 44.5})
    hass.states.async_set(GEN, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=30))
    hass.states.async_set(GEN, "off")
    await hass.async_block_till_done()
    assert _posts(aioclient_mock)[-1] == 44.5


async def test_running_pushes_every_15_minutes(hass, aioclient_mock, freezer):
    hass.states.async_set(GEN, "off")
    await _setup(hass, aioclient_mock, _gen(10.0), tracked={"1": GEN})
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 10.25})
    hass.states.async_set(GEN, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _posts(aioclient_mock) == [10.25]


async def test_idle_does_not_push(hass, aioclient_mock, freezer):
    """Простій - жодних запитів (раз на 15 хв шлемо лише під час роботи)."""
    hass.states.async_set(GEN, "off")
    await _setup(hass, aioclient_mock, _gen(10.0), tracked={"1": GEN})
    freezer.tick(timedelta(minutes=45))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _posts(aioclient_mock) == []


async def test_higher_value_in_pitup_rebases_quietly(hass, aioclient_mock, freezer):
    """У PitUp більше (змінили вручну): рахуємо далі від нього, без попереджень і сповіщень."""
    hass.states.async_set(GEN, "off")
    await _setup(hass, aioclient_mock, _gen(10.0), tracked={"1": GEN})
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": False, "value": 50.0})
    hass.states.async_set(GEN, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 50.5})
    freezer.tick(timedelta(minutes=30))
    hass.states.async_set(GEN, "off")
    await hass.async_block_till_done()
    assert _posts(aioclient_mock) == [50.5]
    from homeassistant.components import persistent_notification

    assert not persistent_notification._async_get_or_create_notifications(hass)


async def test_unavailable_is_not_a_stop(hass, aioclient_mock, freezer):
    """Зв'язок з інвертором зник (unavailable) - сесія триває."""
    hass.states.async_set(GEN, "off")
    await _setup(hass, aioclient_mock, _gen(0.0), tracked={"1": GEN})
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 1.0})
    hass.states.async_set(GEN, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=20))
    hass.states.async_set(GEN, "unavailable")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=40))
    hass.states.async_set(GEN, "off")
    await hass.async_block_till_done()
    # Сесія пережила unavailable: при зупинці - уся година від запуску.
    assert _posts(aioclient_mock)[-1] == 1.0


async def test_restart_mid_run_keeps_time(hass, aioclient_mock, freezer):
    """Перезапуск HA посеред роботи: сесія з диска, час не губиться."""
    hass.states.async_set(GEN, "off")
    entry = await _setup(hass, aioclient_mock, _gen(5.0), tracked={"1": GEN})
    hass.states.async_set(GEN, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=30))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.post(ODOMETER, json={"ok": True, "applied": True, "value": 6.0})
    freezer.tick(timedelta(minutes=30))
    hass.states.async_set(GEN, "off")
    await hass.async_block_till_done()
    assert _posts(aioclient_mock)[-1] == 6.0


async def test_options_list_only_hour_vehicles(hass, aioclient_mock):
    """У налаштуваннях - лише техніка з мотогодинами/годинами; вибір зберігається за id."""
    entry = await _setup(hass, aioclient_mock, _gen(1.0), _gen(100, unit_code="km", vid=2, title="Audi"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fields = [str(k) for k in result["data_schema"].schema]
    assert any("GENA" in f for f in fields) and not any("Audi" in f for f in fields)
    gena = next(f for f in fields if "GENA" in f)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"notify_service": "", gena: GEN})
    assert entry.options["motohours"] == {"1": GEN}
