"""Synthetic cash-flow checks for the accumulating-fund replay."""
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_stock_backtest import BacktestConfig, run_backtest
from etf_backtest import monthly_dates, replay


class ETFBacktestTests(unittest.TestCase):
    def setUp(self):
        self.days = pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31",
                                    "2020-04-30", "2020-05-29"])
        self.prices = pd.Series([100.0, 110.0, 90.0, 120.0, 120.0], index=self.days)
        self.options = dict(start=str(self.days[0].date()), end=str(self.days[-1].date()),
                            tax_rate=.33, deemed_disposal=False)

    def test_variable_inflows_match_ledgers_tax_and_single_stock(self):
        amounts = (1000.0, 1100.0, 900.0, 0.0)
        summary, ledger, path = replay(self.prices, contribution_amounts=amounts, **self.options)
        deposits = ledger.query("event == 'contribution'")
        self.assertEqual(deposits.cash.tolist(), list(amounts))
        self.assertEqual(deposits.date.tolist(), self.days[:-1].tolist())
        self.assertEqual(deposits.units.tolist(), [10, 10, 10, 0])
        self.assertEqual(path.contributed.tolist(), [1000, 2100, 3000, 3000, 3000])
        self.assertEqual(summary["contribution_count"], 4)
        self.assertEqual(summary["contributions"], 3000)
        self.assertAlmostEqual(summary["total_tax"], 600 * .33)
        self.assertAlmostEqual(summary["final_cash"], 3600 - 600 * .33)

        prices = pd.DataFrame(dict(date=self.days, security_id="A", price_eur=self.prices.values))
        weights = pd.DataFrame([dict(effective_date="2020-01-30", available_date="2020-01-30",
                                     security_id="A", weight=1.0)])
        dates = tuple(str(d.date()) for d in sorted(monthly_dates(
            self.prices, self.options["start"], self.options["end"])))
        config = BacktestConfig(start=self.options["start"], end=self.options["end"],
                                contribution_dates=dates, contribution_amounts=amounts,
                                harvest=False, fx_fee=0.0, cgt_exemption=0.0, cgt_rate=.33)
        stock = run_backtest(prices, weights, config)
        stock_deposits = stock.transactions.query("event == 'contribution'")
        self.assertEqual(stock_deposits.cash_eur.tolist(), deposits.cash.tolist())
        self.assertEqual(stock_deposits.date.tolist(), deposits.date.tolist())
        for key in ("contributions", "contribution_count", "total_tax", "final_cash"):
            self.assertAlmostEqual(stock.summary[key], summary[key])

    def test_future_amount_cannot_change_prefix_or_replace_zero(self):
        first = replay(self.prices, contribution_amounts=(0.0, 1100.0, 900.0, 0.0), **self.options)
        second = replay(self.prices, contribution_amounts=(0.0, 1100.0, 90000.0, 0.0), **self.options)
        self.assertEqual(first[2].iloc[0].contributed, 0)
        self.assertEqual(first[2].iloc[0].value, 0)
        for original, changed in zip(first[1:], second[1:]):
            pd.testing.assert_frame_equal(original[original.date < self.days[2]].reset_index(drop=True),
                                          changed[changed.date < self.days[2]].reset_index(drop=True))

    def test_constant_tuple_matches_default(self):
        original = replay(self.prices, **self.options)
        explicit = replay(self.prices, contribution_amounts=(1000.0,) * 4, **self.options)
        self.assertEqual(original[0], explicit[0])
        for first, second in zip(original[1:], explicit[1:]):
            pd.testing.assert_frame_equal(first, second)

    def test_same_day_contribution_pays_dd_before_purchase(self):
        prices = pd.Series([100., 200., 300.], index=pd.to_datetime(
            ["2010-09-30", "2018-09-30", "2018-10-31"]))
        options = dict(start="2010-09-30", end="2018-10-31",
                       contribution_amounts=(100., 50.))
        summary, ledger, _ = replay(prices, **options)
        self.assertFalse(ledger.event.eq("fund_tax_with_fifo_sale").any())
        deposits = ledger[ledger.event.eq("contribution")]
        self.assertEqual(deposits.cash.tolist(), [100., 50.])
        self.assertEqual(deposits.invested_cash.tolist(), [100., 12.])
        self.assertEqual(deposits.tax_funding_cash.tolist(), [0., 38.])
        self.assertEqual(deposits.units.tolist(), [1., .06])
        self.assertAlmostEqual(summary["final_cash"], 277.72)
        self.assertAlmostEqual(summary["total_tax"], 78.28)
        final = ledger[ledger.event.eq("final_sale")].iloc[0]
        self.assertAlmostEqual(deposits.cash.sum()+final.gross_proceeds
                               -deposits.invested_cash.sum()-summary["total_tax"],
                               summary["final_cash"])
        _, legacy, _ = replay(prices, contribution_first=False, **options)
        sale = legacy[legacy.event.eq("fund_tax_with_fifo_sale")].iloc[0]
        self.assertAlmostEqual(sale.gross_proceeds, 38.)
        self.assertAlmostEqual(sale.tax, 0.)

    def test_contribution_shortfall_uses_fifo_and_proportional_dd_credit(self):
        prices = pd.Series([100., 100., 200., 300., 300.], index=pd.to_datetime(
            ["2010-01-31", "2010-02-28", "2018-01-31", "2018-02-28", "2018-03-31"]))
        summary, ledger, _ = replay(prices, start="2010-01-31", end="2018-03-31",
                                    contribution_amounts=(100., 100., 50., 20.))
        deposits = ledger[ledger.event.eq("contribution")]
        sales = ledger[ledger.event.eq("fund_tax_with_fifo_sale")]
        self.assertEqual(len(sales), 1)
        sale = sales.iloc[0]
        self.assertEqual(sale.acquisition, pd.Timestamp("2010-01-31"))
        self.assertAlmostEqual(sale.units, 56./262.)
        self.assertAlmostEqual(sale.tax, sale.units*38.)
        self.assertAlmostEqual(sale.gross_proceeds-sale.tax, 56.)
        self.assertEqual(deposits.invested_cash.tolist(), [100., 100., 12., 0.])
        self.assertEqual(deposits.tax_funding_cash.tolist(), [0., 0., 38., 20.])
        self.assertAlmostEqual(summary["deemed_disposal_tax"], 114.)
        self.assertAlmostEqual(summary["total_tax"], 154.28)
        self.assertAlmostEqual(summary["final_cash"], 521.72)
        final = ledger[ledger.event.eq("final_sale")].iloc[0]
        self.assertAlmostEqual(deposits.cash.sum()+sales.gross_proceeds.sum()
                               +final.gross_proceeds-deposits.invested_cash.sum()
                               -summary["total_tax"], summary["final_cash"])

    def test_deemed_disposal_continues_at_year_twenty_four(self):
        prices = pd.Series([100., 200., 300., 400., 500.], index=pd.to_datetime(
            ["2000-01-31", "2008-01-31", "2016-01-31", "2024-01-31", "2025-01-31"]))
        summary, ledger, _ = replay(prices, start="2000-01-31", end="2025-01-31",
                                    contribution_amounts=(1000., 0., 0., 0.))
        disposals = ledger[ledger.event.eq("deemed_disposal")]
        self.assertEqual(disposals.date.tolist(), list(prices.index[1:4]))
        # Tax sales leave 8.1 units at year 8 and 7.074 units at year 16.
        # Year 24 adds 38 tax per unit after the prior 76 credit per unit.
        self.assertAlmostEqual(disposals.iloc[2].units, 7.074)
        self.assertAlmostEqual(disposals.iloc[2].tax, 7.074 * (300. * .38 - 76.))
        self.assertAlmostEqual(summary["final_cash"], 2957.71014)

    def test_invalid_amounts_fail_before_replay(self):
        for amounts in ((1000.0,) * 3, (1000.0,) * 5, (0.0, -1.0, 0.0, 0.0),
                        (0.0, float("nan"), 0.0, 0.0), (0.0, float("inf"), 0.0, 0.0),
                        (0.0, float("-inf"), 0.0, 0.0)):
            with self.subTest(amounts=amounts), self.assertRaises(ValueError):
                replay(self.prices, contribution_amounts=amounts, **self.options)


if __name__ == "__main__":
    unittest.main()
