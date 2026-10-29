"""Общая логика запуска для main.py и main_nlp.py."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audience import Audience, AudienceError, MonthRange
from .data import load_respondents, load_views
from .metrics import compute_report
from .presentation import build_presentation

ROOT = Path(__file__).resolve().parent.parent


def add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("start", help="нижняя граница периода, MM.YYYY")
    p.add_argument("end", help="верхняя граница периода, MM.YYYY")
    p.add_argument("output", type=Path, help="путь для сохранения .pptx")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data",
                   help="папка с respondents.csv и views.csv (по умолчанию ./data)")
    p.add_argument("--template", type=Path, default=None,
                   help="шаблон презентации (по умолчанию <data-dir>/presentation_template.pptx)")


def generate(audience: Audience, args: argparse.Namespace) -> None:
    period = MonthRange.parse(args.start, args.end)
    template = args.template or args.data_dir / "presentation_template.pptx"
    for f in (template, args.data_dir / "respondents.csv", args.data_dir / "views.csv"):
        if not f.exists():
            raise AudienceError(f"Файл не найден: {f}")
    report = compute_report(load_respondents(args.data_dir / "respondents.csv"),
                            load_views(args.data_dir / "views.csv"), audience, period)
    build_presentation(template, args.output, audience, period, report)
    print(f"ЦА: {audience.describe()} (размер: {report.audience_size})")
    for name, reach in report.top_reach.items():
        print(f"  {name}: {reach * 100:.2f}%")
    print(f"Презентация сохранена: {args.output}")


def run(build_audience, parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args()
    try:
        generate(build_audience(args), args)
    except AudienceError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(2)
