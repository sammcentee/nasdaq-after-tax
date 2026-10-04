"""Verify that queued-ledger checks accept fills and reject altered evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import asdict
import json
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "model"))
import audit_ledgers
from direct_stock_backtest import BacktestConfig, run_backtest


class QueuedLedgerAuditTests(unittest.TestCase):
    def result(self, fill_price=120., loss_signal=False, execution_mode="next_session"):
        days = ["2020-01-02", "2020-01-03", "2020-02-03", "2020-02-04", "2020-02-05", "2020-03-02"]
        prices = pd.DataFrame(dict(date=days, security_id="A",
                                  price_eur=[100., 100., 90. if loss_signal else 110., fill_price, 125., 130.]))
        weights = pd.DataFrame([dict(effective_date="2020-01-01", available_date="2020-01-01",
                                     security_id="A", weight=1.)])
        config = BacktestConfig(start=days[0], end=days[-1], contribution_dates=(days[0],),
                                fx_fee=0., cgt_exemption=50., execution_mode=execution_mode,
                                harvest=loss_signal, harvest_review_dates=("2020-02-03",),
                                gain_harvest=not loss_signal, gain_review_dates=("2020-02-03",),
                                gain_harvest_reinvest="same_security")
        result = run_backtest(prices, weights, config)
        result.summary["configuration"] = asdict(config)
        return result

    def audit(self, result, alter=None):
        transactions = result.transactions.copy(deep=True)
        if alter is not None:
            alter(transactions)
        with TemporaryDirectory() as directory:
            path = Path(directory)
            summary = path / "fixture_summary.json"
            summary.write_text(json.dumps(result.summary))
            transactions.to_csv(path / "fixture_transactions.csv.gz", index=False)
            result.yearly_tax.to_csv(path / "fixture_yearly_tax.csv", index=False)
            result.lots.to_csv(path / "fixture_lots.csv.gz", index=False)
            result.daily.to_csv(path / "fixture_daily.csv.gz", index=False)
            with patch.object(audit_ledgers, "OUT", path):
                return audit_ledgers.audit_case(summary)

    def test_actual_gain_tax_overrun_and_later_repurchase_pass(self):
        audit = self.audit(self.result())
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["gain_repurchase_count"], 1)
        self.assertEqual(audit["queued_fills_checked"], 3)
        self.assertAlmostEqual(audit["maximum_gain_harvest_incremental_cgt_eur"], 16.5)
        deviation = audit["execution_deviations"][0]
        self.assertAlmostEqual(deviation["signal_incremental_cgt_eur"], 0.)
        self.assertAlmostEqual(deviation["actual_incremental_cgt_eur"], 16.5)

    def test_actual_gain_sign_reversal_passes_without_repurchase(self):
        audit = self.audit(self.result(fill_price=90.))
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["sign_reversals_at_fill"], 1)
        self.assertEqual(audit["gain_repurchase_count"], 0)

    def test_loss_signal_can_fill_at_a_profit(self):
        audit = self.audit(self.result(fill_price=110., loss_signal=True))
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["sign_reversals_at_fill"], 1)

    def test_signal_gain_and_fifo_evidence_cannot_be_changed(self):
        result = self.result()
        for field, value, message in (
            ("expected_gains_eur", 500., "expected_gains_eur"),
            ("signal_position_lot_ids", "[-1, 1]", "skipped an earlier FIFO lot"),
            ("signal_date", "2020-02-04", "Invalid or duplicate order signal"),
        ):
            with self.subTest(field=field):
                def alter(t):
                    t.loc[t.event.eq("order_signal") & t.reason.eq("gain_harvest"), field] = value
                with self.assertRaisesRegex(AssertionError, message):
                    self.audit(result, alter)

    def test_fixed_sale_quantity_and_buy_budget_cannot_be_changed(self):
        result = self.result()
        def change_units(t):
            t.loc[t.event.eq("sell") & t.reason.eq("gain_harvest"), "units"] += 1.
        with self.assertRaisesRegex(AssertionError, "Fixed sale units"):
            self.audit(result, change_units)
        def change_budget(t):
            t.loc[t.event.eq("order_signal") & t.reason.eq("gain_repurchase"), "cash_budget_eur"] -= 10.
        with self.assertRaisesRegex(AssertionError, "fixed notional budget"):
            self.audit(result, change_budget)

    def test_actual_tax_and_repurchase_link_cannot_be_changed(self):
        result = self.result()
        def change_tax(t):
            t.loc[t.event.eq("order_fill") & t.reason.eq("gain_harvest"), "incremental_cgt_eur"] = 0.
        with self.assertRaisesRegex(AssertionError, "Actual fill CGT"):
            self.audit(result, change_tax)
        def change_link(t):
            t.loc[t.event.eq("buy") & t.reason.eq("gain_repurchase"), "sale_order_id"] = 999.
        with self.assertRaisesRegex(AssertionError, "originating sale"):
            self.audit(result, change_link)

    def test_legacy_same_close_audit_remains_active(self):
        audit = self.audit(self.result(execution_mode="same_close"))
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["queued_signals_checked"], 0)
        self.assertEqual(audit["maximum_gain_harvest_incremental_cgt_eur"], 0.)

    def test_split_adjusted_units_keep_original_basis(self):
        days = ["2020-01-02", "2020-01-03", "2020-03-02", "2020-03-03", "2020-03-04"]
        prices = pd.DataFrame(dict(date=days, security_id="A", price_eur=[100., 100., 80., 40., 40.]))
        weights = pd.DataFrame([dict(effective_date="2020-01-01", available_date="2020-01-01",
                                     security_id="A", weight=1.)])
        config = BacktestConfig(start=days[0], end=days[-1], contribution_dates=(days[0],),
                                execution_mode="next_session", harvest_review_dates=(days[2],), fx_fee=0.)
        events = pd.DataFrame([dict(date=days[3], security_id="A", event_type="split", ratio=2.)])
        result = run_backtest(prices, weights, config, events)
        result.summary["configuration"] = asdict(config)
        audit = self.audit(result)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["queued_fills_checked"], 2)

    def test_daily_tax_reserve_cannot_be_changed(self):
        result = self.result()
        result.daily.loc[result.daily.date.eq(pd.Timestamp("2020-02-04")), "cgt_reserve_eur"] = 0.
        with self.assertRaisesRegex(AssertionError, "Daily cgt_reserve_eur"):
            self.audit(result)


if __name__ == "__main__":
    unittest.main()
