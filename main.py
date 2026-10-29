import argparse

from ad_report.audience import Audience
from ad_report.cli import add_common_args, run

parser = argparse.ArgumentParser(description="Отчёт по рекламным кампаниям на ТВ")
parser.add_argument("audience", help="выражение ЦА, например M_25_40_B, W_55+, ALL_18_35")
add_common_args(parser)

if __name__ == "__main__":
    run(lambda a: Audience.parse(a.audience), parser)
