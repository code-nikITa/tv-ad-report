import argparse

from ad_report.cli import add_common_args, run
from ad_report.nlp import parse_audience

parser = argparse.ArgumentParser(description="Отчёт по рекламным кампаниям на ТВ (NLP-интерфейс)")
parser.add_argument("description", help='описание ЦА, например "Мужчины от 25 до 40 со средним доходом"')
add_common_args(parser)

if __name__ == "__main__":
    run(lambda a: parse_audience(a.description), parser)
