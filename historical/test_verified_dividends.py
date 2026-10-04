"""Regression checks for sourced dividend dates, duplicates and deferred cash."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model"))
from study_inputs import (load_verified_dividends, replace_verified_dividend_duplicates,
                          verified_dividend_events)
from direct_stock_backtest import BacktestConfig, run_backtest


class VerifiedDividendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = pd.read_csv(ROOT / "benchmark/indexes/NASDAQ100.csv", parse_dates=[0])
        cls.calendar = pd.DatetimeIndex(raw.loc[raw.iloc[:, 1].notna(), raw.columns[0]])
        cls.sourced = load_verified_dividends(cls.calendar)

    def load_rows(self, rows):
        defaults = dict(security_id="A", declaration_date="", ex_date="", record_date="2020-09-01",
                        payment_date="2020-09-30", cash_usd_per_share=.15, source_url="https://issuer.example/report",
                        dividend_type="ordinary_regular_cash", payment_evidence="issuer_report_confirms_payment")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "dividends.csv"
            pd.DataFrame([dict(defaults, **row) for row in rows]).to_csv(path, index=False)
            return load_verified_dividends(self.calendar, path)

    def test_complete_recovered_schedules_and_evidence_limits(self):
        counts = self.sourced.groupby("security_id").size().to_dict()
        self.assertEqual(counts, {"yahoo:CDK": 31, "yahoo:LOGM": 11})
        totals = self.sourced.groupby("security_id").cash_usd_per_share.sum()
        self.assertAlmostEqual(totals["yahoo:CDK"], 4.43)
        self.assertAlmostEqual(totals["yahoo:LOGM"], 3.25)
        self.assertTrue(self.sourced.ex_date.isna().all())
        self.assertTrue(self.sourced.ex_date_quality.eq("derived_Nasdaq_11140_regular_distribution").all())
        self.assertEqual(self.sourced.payment_evidence.eq("issuer_report_confirms_payment").sum(), 41)
        last = self.sourced[self.sourced.security_id.eq("yahoo:CDK")].iloc[-1]
        self.assertEqual(last.payment_date, pd.Timestamp("2022-06-29"))
        self.assertEqual(last.payment_evidence, "issuer_declared_schedule_only")

    def test_verified_record_and_payment_dates_remain_distinct(self):
        expected = [("yahoo:CDK", "2020-09-01", "2020-09-30", "2020-08-31"),
                    ("yahoo:CDK", "2020-12-01", "2020-12-30", "2020-11-30"),
                    ("yahoo:CDK", "2021-03-08", "2021-03-30", "2021-03-05"),
                    ("yahoo:CDK", "2021-06-21", "2021-06-30", "2021-06-18"),
                    ("yahoo:LOGM", "2018-08-08", "2018-08-24", "2018-08-07")]
        for security, record, payment, ex in expected:
            with self.subTest(security=security, payment=payment):
                row = self.sourced[self.sourced.security_id.eq(security)
                                   & self.sourced.payment_date.eq(pd.Timestamp(payment))].iloc[0]
                self.assertEqual(row.record_date, pd.Timestamp(record))
                self.assertEqual(row.entitlement_date, pd.Timestamp(ex))
                self.assertEqual(row.payment_session, pd.Timestamp(payment))

    def test_historical_ex_date_rules_include_transition_and_holidays(self):
        expected = {"2017-09-01": "2017-08-30", "2017-09-05": "2017-08-31",
                    "2017-09-06": "2017-09-01", "2017-09-07": "2017-09-06",
                    "2018-09-01": "2018-08-30", "2022-06-20": "2022-06-16"}
        for record, ex in expected.items():
            with self.subTest(record=record):
                result = self.load_rows([dict(record_date=record,
                    payment_date=str((pd.Timestamp(record)+pd.Timedelta(days=20)).date()))])
                self.assertEqual(result.iloc[0].entitlement_date, pd.Timestamp(ex))

    def test_observed_ex_date_is_preserved_without_derivation(self):
        result = self.load_rows([dict(ex_date="2020-08-31")])
        self.assertEqual(result.iloc[0].ex_date, result.iloc[0].entitlement_date)
        self.assertEqual(result.iloc[0].ex_date_quality, "issuer_or_exchange_verified")

    def test_duplicate_invalid_and_unsupported_sources_fail(self):
        for rows in ([{}, {}], [dict(cash_usd_per_share=-.15)], [dict(source_url="")],
                     [dict(record_date="2020-10-01")], [dict(dividend_type="special_distribution")]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.load_rows(rows)

    def test_matching_vendor_and_action_dividends_are_replaced_once(self):
        dividends = self.load_rows([{}])
        prices = pd.DataFrame([dict(date=pd.Timestamp("2020-08-31"), security_id="A", dividend_usd=.15)])
        actions = pd.DataFrame([dict(date=pd.Timestamp("2020-09-30"), security_id="A",
                                     event_type="cash_dividend", cash_usd_per_share=.15)])
        p, a, replaced = replace_verified_dividend_duplicates(prices, actions, dividends)
        self.assertEqual(p.dividend_usd.sum(), 0.)
        self.assertTrue(a.empty)
        self.assertEqual(len(replaced), 2)
        _, _, repeated = replace_verified_dividend_duplicates(p, a, dividends)
        self.assertEqual(repeated, [])
        prices.loc[0, "dividend_usd"] = .16
        with self.assertRaisesRegex(ValueError, "Conflicting verified dividend"):
            replace_verified_dividend_duplicates(prices, actions, dividends)

    def test_events_do_not_use_future_fx_for_entitlement(self):
        dividends = self.load_rows([{}])
        fx = pd.Series([1., 2.], index=pd.to_datetime(["2020-08-31", "2020-09-30"]))
        events = verified_dividend_events(dividends, fx)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["cash_eur_per_share"], .15)
        self.assertEqual(events[1]["cash_eur_per_share"], .075)
        fx.iloc[-1] = 3.
        changed = verified_dividend_events(dividends, fx)
        self.assertEqual(events[0], changed[0])
        self.assertAlmostEqual(changed[1]["cash_eur_per_share"], .05)

    def test_restored_payment_excludes_ex_date_purchase_and_early_cash(self):
        dividends = self.load_rows([{}])
        fx = pd.Series([1., 2.], index=pd.to_datetime(["2020-08-31", "2020-09-30"]))
        events = pd.DataFrame(verified_dividend_events(dividends, fx))
        days = ["2020-08-28", "2020-08-31", "2020-09-01", "2020-09-30"]
        prices = pd.DataFrame([dict(date=day, security_id="A", price_eur=100., dividend_eur=0.) for day in days])
        weights = pd.DataFrame([dict(effective_date="2020-08-27", available_date="2020-08-27", security_id="A", weight=1.)])
        config = BacktestConfig(start=days[0], end=days[-1], contribution_dates=tuple(days[:2]),
            harvest=False, fx_fee=0., dividend_income_tax=0., dividend_usc=0., dividend_prsi=0.,
            foreign_dividend_withholding=0.)
        result = run_backtest(prices, weights, config, events)
        receipts = result.transactions[result.transactions.event.eq("dividend")]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts.iloc[0].date, pd.Timestamp("2020-09-30"))
        self.assertAlmostEqual(receipts.iloc[0].gross_eur, .75)
        self.assertEqual(result.daily.iloc[1].cash_eur, 0.)
        self.assertAlmostEqual(result.summary["total_gross_dividends"], .75)


if __name__ == "__main__":
    unittest.main()
