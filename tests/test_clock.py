from datetime import date, datetime

import pytest

from emporio_agent.clock import TZ, Clock, hours_on, parse_now, store_status


def at(value: str) -> datetime:
    return parse_now(value)


def test_parse_now_defaults_to_campo_grande():
    dt = parse_now("2026-02-20")
    assert dt.tzinfo == TZ and dt.hour == 10
    assert parse_now("2026-02-20T10:00-04:00").utcoffset().total_seconds() == -4 * 3600
    assert parse_now("2026-02-20T14:00+00:00").hour == 10  # converted to local time


def test_clock_from_env(monkeypatch):
    monkeypatch.setenv("NOW", "2026-02-20T10:00")
    clock = Clock.from_env()
    assert clock.is_override and clock.today() == date(2026, 2, 20)
    monkeypatch.delenv("NOW")
    assert not Clock.from_env().is_override
    assert Clock.from_env("2026-03-01").today() == date(2026, 3, 1)


def test_consciencia_negra_is_closed():
    day = hours_on(date(2026, 11, 20))  # a Friday
    assert not day.is_open_day
    assert "Consciência Negra" in day.holiday
    assert "fechado (feriado" in day.describe()


def test_saturday_hours():
    day = hours_on(date(2026, 11, 21))
    assert day.weekday == "sábado"
    assert day.describe() == "sábado, 21/11/2026: aberto das 09:00 às 13:00"


def test_sunday_closed():
    assert not hours_on(date(2026, 11, 22)).is_open_day


def test_ms_state_holiday():
    assert hours_on(date(2026, 10, 11)).holiday == "Criação do Estado"


@pytest.mark.parametrize(
    ("now", "is_open", "next_opening"),
    [
        ("2026-11-04T10:00", True, None),  # Wednesday morning
        ("2026-11-04T18:00", False, "2026-11-05T09:00"),  # closing time is exclusive
        ("2026-11-04T07:30", False, "2026-11-04T09:00"),  # before opening
        ("2026-11-21T12:59", True, None),  # Saturday
        ("2026-11-21T13:00", False, "2026-11-23T09:00"),  # skips Sunday
        ("2026-11-19T19:00", False, "2026-11-21T09:00"),  # skips the 20/11 holiday
    ],
)
def test_store_status(now, is_open, next_opening):
    status = store_status(at(now))
    assert status.is_open is is_open
    assert status.next_opening == (at(next_opening) if next_opening else None)
    assert status.describe()
