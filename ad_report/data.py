"""Загрузка исходных CSV."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_respondents(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df["birth_date"] = pd.to_datetime(df["birth_date"], format="%d.%m.%Y")
    return df


def load_views(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["advertiser", "ad_id", "respondent_id", "date"],
                     dtype=str)
    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%Y")
    return df
