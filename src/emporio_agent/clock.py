"""One injectable clock in America/Campo_Grande, and the store's opening hours (§2).

Real time is the default. A `NOW` override (env var or `--now`) freezes the clock for
scripted example and test runs; records dated after it are hidden, so an override never
exposes orders "from the future".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import holidays
from holidays.constants import OPTIONAL

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


# Days the manual's "Feriados: fechado" may or may not cover. The store has not published
# its schedule for them, so the agent states the usual hours with a caveat instead of
# asserting either way. ASSUMPTION: Campo Grande's municipal holidays are 13/06 (Santo
# Antônio, padroeiro) and 26/08 (aniversário da cidade).
MUNICIPAL_CAMPO_GRANDE = {(6, 13): "Dia de Santo Antônio, padroeiro de Campo Grande",
                          (8, 26): "Aniversário de Campo Grande"}  # fmt: skip
_IRRELEVANT_OPTIONAL = {"Dia do Servidor Público"}  # a public-sector day off, not a store's


@cache
def _holidays(year: int) -> holidays.HolidayBase:
    # language is explicit: without it, `holidays` follows the OS locale (English names on
    # en_US machines), which broke tests and leaked English into tool outputs.
    return holidays.Brazil(subdiv="MS", years=year, language="pt_BR")


@cache
def _optional_holidays(year: int) -> holidays.HolidayBase:
    return holidays.Brazil(subdiv="MS", years=year, language="pt_BR", categories=(OPTIONAL,))


def holiday_name(day: date) -> str | None:
    """National and Mato Grosso do Sul public holidays."""
    return _holidays(day.year).get(day)


def uncertain_day(day: date) -> str | None:
    """Ponto facultativo or municipal holiday: the store may change its hours."""
    if name := MUNICIPAL_CAMPO_GRANDE.get((day.month, day.day)):
        return f"feriado municipal: {name}"
    name = _optional_holidays(day.year).get(day)
    if name and name not in _IRRELEVANT_OPTIONAL:
        return f"ponto facultativo: {name}"
    return None


@dataclass(frozen=True)
class DayHours:
    day: date
    weekday: str
    hours: tuple[time, time] | None
    holiday: str | None
    caveat: str | None = None

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
        text = f"{label}: aberto das {start:%H:%M} às {end:%H:%M}"
        if self.caveat:
            text += (
                f" — atenção, {self.caveat}: o horário pode mudar nesse dia; diga que é o "
                "horário normal e que a loja confirma"
            )
        return text


def hours_on(day: date) -> DayHours:
    name = holiday_name(day)
    hours = None if name else WEEKLY_HOURS[day.weekday()]
    caveat = uncertain_day(day) if hours else None
    return DayHours(day, WEEKDAYS_PT[day.weekday()], hours, name, caveat)


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


_DMY = re.compile(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{4}|\d{2}))?")


def parse_day(text: str, today: date, prefer: str = "future") -> date | None:
    """Parse a customer date: aaaa-mm-dd, dd/mm/aaaa, dd/mm/aa, dd-mm-aaaa or dd/mm.

    Two-digit years are 20aa. Without a year, `prefer="future"` picks the next occurrence
    (opening hours) and `prefer="past"` the latest one up to today (a delivery date).
    """
    text = text.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    m = _DMY.fullmatch(text)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if year is not None:
            return date(2000 + int(year) if len(year) == 2 else int(year), month, day)
        options = []
        for y in (today.year - 1, today.year, today.year + 1):
            try:
                options.append(date(y, month, day))
            except ValueError:
                continue
        if prefer == "past":
            past = [d for d in options if d <= today]
            return max(past) if past else None
        future = [d for d in options if d >= today]
        return min(future) if future else None
    except ValueError:
        return None
