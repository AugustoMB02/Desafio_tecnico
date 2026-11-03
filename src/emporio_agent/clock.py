"""One injectable clock in America/Campo_Grande, and the store's opening hours (§2).

Real time is the default. A `NOW` override (env var or `--now`) freezes the clock for
scripted example and test runs; records dated after it are hidden, so an override never
exposes orders "from the future".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import holidays

from .money import fmt_date

TZ = ZoneInfo("America/Campo_Grande")
WEEKDAYS_PT = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
    "sábado", "domingo",
)  # fmt: skip

# §2: Mon–Fri 09:00–18:00, Sat 09:00–13:00, Sunday and holidays closed.
WEEKLY_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(9), time(18)),
    1: (time(9), time(18)),
    2: (time(9), time(18)),
    3: (time(9), time(18)),
    4: (time(9), time(18)),
    5: (time(9), time(13)),
    6: None,
}


def parse_now(value: str) -> datetime:
    """ISO date or datetime; without an offset it is read as Campo Grande local time."""
    value = value.strip()
    parsed = (
        datetime.combine(date.fromisoformat(value), time(10))
        if len(value) == 10
        else datetime.fromisoformat(value)
    )
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)


@dataclass(frozen=True)
class Clock:
    fixed: datetime | None = None

    @classmethod
    def from_env(cls, override: str | None = None) -> Clock:
        value = override or os.environ.get("NOW", "").strip()
        return cls(parse_now(value)) if value else cls()

    @property
    def is_override(self) -> bool:
        return self.fixed is not None

    def now(self) -> datetime:
        return self.fixed if self.fixed is not None else datetime.now(TZ)

    def today(self) -> date:
        return self.now().date()


@cache
def _holidays(year: int) -> holidays.HolidayBase:
    return holidays.Brazil(subdiv="MS", years=year)


def holiday_name(day: date) -> str | None:
    """National and Mato Grosso do Sul holidays (municipal ones are a known gap)."""
    return _holidays(day.year).get(day)


@dataclass(frozen=True)
class DayHours:
    day: date
    weekday: str
    hours: tuple[time, time] | None
    holiday: str | None

    @property
    def is_open_day(self) -> bool:
        return self.hours is not None

    def describe(self) -> str:
        label = f"{self.weekday}, {fmt_date(self.day)}"
        if self.holiday:
            return f"{label}: fechado (feriado: {self.holiday})"
        if self.hours is None:
            return f"{label}: fechado"
        start, end = self.hours
        return f"{label}: aberto das {start:%H:%M} às {end:%H:%M}"


def hours_on(day: date) -> DayHours:
    name = holiday_name(day)
    hours = None if name else WEEKLY_HOURS[day.weekday()]
    return DayHours(day, WEEKDAYS_PT[day.weekday()], hours, name)


@dataclass(frozen=True)
class StoreStatus:
    now: datetime
    is_open: bool
    today: DayHours
    next_opening: datetime | None  # None while open

    def describe(self) -> str:
        if self.is_open:
            _, end = self.today.hours  # type: ignore[misc]
            return f"A loja está aberta agora (fecha às {end:%H:%M})."
        assert self.next_opening is not None
        when = hours_on(self.next_opening.date())
        return (
            f"A loja está fechada agora. Próxima abertura: {when.weekday}, "
            f"{fmt_date(self.next_opening)} às {self.next_opening:%H:%M}."
        )


def store_status(now: datetime) -> StoreStatus:
    now = now.astimezone(TZ)
    today = hours_on(now.date())
    if today.hours and today.hours[0] <= now.time() < today.hours[1]:
        return StoreStatus(now, True, today, None)
    day = now.date()
    if today.hours and now.time() < today.hours[0]:
        return StoreStatus(now, False, today, datetime.combine(day, today.hours[0], TZ))
    for offset in range(1, 15):
        nxt = hours_on(day + timedelta(days=offset))
        if nxt.hours:
            return StoreStatus(now, False, today, datetime.combine(nxt.day, nxt.hours[0], TZ))
    raise RuntimeError("no opening found in the next two weeks")
