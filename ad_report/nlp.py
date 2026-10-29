"""Извлечение параметров ЦА из текста на естественном языке."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from .audience import ALLOWED_INCOME, Audience, AudienceError

SYSTEM_PROMPT = """Ты извлекаешь параметры целевой аудитории из описания на русском или английском.
Верни ТОЛЬКО JSON без пояснений и без markdown:
{"gender": "M" | "W" | "ALL", "age_min": int, "age_max": int | null, "income": "A" | "B" | "C" | "AB" | "BC" | null}
Правила: M — мужчины, W — женщины, ALL — пол не указан или оба. age_max = null для открытого интервала («от 55», «старше 60» -> 61).
«до 30» -> age_min 0, age_max 30; не указан возраст -> age_min 0, age_max null.
Доход: A — ниже среднего, B — средний, C — высокий. Допустимы только A, B, C, AB, BC. Нет упоминания — null."""


def _from_dict(d: dict) -> Audience:
    gender = str(d.get("gender") or "ALL").upper()
    income = d.get("income")
    income = "".join(sorted(set(str(income).upper()))) if income else None
    if income is not None and income not in ALLOWED_INCOME:
        income = None
    age_min = int(d.get("age_min") or 0)
    age_max = d.get("age_max")
    expr = Audience(gender, age_min, int(age_max) if age_max is not None else None, income).expression()
    return Audience.parse(expr)  # повторная проверка по общим правилам


def parse_with_llm(text: str) -> Audience:
    """Разбор через любой OpenAI-совместимый Chat Completions API.

    Настройки только через переменные окружения:
      LLM_API_KEY  — ключ (для локальных серверов может быть не нужен);
      LLM_BASE_URL — базовый URL API, например https://api.openai.com/v1 или http://localhost:11434/v1;
      LLM_MODEL    — имя модели.
    """
    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("LLM_MODEL", "")
    if not base or not model:
        raise AudienceError("для LLM-режима нужны LLM_BASE_URL и LLM_MODEL")
    headers = {"Content-Type": "application/json"}
    if key := os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = f"Bearer {key}"
    body = json.dumps({
        "model": model, "temperature": 0, "max_tokens": 300,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.load(resp)["choices"][0]["message"]["content"]
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return _from_dict(json.loads(raw))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        raise AudienceError(f"LLM вернула непригодный ответ: {raw!r}") from e


def parse_rule_based(text: str) -> Audience:
    """Запасной вариант без LLM: эвристики для типичных русских формулировок."""
    t = text.lower().replace("ё", "е")

    male = bool(re.search(r"мужчин|мужск|парн|\bmen\b|\bmale", t))
    female = bool(re.search(r"женщин|женск|девуш|\bwomen\b|\bfemale", t))
    gender = "M" if male and not female else "W" if female and not male else "ALL"

    age_min, age_max = 0, None
    if m := re.search(r"(\d+)\s*(?:-|–|—|до|по)\s*(\d+)", t):
        age_min, age_max = int(m.group(1)), int(m.group(2))
    elif m := re.search(r"(?:старше)\s*(\d+)", t):
        age_min = int(m.group(1)) + 1
    elif m := re.search(r"(?:моложе|младше)\s*(\d+)", t):
        age_max = int(m.group(1)) - 1
    elif m := re.search(r"(?:от|с)\s*(\d+)(?:\s*(?:лет|и старше|\+))?", t):
        age_min = int(m.group(1))
    elif m := re.search(r"(\d+)\s*\+", t):
        age_min = int(m.group(1))
    elif m := re.search(r"до\s*(\d+)", t):
        age_max = int(m.group(1))
    if age_max is not None and age_max < age_min:
        age_min, age_max = age_max, age_min

    levels: set[str] = set()
    s = t
    if re.search(r"средн\w*\s+и\s+(?:выше|высок)", s):
        levels |= {"B", "C"}
        s = re.sub(r"средн\w*\s+и\s+(?:выше|высок\w*)", " ", s)
    if re.search(r"ниже\s+средн|низк|небольш", s):
        levels.add("A")
        s = re.sub(r"ниже\s+средн\w*|низк\w*|небольш\w*", " ", s)
    if re.search(r"выше\s+средн|высок|больш\w+\s+доход", s):
        levels.add("C")
        s = re.sub(r"выше\s+средн\w*|высок\w*", " ", s)
    if re.search(r"средн", s):
        levels.add("B")
    income = "".join(sorted(levels))
    if income not in ALLOWED_INCOME:  # AC / ABC — не поддерживаются, снимаем ограничение
        income = None

    return Audience(gender, age_min, age_max, income)


def parse_audience(text: str) -> Audience:
    if os.environ.get("LLM_BASE_URL") or os.environ.get("LLM_API_KEY"):
        try:
            return parse_with_llm(text)
        except (AudienceError, urllib.error.URLError, OSError, KeyError, IndexError, ValueError) as e:
            print(f"Предупреждение: LLM недоступна ({e}); использую разбор по правилам.",
                  file=sys.stderr)
    else:
        print("Предупреждение: LLM не настроена (LLM_BASE_URL / LLM_API_KEY); "
              "использую разбор по правилам.", file=sys.stderr)
    return parse_rule_based(text)
