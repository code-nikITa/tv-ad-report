from datetime import date

import pandas as pd
import pytest

from ad_report.audience import Audience, AudienceError, MonthRange
from ad_report.metrics import compute_report
from ad_report.nlp import parse_rule_based


def test_parse_expressions():
    assert Audience.parse("ALL_18_35") == Audience("ALL", 18, 35, None)
    assert Audience.parse("W_25_45_BC") == Audience("W", 25, 45, "BC")
    assert Audience.parse("M_60+_A") == Audience("M", 60, None, "A")


@pytest.mark.parametrize("bad", ["X_18_35", "M_40_30", "M_20_30_AC", "M_20_30_ABC", "M_20_30_CB", "M_20", ""])
def test_parse_errors(bad):
    with pytest.raises(AudienceError):
        Audience.parse(bad)


def test_month_range():
    p = MonthRange.parse("01.2024", "02.2024")
    assert p.last_day == date(2024, 2, 29) and len(p.months) == 2
    with pytest.raises(AudienceError):
        MonthRange.parse("13.2024", "01.2025")
    with pytest.raises(AudienceError):
        MonthRange.parse("06.2025", "01.2024")


def _resp(rows):
    df = pd.DataFrame(rows, columns=["id", "gender", "birth_date", "income_group"])
    df["birth_date"] = pd.to_datetime(df["birth_date"], format="%d.%m.%Y")
    return df


def test_age_uses_full_years_at_period_end():
    r = _resp([("a", "M", "01.07.2000", "A"), ("b", "M", "30.06.2000", "A")])
    # на 30.06.2025: a — 24 полных года, b — 25
    got = Audience.parse("ALL_25_25").select(r, date(2025, 6, 30))
    assert list(got["id"]) == ["b"]


def test_reach_and_trp():
    r = _resp([(c, "M", "01.01.1990", "B") for c in "abcd"]
              + [("z", "W", "01.01.1990", "B")])           # z вне ЦА
    rows = [  # advertiser, ad_id, respondent, date
        ("X", "x1", "a", "05.01.2024"), ("X", "x1", "a", "06.01.2024"),   # повтор
        ("X", "x1", "b", "10.02.2024"),
        ("X", "x2", "a", "11.02.2024"),
        ("Y", "y1", "c", "12.02.2024"), ("Y", "y1", "z", "12.02.2024"),
        ("Y", "y2", "z", "13.02.2024"),                                    # охват ЦА = 0
        ("X", "x3", "a", "01.03.2024"),                                    # вне периода
    ]
    v = pd.DataFrame(rows, columns=["advertiser", "ad_id", "respondent_id", "date"])
    v["date"] = pd.to_datetime(v["date"], format="%d.%m.%Y")
    rep = compute_report(r, v, Audience.parse("M_30_40"), MonthRange.parse("01.2024", "02.2024"))
    assert rep.audience_size == 4
    # X: x1 -> 2/4, x2 -> 1/4 => 0.375 ; Y: y1 -> 1/4, y2 -> 0 => 0.125
    assert rep.top_reach["X"] == pytest.approx(0.375)
    assert rep.top_reach["Y"] == pytest.approx(0.125)
    assert list(rep.top_reach.index) == ["X", "Y"]
    # TRP X: янв = 2 просмотра -> 50, фев = 2 -> 50; Y: фев = 1 -> 25
    assert rep.trp.loc[pd.Period("2024-01"), "X"] == pytest.approx(50)
    assert rep.trp.loc[pd.Period("2024-02"), "X"] == pytest.approx(50)
    assert rep.trp.loc[pd.Period("2024-02"), "Y"] == pytest.approx(25)
    assert rep.trp.loc[pd.Period("2024-01"), "Y"] == 0


def test_nlp_rule_based():
    assert parse_rule_based("Мужчины от 25 до 40 со средним доходом") == Audience("M", 25, 40, "B")
    assert parse_rule_based("женщины 25-45 со средним и высоким доходом") == Audience("W", 25, 45, "BC")
    assert parse_rule_based("Мужчины старше 59 с доходом ниже среднего") == Audience("M", 60, None, "A")
    assert parse_rule_based("все от 18 до 35") == Audience("ALL", 18, 35, None)
    assert parse_rule_based("женщины от 55 лет, доход средний и выше") == Audience("W", 55, None, "BC")


def test_llm_branch_with_mock_server(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from ad_report.nlp import parse_audience

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            assert self.headers["Authorization"] == "Bearer k"
            self.rfile.read(int(self.headers["Content-Length"]))
            content = '```json\n{"gender":"W","age_min":30,"age_max":null,"income":"BC"}\n```'
            payload = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{srv.server_port}/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    try:
        assert parse_audience("что угодно") == Audience("W", 30, None, "BC")
    finally:
        srv.shutdown()


def test_llm_failure_falls_back(monkeypatch):
    from ad_report.nlp import parse_audience
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")  # порт закрыт
    monkeypatch.setenv("LLM_MODEL", "m")
    assert parse_audience("Мужчины от 25 до 40 со средним доходом") == Audience("M", 25, 40, "B")
