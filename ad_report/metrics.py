"""Расчёт охвата и TRP."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .audience import Audience, AudienceError, MonthRange

TOP_N = 5


@dataclass
class Report:
    audience_size: int
    top_reach: pd.Series        # индекс — рекламодатель, значения — средний охват (доля 0..1), по убыванию
    trp: pd.DataFrame           # строки — месяцы (Period), столбцы — рекламодатели из top_reach


def compute_report(respondents: pd.DataFrame, views: pd.DataFrame,
                   audience: Audience, period: MonthRange) -> Report:
    ta = audience.select(respondents, period.last_day)
    size = len(ta)
    if size == 0:
        raise AudienceError("В выбранную целевую аудиторию не попал ни один респондент")

    start, end = pd.Timestamp(period.first_day), pd.Timestamp(period.last_day)
    v = views[(views["date"] >= start) & (views["date"] <= end)]

    # Ролики, попавшие в период: есть хотя бы один просмотр (любым респондентом).
    ads = v[["advertiser", "ad_id"]].drop_duplicates()
    if ads.empty:
        raise AudienceError("В указанном периоде нет данных о просмотрах")

    v_ta = v[v["respondent_id"].isin(set(ta["id"]))]

    # Шаг 1. Охват ролика = уникальные зрители ЦА / размер ЦА.
    viewers = v_ta.drop_duplicates(["ad_id", "respondent_id"]).groupby("ad_id").size()
    ads = ads.assign(reach=ads["ad_id"].map(viewers).fillna(0) / size)
    avg_reach = ads.groupby("advertiser")["reach"].mean()
    top = (avg_reach.rename_axis("advertiser").reset_index()
           .sort_values(["reach", "advertiser"], ascending=[False, True])
           .head(TOP_N).set_index("advertiser")["reach"])

    # Шаг 2. TRP = 100 * просмотры ЦА / размер ЦА (с повторами), по месяцам.
    v_top = v_ta[v_ta["advertiser"].isin(top.index)]
    month = v_top["date"].dt.to_period("M")
    counts = (v_top.groupby([month.rename("month"), "advertiser"]).size()
              .unstack("advertiser").reindex(index=period.months, columns=list(top.index))
              .fillna(0))
    return Report(size, top, counts * 100 / size)
