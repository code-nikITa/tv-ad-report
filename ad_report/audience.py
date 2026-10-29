"""Разбор выражения целевой аудитории и диапазона месяцев."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

ALLOWED_INCOME = {"A", "B", "C", "AB", "BC"}  # AC и ABC запрещены

_CLOSED = re.compile(r"^(M|W|ALL)_(\d+)_(\d+)(?:_([ABC]+))?$")
_OPEN = re.compile(r"^(M|W|ALL)_(\d+)\+(?:_([ABC]+))?$")

MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
              "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
_GENDER_RU = {"M": "мужчины", "W": "женщины", "ALL": "все респонденты"}
_INCOME_RU = {
    "A": "с доходом ниже среднего",
    "B": "со средним доходом",
    "C": "с высоким доходом",
    "AB": "с доходом ниже среднего и средним",
    "BC": "со средним и высоким доходом",
}


class AudienceError(ValueError):
    """Некорректные входные параметры."""


@dataclass(frozen=True)
class Audience:
    gender: str                 # "M" | "W" | "ALL"
    age_min: int
    age_max: int | None         # None — открытый интервал (55+)
    income: str | None          # None — без ограничения по доходу

    @classmethod
    def parse(cls, expr: str) -> "Audience":
        expr = expr.strip().upper()
        m = _CLOSED.match(expr)
        if m:
            gender, lo, hi, income = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            if lo > hi:
                raise AudienceError(f"Нижняя граница возраста больше верхней: {expr!r}")
        else:
            m = _OPEN.match(expr)
            if not m:
                raise AudienceError(
                    f"Не удалось разобрать выражение ЦА {expr!r}. Форматы: "
                    "{M|W|ALL}_{от}_{до}[_доход] или {M|W|ALL}_{от}+[_доход]")
            gender, lo, hi, income = m.group(1), int(m.group(2)), None, m.group(3)
        if income is not None:
            if income != "".join(sorted(set(income))) or income not in ALLOWED_INCOME:
                raise AudienceError(
                    f"Недопустимая группа дохода {income!r}: разрешены A, B, C, AB, BC "
                    "(буквы по алфавиту, без AC и ABC)")
        return cls(gender, lo, hi, income)

    def expression(self) -> str:
        age = f"{self.age_min}+" if self.age_max is None else f"{self.age_min}_{self.age_max}"
        return "_".join(p for p in (self.gender, age, self.income) if p)

    def describe(self) -> str:
        if self.age_max is None:
            age = f"от {self.age_min} лет"
        else:
            age = f"от {self.age_min} до {self.age_max} лет"
        parts = [_GENDER_RU[self.gender], age]
        if self.income:
            parts.append(_INCOME_RU[self.income])
        return " ".join(parts)

    def select(self, respondents: pd.DataFrame, as_of: date) -> pd.DataFrame:
        """Респонденты ЦА; возраст — полных лет на дату as_of."""
        b = respondents["birth_date"]
        age = (as_of.year - b.dt.year
               - ((b.dt.month > as_of.month)
                  | ((b.dt.month == as_of.month) & (b.dt.day > as_of.day))).astype(int))
        mask = age >= self.age_min
        if self.age_max is not None:
            mask &= age <= self.age_max
        if self.gender != "ALL":
            mask &= respondents["gender"] == self.gender
        if self.income:
            mask &= respondents["income_group"].isin(list(self.income))
        return respondents[mask]


@dataclass(frozen=True)
class MonthRange:
    start: pd.Period
    end: pd.Period

    @classmethod
    def parse(cls, lo: str, hi: str) -> "MonthRange":
        start, end = _parse_month(lo), _parse_month(hi)
        if start > end:
            raise AudienceError(f"Начало периода {lo} позже конца {hi}")
        return cls(start, end)

    @property
    def first_day(self) -> date:
        return date(self.start.year, self.start.month, 1)

    @property
    def last_day(self) -> date:
        return date(self.end.year, self.end.month,
                    calendar.monthrange(self.end.year, self.end.month)[1])

    @property
    def months(self) -> list[pd.Period]:
        return list(pd.period_range(self.start, self.end, freq="M"))

    def describe(self) -> str:
        def fmt(p): return f"{MONTHS_NOM[p.month - 1]} {p.year}"
        return fmt(self.start) if self.start == self.end else f"{fmt(self.start)} – {fmt(self.end)}"


def _parse_month(s: str) -> pd.Period:
    m = re.fullmatch(r"(\d{2})\.(\d{4})", s.strip())
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise AudienceError(f"Месяц должен быть в формате MM.YYYY, получено {s!r}")
    return pd.Period(year=int(m.group(2)), month=int(m.group(1)), freq="M")
