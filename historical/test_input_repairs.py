"""Checks for the sourced Expedia stock entitlement and vendor cash correction."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model"))
from study_inputs import prepare
from direct_stock_backtest import BacktestConfig, DataIntegrityError, run_backtest


class InputRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as directory:
            cls.prices, _, cls.events, _, _, _ = prepare(directory)
            path = Path(directory) / "removed_noncash_dividends.json"
            cls.repairs = json.loads(path.read_text()) if path.exists() else []

    def test_expedia_spin_produces_shares_without_a_cash_dividend(self):
        prices = self.prices.loc[
            self.prices.security_id.isin(["tts-828861", "tts-36804965"])
            & self.prices.date.between("2011-12-20", "2011-12-21")]
        events = self.events.loc[self.events.security_id.eq("tts-828861")
                                 & self.events.date.eq(pd.Timestamp("2011-12-21"))]
        weights = pd.DataFrame([dict(effective_date="2011-12-19", available_date="2011-12-19",
                                     security_id="tts-828861", weight=1.)])
        config = BacktestConfig(start="2011-12-20", end="2011-12-21", harvest=False,
            contribution_dates=("2011-12-20",), fx_fee=0., liquidate_at_end=False)
        result = run_backtest(prices, weights, config, events)
        initial_price = prices.loc[prices.security_id.eq("tts-828861")
            & prices.date.eq(pd.Timestamp("2011-12-20")), "price_eur"].iloc[0]
        units = 1000./initial_price/2.
        final = result.daily.iloc[-1]
        self.assertAlmostEqual(final.holdings["tts-828861"], units)
        self.assertAlmostEqual(final.holdings["tts-36804965"], units)
        self.assertFalse(result.transactions.event.eq("dividend").any())
        self.assertAlmostEqual(final.cash_eur, 0.)

    def test_legitimate_special_cash_dividends_remain(self):
        for security, day, amount in [("tts-282720976", "2016-03-04", 4.),
                                      ("tts-282720976", "2020-02-03", 12.),
                                      ("tts-832472", "2014-11-26", 16.5)]:
            with self.subTest(security=security, day=day):
                row = self.prices.loc[self.prices.security_id.eq(security)
                    & self.prices.date.eq(pd.Timestamp(day))].iloc[0]
                self.assertAlmostEqual(row.dividend_usd, amount)

    def test_removed_cash_has_primary_source_evidence(self):
        self.assertEqual(len(self.repairs), 1)
        self.assertEqual(self.repairs[0]["security_id"], "tts-828861")
        self.assertEqual(self.repairs[0]["date"], "2011-12-21")
        self.assertAlmostEqual(self.repairs[0]["vendor_dividend_usd"], 15.125)
        self.assertIn("sec.gov/Archives/edgar/", self.repairs[0]["source"])

    def test_unresolved_echostar_distribution_fails_only_for_a_holder(self):
        prices = self.prices.loc[self.prices.security_id.eq("tts-12361625")
            & self.prices.date.between("2019-09-10", "2019-09-11")]
        events = self.events.loc[self.events.security_id.eq("tts-12361625")
            & self.events.date.eq(pd.Timestamp("2019-09-11"))]
        self.assertEqual(len(events), 1)
        weights = pd.DataFrame([dict(effective_date="2019-09-09", available_date="2019-09-09",
                                     security_id="tts-12361625", weight=1.)])
        config = BacktestConfig(start="2019-09-10", end="2019-09-11", harvest=False,
            contribution_dates=("2019-09-10",), fx_fee=0., liquidate_at_end=False)
        with self.assertRaisesRegex(DataIntegrityError, "rollover treatment required"):
            run_backtest(prices, weights, config, events)
        weights["security_id"] = "__CASH__"
        result = run_backtest(prices, weights, config, events)
        self.assertEqual(result.daily.iloc[-1].holdings, {})
        self.assertAlmostEqual(result.daily.iloc[-1].cash_eur, 1000.)

    def test_prepare_rejects_action_shift_into_another_tax_year(self):
        original_read_csv = pd.read_csv

        def read_csv(path, *args, **kwargs):
            frame = original_read_csv(path, *args, **kwargs)
            if Path(path).name == "actions.csv":
                frame.loc[frame.security_id.eq("tts-832024")
                          & frame.event_type.eq("cash_merger"), "date"] = pd.Timestamp("2011-12-31")
            return frame

        with TemporaryDirectory() as directory, patch("study_inputs.pd.read_csv", side_effect=read_csv):
            with self.assertRaisesRegex(ValueError, "Corporate action cannot move across tax years"):
                prepare(directory)


if __name__ == "__main__":
    unittest.main()
